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

Mission 3 (M3-C): Evidence-chain penalty cho final — giữ item (không xóa),
  trừ điểm confidence + ghi limitation nếu không có chuỗi diễn biến
  (≥2 role kêu quyết định khác nhau trong evidence) hoặc hedge còn sót trong
  quote chốt.
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

_SELF_PRONOUNS = frozenset({"em", "anh", "chị", "tớ", "mình", "tôi"})
_FILLER_RE = re.compile(r"^(?:dạ|vâng|ạ)\s+", flags=re.IGNORECASE)
_PARTICLE_RE = re.compile(r"\s*(?:ạ|dạ|vâng|nhé|nha|nhe|ha|hả)\s*$", flags=re.IGNORECASE)
# LƯU Ý: không liệt kê động từ nhận việc ở đây — volunteer check dùng cấu trúc
# (đại từ mở đầu + không tên cụ thể) vì động từ là lớp mở, liệt kê không bao giờ đủ.


def _resolve_self_reference(
    owner_raw: str,
    evidence: list[dict[str, Any]],
    participants: list[Participant],
) -> tuple[str, str] | None:
    """Đại từ tự xưng trong field owner ("Em làm ạ") → speaker nói câu evidence đó."""
    s = str(owner_raw or "").strip()
    if not s or s == TBD_SENTINEL:
        return None
    s_lower = s.lower()
    names: set[str] = set()
    for p in participants:
        names.add(p.name.lower())
        names.update((a or "").lower() for a in (p.aliases or []))
    names.discard("")
    if any(n in s_lower for n in names):
        return None
    core = _FILLER_RE.sub("", s_lower).strip()
    core = _PARTICLE_RE.sub("", core).strip()
    toks = core.split()
    if not toks or toks[0] not in _SELF_PRONOUNS:
        return None
    evs = evidence or []
    speaker = (evs[0].get("speaker", "") or "").strip() if evs else ""
    if not speaker:
        return None
    for p in participants:
        if speaker == p.name or speaker in (p.aliases or []):
            return p.name, "inferred"
    return None


def _resolve_volunteer_from_quote(
    evidence: list[dict[str, Any]],
    participants: list[Participant],
) -> tuple[str, str] | None:
    """Câu evidence tự nhận việc ("Em làm ạ", "Dạ em cover phần này") → speaker.

    CẤU TRÚC, không danh sách động từ (động từ là lớp mở — liệt kê không bao giờ
    đủ): quote mở đầu bằng [dạ/vâng] + đại từ tự xưng, KHÔNG chứa tên/alias cụ
    thể nào, và speaker thuộc participants. "Em Nam gửi..." có tên → loại ngay.
    Returns (name, "inferred") hoặc None.
    """
    evs = evidence or []
    if not evs:
        return None
    quote = str((evs[0].get("quote") or "")).strip()
    speaker = str((evs[0].get("speaker") or "")).strip()
    if not quote or not speaker:
        return None
    names: set[str] = set()
    for p in participants:
        names.add(p.name.lower())
        names.update((a or "").lower() for a in (p.aliases or []))
    names.discard("")
    if any(n in quote.lower() for n in names):
        return None
    toks = quote.lower().split()
    while toks and toks[0] in ("dạ", "vâng", "ạ"):
        toks.pop(0)
    if not toks or toks[0] not in _SELF_PRONOUNS:
        return None
    for p in participants:
        if speaker == p.name or speaker in (p.aliases or []):
            return p.name, "inferred"
    return None


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
    - CHỨA đúng 1 tên/alias trong câu ("em Hà làm nhé" → Hà) → (name, "inferred")
    - Không khớp, rỗng, hoặc chứa ≥2 tên (mơ hồ) → ("TBD", "tbd")
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
    # Contains-fallback: tên/alias xuất hiện trong câu dài.
    lowered = owner_clean.lower()
    hits: list[str] = []
    for p in participants:
        candidates = [p.name] + list(p.aliases or [])
        if any(c and c.lower() in lowered for c in candidates):
            hits.append(p.name)
    if len(hits) == 1:
        return hits[0], "inferred"
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
    # M3-C new optional penalties (defaults 0.0 để backward compat)
    single_evidence_final: bool = False,
    hedge_final: bool = False,
) -> tuple[float, str, list[str]]:
    """Apply formula: clamp01(conf_llm + quote + tbd + inferred + m3_c).

    quote_matched và evidence_mismatch loại trừ nhau — apply max 1.
    Contradiction (-0.20) được áp riêng bởi verify_state (chỉ áp cho final decisions).

    M3-C extras (chỉ cho Decision final):
      - single_evidence_final: -0.20 nếu final không có ≥2 role khác nhau
        trong evidence (propose/object/confirm). Trung thực — KHÔNG xóa, chỉ
        hạ điểm để host soi.
      - hedge_final: -0.15 nếu final còn sót hedge marker (có lẽ, xem xét,
        sớm nhé, ...) — defense in depth nếu resolve._apply_hedge_gate lọt.

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

    # M3-C: penalties cho evidence-chain & hedge trên final.
    if single_evidence_final:
        delta -= 0.20
        notes.append("single-evidence-final -0.20")
    if hedge_final:
        delta -= 0.15
        notes.append("hedge-final -0.15")

    final = max(0.0, min(1.0, conf_llm + delta))
    reason = f"conf_llm={conf_llm:.2f}; " + ("; ".join(notes) if notes else "no adjust")
    return final, reason, notes


# ──────────────────────────────────────────────────────────────────────
# M3-C: Evidence-chain check cho Decision final
# ──────────────────────────────────────────────────────────────────────


# Hedge lexicon (mirror resolve.HEDGE_RE) — defense in depth ở verify
# nếu resolve._apply_hedge_gate lọt qua vì không có turns hoặc data thiếu.
_HEDGE_RE = re.compile(
    r"\bc[óo]\s*l[ẽe]\b|\bc[óo]\s*th[ểe]\b|\bxem\s*x[éé]t\b|"
    r"\bt[íi]nh\s*sau\b|\bs[ớo]m\s*nh[éh]\b|\bkhi\s*n[àa]o\s*xong\b|"
    r"\banh\s*em\s*tri[ểe]n\s*khai\s*nh[éh]\b|\bđ[ểe]\s*b[àa]n\s*sau\b|"
    r"\bch[ưu]a\s*ch[ắa]c\b|\bt[ạa]m\s*th[ờo]i\b",
    re.IGNORECASE,
)

# Role chain "diễn biến" — propose/object/confirm đều tính là 1 role khác
# decide. ≥2 role khác nhau trong evidence = có chuỗi diễn biến.
_CHAIN_ROLES = frozenset({"propose", "object", "decide", "confirm"})


def _has_hedge_text(text: str) -> bool:
    return bool(_HEDGE_RE.search(text or ""))


def _check_evidence_chain_for_final(
    item_dict: dict[str, Any],
) -> tuple[bool, bool, str]:
    """M3-C: kiểm chuỗi diễn biến + hedge cho final.

    Returns: (single_evidence_final, hedge_final, reason_detail).
    - single_evidence_final=True nếu evidence chỉ có 1 decide + không có
      role khác (propose/object/confirm) → diễn biến đơn lẻ.
    - hedge_final=True nếu content hoặc quote chốt còn hedge (defense in depth).

    reason_detail dùng để ghi limitation chi tiết (KHÔNG xóa item, chỉ hạ điểm).
    """
    item_type = item_dict.get("type")
    if item_type != "decision" or item_dict.get("status") != "final":
        return False, False, ""

    evs = item_dict.get("evidence") or []
    chain_roles = set()
    for ev in evs:
        r = ev.get("role_in_discussion")
        if r in _CHAIN_ROLES:
            chain_roles.add(r)

    # single-evidence-final: chỉ 1 role "decide" + không role phụ
    single = (len(chain_roles) == 1 and "decide" in chain_roles
              and len(evs) <= 1)

    hedge = False
    if _has_hedge_text(str(item_dict.get("content") or "")):
        hedge = True
    if not hedge:
        for ev in evs:
            if (ev.get("role_in_discussion") or "") == "decide":
                if _has_hedge_text(ev.get("quote", "")):
                    hedge = True
                    break

    detail = []
    if single:
        detail.append(
            f"single-evidence-final: chỉ {len(evs)} evidence, "
            f"role={chain_roles or 'none'}"
        )
    if hedge:
        detail.append("hedge-final: content/quote còn hedge")
    return single, hedge, "; ".join(detail)


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
            # Self-reference: "Em làm ạ" (không kèm tên) do chính speaker nói
            # → owner là speaker đó (live sample đàm phán: Nam "Em làm ạ" → Nam,
            # Hà "Em review giúp" → Hà). Chỉ khi KHÔNG chứa tên/alias nào khác.
            # Nếu model đã bó tay (owner=TBD) mà QUOTE evidence tự nhận việc
            # ("Dạ em gửi báo giá") → cũng resolve từ speaker (volunteer).
            _self_resolved = False
            if owner == TBD_SENTINEL:
                _self = _resolve_self_reference(
                    item_dict.get("owner", ""), item_dict.get("evidence", []),
                    participants,
                )
                if _self is None:
                    _self = _resolve_volunteer_from_quote(
                        item_dict.get("evidence", []), participants
                    )
                if _self is not None:
                    owner, owner_src = _self
                    _self_resolved = True
                    limitations.append(
                        f"item {item_id} (task): owner tự nhận việc "
                        f"{item_dict.get('owner')!r} → {owner} (inferred)"
                    )
            old_owner = item_dict.get("owner", "")
            item_dict["owner"] = owner
            # Nếu ta đã ép TBD, force source = tbd. Nếu ta tự suy ra owner
            # (self-reference), force source = inferred (không giữ claim cũ).
            if owner == TBD_SENTINEL:
                item_dict["owner_source"] = "tbd"
            elif _self_resolved:
                item_dict["owner_source"] = "inferred"
            else:
                # Source LUÔN theo suy luận của ta (canonicalize), không giữ
                # claim của model (vd model ghi "explicit" cho tên suy ra).
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
            # Due inferred mà THIẾU due_hint → không kiểm chứng được (ENTITY CONTRACT
            # bắt hint giữ chữ gốc). Giữ due nhưng ghi limitation cho host soi.
            if (
                item_dict.get("due") != TBD_SENTINEL
                and item_dict.get("due_source") == "inferred"
                and not item_dict.get("due_hint")
            ):
                limitations.append(
                    f"item {item_id} (task): due inferred nhưng thiếu due_hint — "
                    f"không kiểm chứng được chữ gốc"
                )
        elif item_type == "blocker":
            naf = item_dict.get("needs_action_from", "")
            if naf and naf != TBD_SENTINEL:
                canonical, _ = canonicalize_owner(naf, participants)
                item_dict["needs_action_from"] = canonical
        elif item_type == "requirement":
            # Origin ngoài allowlist (model hay viết câu dài) → "unknown" +
            # limitation, GIỮ item (origin là metadata phụ như role — mất cả
            # item vì 1 field phụ là sai lầm đã trả giá ở brainstorm).
            origin = str(item_dict.get("origin") or "").strip().lower()
            if origin not in ("customer", "internal", "partner"):
                if origin and origin != "unknown":
                    limitations.append(
                        f"item {item_id} (requirement): origin {origin[:40]!r} "
                        f"không hợp lệ → 'unknown'"
                    )
                item_dict["origin"] = "unknown"
        elif item_type == "open_issue":
            nso = item_dict.get("next_step_owner")
            if nso and nso != TBD_SENTINEL:
                canonical, _ = canonicalize_owner(nso, participants)
                item_dict["next_step_owner"] = canonical
            # next_step là bắt buộc (R3) nhưng model họp mơ hồ hay bỏ trống →
            # điền placeholder thủ tục + limitation, GIỮ item (bỏ cả item vì
            # thiếu 1 field thủ tục thì mất luôn record "chưa chốt" — sai lầm
            # đã trả giá ở brainstorm). Placeholder trung thực: ghi rõ host làm.
            if not str(item_dict.get("next_step") or "").strip():
                item_dict["next_step"] = "Host xác định bước tiếp theo"
                limitations.append(
                    f"item {item_id} (open_issue): thiếu next_step → "
                    f"placeholder cho host (R3)"
                )

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
        if (
            not evidence_list
            and item_type != "knowledge"
            and not item_dict.get("system_generated")
        ):
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
            matched, _ratio, _idx, _method = find_quote_in_turns(
                quote, turns, claimed_turn
            )
            if matched:
                quote_matched_any = True
                # Sửa ts/turn/speaker về turn KHỚP THẬT (model hay gán sai ts
                # vài giây dù quote đúng — live tc1: quote 04:14 gán ts 04:24).
                if _idx is not None and 0 <= _idx < len(turns):
                    t = turns[_idx]
                    if (
                        ev.get("timestamp") != t.get("t_start")
                        or ev.get("turn") != t.get("turn")
                    ):
                        limitations.append(
                            f"item {item_id} ({item_type}): evidence ts "
                            f"{ev.get('timestamp')} → {t.get('t_start')} "
                            f"(khớp quote tại turn {t.get('turn')})"
                        )
                    ev["timestamp"] = t.get("t_start", ev.get("timestamp"))
                    ev["turn"] = t.get("turn", ev.get("turn"))
                    ev["speaker"] = t.get("speaker", ev.get("speaker"))
            else:
                mismatch_any = True

        # ─── 3. Confidence (taxonomy §5) ───
        conf_llm = conf_llm_map.get(
            item_id,
            float(item_dict.get("confidence", 0.5) or 0.5),
        )

        # M3-C: check evidence-chain + hedge cho Decision final TRƯỚC khi
        # compute confidence. Kết quả truyền vào compute_confidence làm penalty
        # và ghi limitation chi tiết (KHÔNG xóa item, chỉ hạ điểm).
        single_ev_final, hedge_final, m3_detail = (
            _check_evidence_chain_for_final(item_dict)
        )

        final_conf, conf_reason, _notes = compute_confidence(
            conf_llm=conf_llm,
            quote_matched=quote_matched_any,
            evidence_mismatch=mismatch_any,
            item_dict=item_dict,
            single_evidence_final=single_ev_final,
            hedge_final=hedge_final,
        )
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

        # M3-C: ghi limitation chi tiết nếu final thiếu chain / có hedge.
        # Không xóa item — trung thực, host soi.
        if m3_detail:
            limitations.append(
                f"item {item_id} ({item_type}): M3-C {m3_detail}"
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

    # ─── 6. Contradiction trên finals SỐNG SÓT (không phạt oan).
    # Penalty cũ tính trên raw input (kể cả item sau đó rớt) → stale.
    # Chỉ khi ≥2 final cùng tồn tại sau validate mới trừ điểm + log.
    surviving_finals = [
        it for it in validated_items
        if isinstance(it, Decision) and it.status == "final"
    ]
    if len(surviving_finals) > 1:
        for it in surviving_finals:
            it.confidence = max(0.0, float(it.confidence) - 0.20)
            it.confidence_reason += "; contradiction -0.20"
        # Tính lại badge (penalty có thể đổi màu).
        badge_counter = Counter(badge_for(it.confidence) for it in validated_items)
        limitations.append(
            f"R4: {len(surviving_finals)} Decision final cùng tồn tại — "
            f"mâu thuẫn tiềm ẩn, mỗi final -0.20"
        )

    # ─── 7. Stats ───
    stats = Stats(
        by_type=dict(type_counter),
        items_total=sum(type_counter.values()),
        by_badge=dict(badge_counter),
    )

    # ─── 7. Brief ref-check (taxonomy §8): outcome phải trỏ tới ID đã chốt.
    # "Nói ra" ≠ "chốt" — outcome không có ref tương ứng thì không tồn tại.
    brief = _verify_brief(brief_raw, validated_items, limitations)

    # ─── 8. Toàn vẹn link: link_to_decision phải trỏ tới item TỒN TẠI.
    # Model hay link tới ID tưởng tượng (live tc1: link=D2 không tồn tại).
    valid_ids = {it.id for it in validated_items}
    for it in validated_items:
        link = getattr(it, "link_to_decision", None)
        if link and link not in valid_ids:
            limitations.append(
                f"item {it.id}: link_to_decision={link} không tồn tại → null"
            )
            it.link_to_decision = None

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