"""
pipeline/gates.py — Các cổng kiểm chứng deterministic của Mission 3 (M3-A, M3-B, M3-D, CR-DUE-REV).

Tách từ `pipeline/resolve.py` để giữ module trọng tài xuyên chunk gọn gàng,
dễ đọc và dễ kiểm thử độc lập. `pipeline/resolve.py` vẫn re-export đầy đủ
các symbol để tương thích ngược với test và script eval.

Triết lý (AGENTS.md §1):
- "LLM đề xuất, code kiểm chứng, con người chốt."
- Không xóa item âm thầm — mọi hành động hạ cấp / đổi loại / sửa due đều ghi vết
  vào `known_limitations`.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .schema import Participant, TBD_SENTINEL

# Câu tường thuật lại (recap), KHÔNG phải câu chốt — dù model có gán role=decide.
_RECAP_RE = re.compile(
    r"note lại|ghi lại|tóm lại|recap|tổng hợp lại|nhắc lại|ghi chép|tóm tắt lại"
)


def _is_recap(quote: str) -> bool:
    return bool(_RECAP_RE.search(quote or ""))


# ──────────────────────────────────────────────────────────────────────
# M3-A: Decision Gate 3 điều kiện (chống false decision)
# ──────────────────────────────────────────────────────────────────────

# Động từ chốt — case-insensitive. Whitelist hẹp để KHÔNG bắt nhầm câu thường.
# Đủ để phủ các mẫu phổ biến: chốt, chốt nhé, quyết định, duyệt, thống nhất,
# đồng ý (chốt/làm).
DECIDE_VERBS = re.compile(
    r"\bch[oố]t\b|\bquy[ếe]t\s*đ[ịi]nh|\bduy[ệe]t\b|\bth[ốo]ng\s*nh[ấa]t\b|"
    r"\bđ[ồo]ng\s*[ýy]\s*(?:ch[oố]t|l[àa]m)|\bok\s+ch[oố]t",
    re.IGNORECASE,
)

# Lexicon rút lại / bác / huỷ — phủ 5 turn tiếp theo. Heuristic an toàn.
# Yêu cầu context mạnh (tránh false positive):
# - "thôi" alone (vd "Thôi, tuần sau quyết lại nhé" = postpone, không retract).
# - "khoan" alone ("À khoan, có ai phản đối không?" = rhetorical).
# - Cụm rõ ràng "hủy / bãi bỏ / revert / chưa chốt / chưa đủ dữ liệu" mới tính.
# Để reversal detection (R4) xử lý A→B→A mà không bị M3-A nuốt mất final.
RETRACT_RE = re.compile(
    r"\bth[oô]i\s*(?:đ[ểe]|h[ủu]y|r[ồo]i\s*h[ủu]y)\b|"
    r"\bkhoan[,.]?\s+(?:đ[ãể]|ch[ưu]a\s*ch[oố]t|đ[ợơ]i)\b|"
    r"\bch[ưu]a\s*ch[oố]t\b|\bh[ủu]y\s+(?:task|đ[ềe]u|ch[oố]t|nhé)\b|"
    r"\bb[ãa]i\s*b[ỏo]\b|\bb[áa]c\s*(?:đ[ãể]|v[ậy]nha|nhé|th[ếe]|đề|\w+ng)\b|\bb[áa]c\s*$|"
    r"\bquay\s*l[ạầ]i\b|\brevert\b|\bb[ỏo]\s*qua\b|"
    r"\bch[ưu]a\s*đ[ủu]\s*(?:d[ữu]\s*li[ệe]u|s[ốo])\b",
    re.IGNORECASE,
)


def _has_decide_verb(text: str) -> bool:
    """Quote/content có chứa 1 trong các động từ chốt thật không."""
    return bool(DECIDE_VERBS.search(text or ""))


def _has_retract_signal(
    turns: list[dict[str, Any]] | None,
    after_turn: int | None,
    *,
    window: int = 5,
) -> str | None:
    """Quét các turn SAU after_turn ±window xem có câu rút lại/bác không.

    Trả về quote rút lại (để ghi limitation chi tiết) hoặc None.
    """
    if not turns or after_turn is None:
        return None
    for t in turns:
        tn = t.get("turn")
        if not isinstance(tn, int):
            continue
        if 0 < (tn - after_turn) <= window and RETRACT_RE.search(t.get("text", "")):
            return t.get("text", "")
    return None


def _passes_decision_gate(
    raw: dict[str, Any],
    participants: list[Participant],
    turns: list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """M3-A: Final phải đủ 3 điều kiện, nếu không → trả False + lý do.

    Điều kiện (theo PLAN_M3 §3.1):
      1) Có evidence role=decide KHÔNG-recap với quote chứa động từ chốt.
      2) `decided_by` thuộc participants (không TBD) — CHỈ khi participants có data.
         Backward compat: khi meta thiếu participants, gate KHÔNG phạt vì không
         có info để kiểm chứng (đây là heuristic phòng thủ, không bịa).
      3) Không có câu rút lại / bác trong 5 turn sau evidence quyết định.

    Returns:
        (ok: bool, reason: str|None).
        reason=None khi ok=True; ngược lại reason mô tả điều kiện thiếu.
    """
    evs = raw.get("evidence") or []
    # Điều kiện 1: câu chốt + role=decide + non-recap + quote có DECIDE_VERBS
    last_decide_turn: int | None = None
    has_decide = False
    for ev in evs:
        if (ev.get("role_in_discussion") or "") != "decide":
            continue
        if _is_recap(ev.get("quote", "")):
            continue
        quote = ev.get("quote", "") or ""
        if not _has_decide_verb(quote):
            continue
        has_decide = True
        ev_turn = ev.get("turn")
        if isinstance(ev_turn, int) and (
            last_decide_turn is None or ev_turn > last_decide_turn
        ):
            last_decide_turn = ev_turn
    if not has_decide:
        return False, "missing decide-verb in any decide-role evidence"

    # Điều kiện 2: decided_by thuộc participants (chỉ khi có data)
    decided_by = (raw.get("decided_by") or "").strip()
    if not decided_by:
        return False, "decided_by empty"
    if participants:
        valid_names = {p.name for p in participants}
        if decided_by not in valid_names:
            return False, f"decided_by {decided_by!r} not in participants"

    # Điều kiện 3: kiểm retract chỉ khi có turns data.
    if turns:
        retract = _has_retract_signal(turns, last_decide_turn)
        if retract:
            return False, f"retracted after turn {last_decide_turn}: {retract[:60]!r}"

    return True, None


def _apply_decision_gate(
    items: list[dict[str, Any]],
    participants: list[Participant],
    turns: list[dict[str, Any]] | None,
    limitations: list[str],
) -> None:
    """M3-A: Final không qua gate 3 đk → hạ `final→proposal` + limitation (in-place).

    Không xoá item (giữ audit).
    - Backward compat: participants rỗng → bỏ qua điều kiện 2 (không info, không phạt).
    - turns=None → bỏ qua điều kiện 3 (không có transcript để quét retract).
    """
    for raw in items:
        if raw.get("type") != "decision" or raw.get("status") != "final":
            continue
        passes, fail_reason = _passes_decision_gate(raw, participants, turns)
        if not passes:
            raw["status"] = "proposal"
            limitations.append(
                f"M3-A gate: {raw.get('id')} final→proposal ({fail_reason})"
            )


# ──────────────────────────────────────────────────────────────────────
# M3-B: Hedge lexicon — cấm final + Task hedge → TBD
# ──────────────────────────────────────────────────────────────────────

HEDGE_RE = re.compile(
    r"\bc[óo]\s*l[ẽe]\b|\bc[óo]\s*th[ểe]\b|\bxem\s*x[éé]t\b|"
    r"\bt[íi]nh\s*sau\b|\bs[ớo]m\s*nh[éh]\b|\bkhi\s*n[àa]o\s*xong\b|"
    r"\banh\s*em\s*tri[ểe]n\s*khai\s*nh[éh]\b|\bđ[ểe]\s*b[àa]n\s*sau\b|"
    r"\bch[ưu]a\s*ch[ắa]c\b|\bt[ạa]m\s*th[ờo]i\b|\b[đd][ểe]\s*[xs]em\s*sau\b",
    re.IGNORECASE,
)


def _has_hedge(text: str) -> bool:
    """Content/quote có chứa hedge marker (mơ hồ) không."""
    return bool(HEDGE_RE.search(text or ""))


def _apply_hedge_gate(
    items: list[dict[str, Any]],
    turns: list[dict[str, Any]] | None,
    limitations: list[str],
) -> None:
    """M3-B: hedge trong (b) → cấm final + hạ proposal+task (in-place).

    Không xoá item. Audit-friendly: ghi limitation cho từng case.
    """
    # Build set hedge-marker ở turn nào (1-indexed) — dùng để xử lý Task.
    hedge_turns: set[int] = set()
    if turns:
        for t in turns:
            if _has_hedge(t.get("text", "")):
                tn = t.get("turn")
                if isinstance(tn, int):
                    hedge_turns.add(tn)

    for raw in items:
        rtype = raw.get("type")
        # Decision: hedge trong content hoặc quote chốt → cấm final.
        if rtype == "decision" and raw.get("status") == "final":
            content = str(raw.get("content") or "")
            hedge_in_decide = _has_hedge(content)
            if not hedge_in_decide:
                for ev in raw.get("evidence") or []:
                    if (ev.get("role_in_discussion") or "") == "decide":
                        if _has_hedge(ev.get("quote", "")):
                            hedge_in_decide = True
                            break
            if hedge_in_decide:
                raw["status"] = "proposal"
                limitations.append(
                    f"M3-B hedge: {raw.get('id')} final→proposal (chứa hedge "
                    f"trong content/quote)"
                )
        # Task: hedge trong evidence → ép TBD owner/due + hint.
        elif rtype == "task":
            evs = raw.get("evidence") or []
            ev_in_hedge = False
            for ev in evs:
                ev_turn = ev.get("turn")
                if isinstance(ev_turn, int) and ev_turn in hedge_turns:
                    ev_in_hedge = True
                    break
                if _has_hedge(ev.get("quote", "")):
                    ev_in_hedge = True
                    break
            if ev_in_hedge:
                old_owner = raw.get("owner", "")
                old_due = raw.get("due", "")
                if old_owner and old_owner != TBD_SENTINEL:
                    raw["owner"] = TBD_SENTINEL
                    raw["owner_source"] = "tbd"
                    if not raw.get("due_hint"):
                        raw["due_hint"] = old_owner
                if old_due and old_due != TBD_SENTINEL:
                    raw["due"] = TBD_SENTINEL
                    raw["due_source"] = "tbd"
                    if not raw.get("due_hint"):
                        raw["due_hint"] = old_due
                limitations.append(
                    f"M3-B hedge: {raw.get('id')} task → owner/due=TBD "
                    f"(câu evidence chứa hedge)"
                )


# ──────────────────────────────────────────────────────────────────────
# M3-D: Task vs Knowledge tách bằng code
# ──────────────────────────────────────────────────────────────────────

KNOWLEDGE_RE = re.compile(
    r"\bquy\s*[ưữ]?[ớo]c\b|\bl[ầa]n\s*sau\b|\bkinh\s*nghi[ệe]m\b|"
    r"\bnguy[êe]n\s*t[ắa]c\b|\bl[ưu]\s*[uyý]\b|\bpolicy\b|"
    r"\bb[àa]i\s*h[ọo]c\b|\bsau\s*n[àa]y\b|\bt[ưu][ơo]ng\s*lai\b",
    re.IGNORECASE,
)

ACTION_VERB_RE = re.compile(
    r"\bg[ửu]i\b|\bl[àa]m\b|\bchu[ầa]n\s*b[ịi]\b|\btri[ểe]n\s*khai\b|"
    r"\breview\b|\bki[ểe]m?\s*tra\b|\bg[oọ]i\b|\bh[ọo]p\s*(?![ơớ]ng\s*l[âa]i)\b|"
    r"\bb[áa]o\s*c[áa]o\b|\bfix\b|\bs[ửu]a\b|\bsetup\b|\bdraft\b|"
    r"\bs[ảa]n\s*xu[ấa]t\b|\bdeploy\b|\btest\b",
    re.IGNORECASE,
)


def _looks_like_knowledge(text: str) -> bool:
    """Match mẫu tri thức/quy ước/lần sau/... — Knowledge không phải Task."""
    if not text:
        return False
    return bool(KNOWLEDGE_RE.search(text))


def _looks_like_action_task(text: str) -> bool:
    """Match động từ hành động cụ thể — Task có thể giao được."""
    if not text:
        return False
    return bool(ACTION_VERB_RE.search(text))


def _task_has_concrete_owner_or_due(raw: dict[str, Any]) -> bool:
    """Task có owner explicit/inferred (≠ TBD) HOẶC due ISO (≠ TBD)."""
    owner = raw.get("owner") or ""
    due = raw.get("due") or ""
    if owner and owner != TBD_SENTINEL:
        return True
    if due and due != TBD_SENTINEL:
        return True
    return False


def _reclassify_knowledge_task(
    items: list[dict[str, Any]], limitations: list[str]
) -> None:
    """M3-D: LLM đặt sai loại → code sửa chéo + ghi vết (in-place).

    Quy tắc:
    - LLM đặt `task` mà KHÔNG có action verb VÀ KHÔNG có owner/due cụ thể
      VÀ content match KNOWLEDGE_RE → đổi sang `knowledge`.
    - LLM đặt `knowledge` mà có action verb + owner/due cụ thể → đổi sang `task`.

    KHÔNG xoá item; chỉ đổi `type` + ghi limitation.
    """
    for raw in items:
        rtype = raw.get("type")
        if rtype == "task":
            what = str(raw.get("what") or "")
            if not _task_has_concrete_owner_or_due(raw) and _looks_like_knowledge(what):
                # Reclassify Task → Knowledge
                raw["type"] = "knowledge"
                # Pop các field không thuộc Knowledge (Task-specific).
                for k in ("what", "owner", "owner_source", "due", "due_source",
                          "due_hint", "link_to_decision"):
                    if k in raw and k != "content":
                        # Knowledge dùng 'content'; nếu what có, copy sang content.
                        if k == "what":
                            raw.setdefault("content", raw.get("what"))
                        raw.pop(k, None)
                # Confidence nhẹ hơn (knowledge thường là nhận định, không hứa hẹn).
                if raw.get("confidence", 0) > 0.85:
                    raw["confidence"] = 0.8
                if "reclassify" not in str(raw.get("confidence_reason", "")):
                    old_reason = raw.get("confidence_reason", "")
                    raw["confidence_reason"] = (
                        f"M3-D reclassify task→knowledge; {old_reason}"
                    ).strip("; ")
                if not raw.get("tags"):
                    raw["tags"] = ["reclassify"]
                limitations.append(
                    f"M3-D: {raw.get('id')} task→knowledge (pattern quy ước/lần sau, "
                    f"không owner/due cụ thể)"
                )
        elif rtype == "knowledge":
            content = str(raw.get("content") or "")
            evidence = raw.get("evidence") or []
            # Lấy text từ evidence nếu content trống.
            ev_text = " ".join(
                (ev.get("quote") or "") for ev in evidence[:1]
            )
            search_text = content or ev_text
            if (
                _looks_like_action_task(search_text)
                and _task_has_concrete_owner_or_due(raw)
            ):
                # Reclassify Knowledge → Task: cần owner/due.
                # Thường Knowledge do LLM đặt sai thiếu các trường task → không
                # tự ép schema. Ở đây ta chỉ GỢI Ý qua limitation (tránh
                # silent-rewrite — R5 + trung thực).
                limitations.append(
                    f"M3-D gợi ý: {raw.get('id')} đang là knowledge nhưng có động từ "
                    f"hành động + owner/due cụ thể → host cân nhắc chuyển thành task "
                    f"(KHÔNG tự đổi để giữ audit)"
                )


# ──────────────────────────────────────────────────────────────────────
# CR-DUE-REV (CR giả định) — Deadline sửa giữa họp
# ──────────────────────────────────────────────────────────────────────

_DUE_HINT_DATE_RE = re.compile(
    r"\b(\d{1,2})\s*[/\-]\s*(\d{1,2})(?:\s*[/\-]\s*(\d{2,4}))?\b"
)


def _apply_due_revision(
    items: list[dict[str, Any]],
    meta: dict[str, Any],
    limitations: list[str],
) -> None:
    """CR-DUE-REV (giả định): deadline sửa giữa họp → lấy lần chốt CUỐI.

    Luật:
      - Nếu task có evidence chứa CÂU SỬA due (vd "dời sang thứ 2 21-10") ở
        turn SAU evidence đầu tiên về task → override due = ISO của câu sửa
        CUỐI CÙNG (lần chốt mới nhất theo thứ tự turn).
      - `due_hint` giữ cả vết cũ→mới (vd "16-10 → 21-10 (revised turn 90)").
      - Nếu evidence quote có hint relative-date parse được → dùng ISO đó.

    Module độc lập: bật/tắt qua cờ ENABLE_DUE_REVISION (mặc định True).
    Khi CR thật tới (multi-topic, export-filter, ...) chỉ thay hàm này.
    """
    meeting_date_iso = meta.get("date", "1970-01-01")
    for raw in items:
        if raw.get("type") != "task":
            continue
        evs = raw.get("evidence") or []
        if len(evs) < 2:
            continue
        # Sắp xếp theo turn tăng dần.
        ordered = sorted(
            [ev for ev in evs if isinstance(ev.get("turn"), int)],
            key=lambda e: e["turn"],
        )
        if len(ordered) < 2:
            continue
        # Tìm evidence SAU first_turn có chứa pattern ngày hoặc keyword sửa.
        # Lấy CÂU SỬA CUỐI CÙNG (max turn) — đây là lần chốt mới nhất.
        candidates: list[tuple[str, int]] = []
        for ev in ordered[1:]:
            quote = (ev.get("quote") or "").lower()
            if (
                _DUE_HINT_DATE_RE.search(quote)
                or "dời" in quote
                or "sửa" in quote
                or "chuyển" in quote
                or "lùi" in quote
                or "revise" in quote
            ):
                candidates.append((ev.get("quote", ""), ev["turn"]))
        if not candidates:
            continue
        # Lấy câu sửa CUỐI (max turn) — thể hiện lần chốt mới nhất.
        revised_quote, revised_turn = max(candidates, key=lambda c: c[1])
        # Parse ISO từ câu sửa. Ưu tiên ngày CỤ THỂ (số/cũ) trong câu trước
        # (relative-date parser match "thứ 2 tuần sau" ngay cả khi câu có cả
        # "21/10" → sai); fallback relative-date nếu không có ngày số.
        iso_new: str | None = None
        m = _DUE_HINT_DATE_RE.search(revised_quote)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = (
                int(m.group(3)) if m.group(3)
                else date.fromisoformat(meeting_date_iso).year
            )
            if len(str(year)) == 2:
                year = 2000 + year
            try:
                iso_new = date(year, month, day).isoformat()
            except ValueError:
                iso_new = None
        if not iso_new:
            from .resolve import parse_relative_date

            iso_new, _ = parse_relative_date(revised_quote, meeting_date_iso)
        if not iso_new:
            continue
        old_due = raw.get("due", "")
        old_hint = raw.get("due_hint")
        # Bảo vệ: không ghi đè due nếu đã ISO + match (không có sửa thật).
        if old_due and old_due != TBD_SENTINEL and old_due == iso_new:
            continue
        # Ghi vết cũ → mới.
        if old_due and old_due != TBD_SENTINEL:
            new_hint = f"{old_due} → {iso_new} (revised turn {revised_turn})"
        else:
            new_hint = f"→ {iso_new} (revised turn {revised_turn})"
        if old_hint:
            raw["due_hint"] = f"{old_hint} | {new_hint}"
        else:
            raw["due_hint"] = new_hint
        raw["due"] = iso_new
        raw["due_source"] = "explicit"
        limitations.append(
            f"CR-DUE-REV: {raw.get('id')} due {old_due or '(none)'} → {iso_new} "
            f"(câu sửa ở turn {revised_turn})"
        )


__all__ = [
    "ACTION_VERB_RE",
    "DECIDE_VERBS",
    "HEDGE_RE",
    "KNOWLEDGE_RE",
    "RETRACT_RE",
    "_RECAP_RE",
    "_apply_decision_gate",
    "_apply_due_revision",
    "_apply_hedge_gate",
    "_has_decide_verb",
    "_has_hedge",
    "_has_retract_signal",
    "_is_recap",
    "_looks_like_action_task",
    "_looks_like_knowledge",
    "_passes_decision_gate",
    "_reclassify_knowledge_task",
    "_task_has_concrete_owner_or_due",
]
