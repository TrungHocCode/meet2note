"""
verify.py — Thuần Python, KHÔNG LLM. Enforce R1/R2/R5 + công thức confidence.

Hợp đồng input/output:
- Input: meeting (Meeting Pydantic), items_raw (list[dict] từ extract),
  conf_llm_map (dict[id, float]), turns (list[dict]), limitations (list[str] optional).
- Output: MeetingState (Pydantic, validated).

Triết lý (AGENTS.md §1, taxonomy §5):
- Quote verify: normalize (lowercase, bỏ dấu câu, collapse whitespace) →
  difflib.SequenceMatcher.ratio ≥ 0.85 so với turn đã claim; thử ±2 turns.
- Substring fallback: nếu quote là substring của turn và coverage ≥ 50%
  (quote ≥ 10 chars) → matched (cho phép LLM trích câu con của turn dài).
- TBD enforcement (R1, R2): owner ngoài participants → TBD; due không ISO + không
  phải "TBD" → TBD + due_hint.
- R4: phát hiện >1 final decision → đánh dấu contradiction (-0.20 mỗi final).
  Reverse graph (A→B→A) thuộc resolve phase — chỉ log limitation ở đây.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Any

from .schema import (
    BriefOutcome,
    Decision,
    Item,
    ItemTypeAdapter,
    Meeting,
    MeetingBrief,
    MeetingState,
    OpenIssue,
    Participant,
    Stats,
    TBD_SENTINEL,
)


# ──────────────────────────────────────────────────────────────────────
# Normalize + fuzzy match
# ──────────────────────────────────────────────────────────────────────

# Bỏ mọi ký tự không phải chữ/số/khoảng trắng (Unicode-aware cho tiếng Việt).
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)

# Allowlist role_in_discussion (taxonomy §2) — ngoài danh sách → "info" + limitation.
_VALID_ROLES = frozenset({"propose", "object", "decide", "confirm", "info"})
_SPACE_RE = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """Lowercase, bỏ dấu câu, collapse whitespace (taxonomy §5)."""
    t = text.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _SPACE_RE.sub(" ", t).strip()
    return t


def quote_match(
    quote: str,
    turn_text: str,
    *,
    threshold: float = 0.85,
    min_substring_len: int = 10,
    min_coverage: float = 0.30,
) -> tuple[bool, float, str]:
    """Check if `quote` fuzzy-matches `turn_text` (taxonomy §5).

    Hai chiến lược:
    - "ratio": difflib.SequenceMatcher.ratio(q, t) >= threshold (default 0.85).
    - "substring": q fully contained trong t, len(q) >= min_substring_len (default 10),
      coverage = len(q)/len(t) >= min_coverage (default 0.30).

    Lý do coverage thấp (0.30 thay vì 0.5):
    - Turn thực tế có thể dài (≥80 chars), LLM trích câu con (10-20 chars).
    - Ví dụ tc2: quote "Vậy chốt B nhé" (13 chars) vs turn 34 chars → coverage 38%.
    - Vẫn đủ non-trivial vì len(q) >= 10 và quote phải fully contained.

    Returns: (matched, ratio, method) — method ∈ {"ratio", "substring", "none"}.
    """
    nq = normalize_for_match(quote)
    nt = normalize_for_match(turn_text)
    if not nq or not nt:
        return False, 0.0, "none"

    ratio = difflib.SequenceMatcher(None, nq, nt).ratio()
    if ratio >= threshold:
        return True, ratio, "ratio"

    # Substring check (chỉ áp dụng khi quote đủ dài để tránh match vặt vãi)
    if nq in nt and len(nq) >= min_substring_len:
        coverage = len(nq) / len(nt)
        if coverage >= min_coverage:
            # Substring "effective ratio" = 2 * len(q) / (len(q) + len(t))
            sub_ratio = 2 * len(nq) / (len(nq) + len(nt))
            return True, max(ratio, sub_ratio), "substring"

    return False, ratio, "none"


def find_quote_in_turns(
    quote: str,
    turns: list[dict[str, Any]],
    target_turn: int | None,
    *,
    window: int = 2,
    threshold: float = 0.85,
) -> tuple[bool, float, int | None, str]:
    """Tìm quote trong ±`window` turns quanh `target_turn` (taxonomy §5).

    Nếu không có target_turn, scan toàn bộ turns.
    Returns: (matched, best_ratio, matched_turn_idx_0based, method).
    """
    if not turns:
        return False, 0.0, None, "none"

    # Build candidate list (target ± window, dedup, giữ thứ tự)
    seen_idx: set[int] = set()
    candidates: list[int] = []
    if target_turn is not None and 1 <= target_turn <= len(turns):
        for off in range(-window, window + 1):
            idx = target_turn - 1 + off
            if 0 <= idx < len(turns) and idx not in seen_idx:
                candidates.append(idx)
                seen_idx.add(idx)
    if not candidates:
        candidates = list(range(len(turns)))

    best_matched = False
    best_ratio = 0.0
    best_idx: int | None = None
    best_method = "none"

    for idx in candidates:
        m, r, method = quote_match(quote, turns[idx]["text"], threshold=threshold)
        if r > best_ratio:
            best_ratio = r
            best_idx = idx
            best_method = method
            best_matched = m

    return best_matched, best_ratio, best_idx, best_method


def badge_for(conf: float) -> str:
    """Đỏ <0.50 · vàng 0.50-0.75 · xanh ≥0.75 (taxonomy §5)."""
    if conf < 0.50:
        return "red"
    if conf < 0.75:
        return "yellow"
    return "green"


# ──────────────────────────────────────────────────────────────────────
# TBD enforcement (R1, R2)
# ──────────────────────────────────────────────────────────────────────


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso_date(s: str) -> bool:
    return bool(_ISO_RE.match(s))


def canonicalize_owner(
    owner: str,
    participants: list[Participant],
) -> tuple[str, str]:
    """Đổi owner về tên trong participants, gán source (R1 — taxonomy §6).

    Returns: (canonical_name_or_TBD, owner_source).
    - Khớp `name` chính xác → (name, "explicit")
    - Khớp alias → (name, "inferred")
    - Không khớp hoặc rỗng → ("TBD", "tbd")
    """
    if not owner or owner.strip() == TBD_SENTINEL:
        return TBD_SENTINEL, "tbd"

    owner_clean = owner.strip()
    for p in participants:
        if owner_clean == p.name:
            return p.name, "explicit"
    for p in participants:
        if owner_clean in (p.aliases or []):
            return p.name, "inferred"
    return TBD_SENTINEL, "tbd"


def normalize_due(due: str) -> tuple[str, str]:
    """Đảm bảo due là ISO YYYY-MM-DD hoặc TBD (R2).

    Returns: (due_canonical, due_source).
    - ISO hợp lệ → (value, "explicit")
    - "TBD" → ("TBD", "tbd")
    - Còn lại (sớm nhé / ASAP / "tuần sau" / ...) → ("TBD", "tbd")
      (full relative-date parsing thuộc resolve phase — taxonomy §6).
    """
    if not due or not due.strip():
        return TBD_SENTINEL, "tbd"
    d = due.strip()
    if d.upper() == TBD_SENTINEL:
        # Chấp nhận mọi case ("tbd", "Tbd") — model local hay viết thường.
        return TBD_SENTINEL, "tbd"
    if _is_iso_date(d):
        return d, "explicit"
    return TBD_SENTINEL, "tbd"


# ──────────────────────────────────────────────────────────────────────
# Confidence formula (taxonomy §5) — deterministic
# ──────────────────────────────────────────────────────────────────────


def _count_tbd_fields(item: dict[str, Any]) -> int:
    """Đếm số field = TBD (taxonomy §5 — mỗi field -0.15)."""
    count = 0
    itype = item.get("type")
    if itype == "task":
        if item.get("owner") == TBD_SENTINEL:
            count += 1
        if item.get("due") == TBD_SENTINEL:
            count += 1
    elif itype == "blocker":
        if item.get("needs_action_from") == TBD_SENTINEL:
            count += 1
    elif itype == "open_issue":
        if item.get("next_step_owner") == TBD_SENTINEL:
            count += 1
    return count


def _count_inferred_fields(item: dict[str, Any]) -> int:
    """Đếm số field source=inferred (taxonomy §5 — mỗi field -0.10)."""
    count = 0
    if item.get("type") == "task":
        if item.get("owner_source") == "inferred":
            count += 1
        if item.get("due_source") == "inferred":
            count += 1
    return count


def compute_confidence(
    *,
    conf_llm: float,
    quote_matched: bool,
    evidence_mismatch: bool,
    item_dict: dict[str, Any],
) -> tuple[float, str, list[str]]:
    """Apply formula: clamp01(conf_llm + quote + tbd + inferred + contradiction).

    quote_matched và evidence_mismatch loại trừ nhau — apply max 1.
    Contradiction (-0.20) được áp riêng bởi verify_state (chỉ áp cho final decisions).

    Returns: (final_conf, reason_string, notes_list).
    """
    delta = 0.0
    notes: list[str] = []

    if evidence_mismatch:
        delta -= 0.30
        notes.append("evidence_mismatch -0.30")
    elif quote_matched:
        delta += 0.10
        notes.append("quote_matched +0.10")

    tbd_n = _count_tbd_fields(item_dict)
    if tbd_n > 0:
        d = -0.15 * tbd_n
        delta += d
        notes.append(f"TBD ×{tbd_n} {d:+.2f}")

    inf_n = _count_inferred_fields(item_dict)
    if inf_n > 0:
        d = -0.10 * inf_n
        delta += d
        notes.append(f"inferred ×{inf_n} {d:+.2f}")

    final = max(0.0, min(1.0, conf_llm + delta))
    reason = f"conf_llm={conf_llm:.2f}; " + ("; ".join(notes) if notes else "no adjust")
    return final, reason, notes


# ──────────────────────────────────────────────────────────────────────
# Main: verify_state
# ──────────────────────────────────────────────────────────────────────


def _verify_brief(
    brief_raw: dict[str, Any] | None,
    validated_items: list[Item],
    limitations: list[str],
) -> MeetingBrief | None:
    """Kiểm brief (taxonomy §8): problem bắt buộc; outcome chỉ giữ khi có
    ≥1 ref_id tồn tại trong items đã validate. Không ref = phát biểu đó chưa
    thành Decision/OpenIssue = không được ghi nhận là kết quả."""
    if not brief_raw:
        return None
    try:
        brief = MeetingBrief.model_validate(brief_raw)
    except Exception as e:
        limitations.append(f"brief: parse fail ({e}) — bỏ brief")
        return None
    valid_ids = {i.id for i in validated_items}
    kept: list[BriefOutcome] = []
    for oc in brief.outcomes:
        good_refs = [r for r in oc.ref_ids if r in valid_ids]
        if not good_refs:
            limitations.append(
                f"brief: outcome không trỏ tới ID đã chốt → bỏ "
                f"({oc.text[:60]!r}, refs={oc.ref_ids})"
            )
            continue
        kept.append(BriefOutcome(text=oc.text, ref_ids=good_refs))
    return MeetingBrief(problem=brief.problem.strip(), outcomes=kept)


def verify_state(
    *,
    meeting: Meeting,
    items_raw: list[dict[str, Any]],
    conf_llm_map: dict[str, float],
    turns: list[dict[str, Any]],
    limitations: list[str] | None = None,
    brief_raw: dict[str, Any] | None = None,
) -> MeetingState:
    """Build MeetingState: validate items + enforce R1/R2/R5 + compute badges.

    Args:
        meeting: Meeting (Pydantic).
        items_raw: list raw item dict từ extract.
        conf_llm_map: dict[item_id, conf_llm] từ extract.
        turns: list turn dict (dùng để quote verify).
        limitations: extra limitations (ingest + extract) để carry forward.

    Returns:
        MeetingState — Pydantic validated.

    Side effects: bỏ qua item vi phạm R1/R2 nghiêm trọng (không parse được)
    → ghi vào known_limitations thay vì fail cả meeting.
    """
    limitations = list(limitations or [])
    participants = meeting.participants

    # Count final decisions để phát hiện contradiction (R4 — phần đơn giản)
    final_count = sum(
        1 for raw in items_raw
        if raw.get("type") == "decision" and raw.get("status") == "final"
    )
    has_contradiction = final_count > 1

    validated_items: list[Item] = []
    type_counter: Counter[str] = Counter()
    badge_counter: Counter[str] = Counter()
    has_final_decision = False
    has_open_issue_with_next_step = False

    for raw in items_raw:
        # Shallow copy để không mutate dict của extract
        item_dict = dict(raw)
        item_id = str(item_dict.get("id", "?"))
        item_type = item_dict.get("type")

        # ─── 1. TBD enforcement + canonicalize ───
        if item_type == "task":
            owner, owner_src = canonicalize_owner(
                item_dict.get("owner", ""), participants
            )
            old_owner = item_dict.get("owner", "")
            item_dict["owner"] = owner
            # Nếu ta đã ép TBD, force source = tbd
            if owner == TBD_SENTINEL:
                item_dict["owner_source"] = "tbd"
            elif item_dict.get("owner_source") not in ("explicit", "inferred", "tbd"):
                item_dict["owner_source"] = owner_src

            old_due = item_dict.get("due", "")
            due, due_src = normalize_due(old_due)
            item_dict["due"] = due
            if due == TBD_SENTINEL and old_due and old_due != TBD_SENTINEL:
                # Lưu chữ gốc mơ hồ vào due_hint
                if not item_dict.get("due_hint"):
                    item_dict["due_hint"] = old_due
                # Ta đã ép TBD → force source = tbd (như owner).
                item_dict["due_source"] = "tbd"
            hint = item_dict.get("due_hint")
            if isinstance(hint, str) and (
                not hint.strip() or hint.strip().upper() == TBD_SENTINEL
            ):
                # hint 'tbd'/rỗng của model = không thông tin → None cho sạch.
                item_dict["due_hint"] = None
                item_dict["due_source"] = "tbd"
            elif item_dict.get("due_source") not in ("explicit", "inferred", "tbd"):
                item_dict["due_source"] = due_src
        elif item_type == "blocker":
            naf = item_dict.get("needs_action_from", "")
            if naf and naf != TBD_SENTINEL:
                canonical, _ = canonicalize_owner(naf, participants)
                item_dict["needs_action_from"] = canonical
        elif item_type == "open_issue":
            nso = item_dict.get("next_step_owner")
            if nso and nso != TBD_SENTINEL:
                canonical, _ = canonicalize_owner(nso, participants)
                item_dict["next_step_owner"] = canonical

        # ─── 1b. Confidence gate (quyết định #7 — dời từ extract sang đây khi
        # extract nới lỏng shape): thiếu hoặc ngoài [0,1] → bỏ ITEM (không giết
        # chunk, không silent default 0.5).
        raw_conf = item_dict.get("confidence")
        if (
            raw_conf is None
            or isinstance(raw_conf, bool)
            or not isinstance(raw_conf, (int, float))
            or not 0.0 <= float(raw_conf) <= 1.0
        ):
            limitations.append(
                f"item {item_id} ({item_type}): confidence thiếu/ngoài [0,1] — bỏ"
            )
            continue

        # ─── 2. Evidence quote verify (R5) ───
        evidence_list = item_dict.get("evidence", [])
        if not evidence_list and item_type != "knowledge":
            limitations.append(
                f"item {item_id} ({item_type}): thiếu evidence — bỏ"
            )
            continue

        quote_matched_any = False
        mismatch_any = False
        role_normalized = False
        for ev in evidence_list:
            quote = ev.get("quote", "")
            claimed_turn = ev.get("turn")
            # Role ngoài allowlist (vd model local tự đặt "assign") → gán "info"
            # + ghi limitation (accept-with-flag, KHÁC silent default: có vết audit).
            # Role là metadata phụ — không đáng reject cả chunk như confidence (quyết định #7).
            if ev.get("role_in_discussion") not in _VALID_ROLES:
                ev["role_in_discussion"] = "info"
                role_normalized = True
            if not quote:
                mismatch_any = True
                continue
            if not quote:
                mismatch_any = True
                continue
            matched, _ratio, _idx, _method = find_quote_in_turns(
                quote, turns, claimed_turn
            )
            if matched:
                quote_matched_any = True
            else:
                mismatch_any = True

        # ─── 3. Confidence (taxonomy §5) ───
        conf_llm = conf_llm_map.get(
            item_id,
            float(item_dict.get("confidence", 0.5) or 0.5),
        )
        final_conf, conf_reason, _notes = compute_confidence(
            conf_llm=conf_llm,
            quote_matched=quote_matched_any,
            evidence_mismatch=mismatch_any,
            item_dict=item_dict,
        )
        # Contradiction penalty (R4) — chỉ áp cho final decisions khi >1 final
        if has_contradiction and item_type == "decision" and item_dict.get("status") == "final":
            final_conf = max(0.0, final_conf - 0.20)
            conf_reason += "; contradiction -0.20"
        # unresolved_reversal penalty (P2 R4) — đã được resolve flag + O_REV
        if (
            item_type == "decision"
            and item_dict.get("status") == "final"
            and item_dict.get("unresolved_reversal") is True
        ):
            final_conf = max(0.0, final_conf - 0.20)
            conf_reason += "; unresolved_reversal -0.20"

        item_dict["confidence"] = final_conf
        item_dict["confidence_reason"] = conf_reason

        if mismatch_any and item_type != "knowledge":
            limitations.append(
                f"item {item_id} ({item_type}): evidence_mismatch (R5)"
            )
        if role_normalized:
            limitations.append(
                f"item {item_id} ({item_type}): role ngoài allowlist → 'info'"
            )

        # ─── 4. Pydantic validate cuối ───
        try:
            validated = ItemTypeAdapter.validate_python(item_dict)
        except Exception as e:
            err = str(e)
            if len(err) > 200:
                err = err[:200] + "..."
            limitations.append(
                f"item {item_id} ({item_type}): Pydantic reject — {err}"
            )
            continue

        validated_items.append(validated)
        type_counter[item_type] += 1
        badge_counter[badge_for(final_conf)] += 1

        if isinstance(validated, Decision) and validated.status == "final":
            has_final_decision = True
        if isinstance(validated, OpenIssue) and validated.next_step:
            has_open_issue_with_next_step = True

    # ─── 5. R3 — no_decision ───
    # Gốc lệch #3: spec+validator tạo thế kẹt (True thì crash, False thì sai
    # ngữ nghĩa). Phía tối ưu là CODE: tổng hợp system OpenIssue để True hợp lệ.
    no_decision = False
    if not has_final_decision:
        if has_open_issue_with_next_step:
            no_decision = True
        else:
            # LLM trắng final và không tạo Open Issue → verify tự tổng hợp 1
            # system OpenIssue (confidence 0.0 = đỏ) để no_decision=True hợp lệ.
            # Item này KHÓA export (gate R6) cho tới khi host xử lý — trung thực
            # hơn là gắn False như "mọi thứ đã chốt".
            system_issue = OpenIssue(
                id="O_SYS",
                content="Pipeline không xác định được quyết định/trạng thái nào "
                "từ transcript — cần host kiểm tra.",
                next_step="Host mở transcript gốc, xác định trạng thái tay "
                "hoặc chạy lại pipeline.",
                next_step_owner=TBD_SENTINEL,
                confidence=0.0,
                confidence_reason="System fallback R3: LLM không trả final "
                "nào và không tạo Open Issue.",
                evidence=[],
                system_generated=True,
            )
            validated_items.append(system_issue)
            type_counter["open_issue"] += 1
            badge_counter["red"] += 1
            no_decision = True
            limitations.append(
                "R3: LLM trắng final và không có Open Issue — đã tổng hợp "
                "O_SYS (system, confidence 0.0). Host bắt buộc review."
            )

    # ─── 6. Stats + contradiction log ───
    stats = Stats(
        by_type=dict(type_counter),
        items_total=sum(type_counter.values()),
        by_badge=dict(badge_counter),
    )

    if has_contradiction:
        limitations.append(
            f"R4: {final_count} Decision có status=final — mâu thuẫn tiềm ẩn "
            "(resolve phase sẽ xử lý A→B→A / 2 final cùng chủ đề ở P2)"
        )

    # ─── 7. Brief ref-check (taxonomy §8): outcome phải trỏ tới ID đã chốt.
    # "Nói ra" ≠ "chốt" — outcome không có ref tương ứng thì không tồn tại.
    brief = _verify_brief(brief_raw, validated_items, limitations)

    return MeetingState(
        meeting=meeting,
        items=validated_items,
        brief=brief,
        no_decision=no_decision,
        stats=stats,
        known_limitations=limitations,
    )


__all__ = [
    # normalize + match
    "normalize_for_match",
    "quote_match",
    "find_quote_in_turns",
    "badge_for",
    # TBD
    "canonicalize_owner",
    "normalize_due",
    # confidence
    "compute_confidence",
    # main
    "verify_state",
]