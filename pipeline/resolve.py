"""
resolve.py — Pass-2: trọng tài xuyên chunk + entity-link deterministic.

Triết lý (AGENTS.md §1, taxonomy §6):
- "LLM đề xuất, code kiểm chứng, con người chốt."
- Resolve là deterministic pass: HỮ, sửa quyết định của LLM pass-1 nếu lệch.
- Entity-link ngày/người bằng Python (regex + participants), KHÔNG tin LLM.

Khi nào cần (P2 — bug P1 để lại):
- P1 extract dedup theo `id` XUYÊN CHUNK → giữ bản đầu. Trong tc2: D1 được
  trích ở chunk 0 (đoán sớm @05:46 turn 29) + chunk 1+2 (trích đúng @45:30
  turn 65). Dedup giữ-bản-đầu → mất evidence đúng → D1.final dùng câu chốt
  của chunk 0 (sai).

P2 làm gì (theo kế hoạch `§1 resolve.py`):
1. Within-chunk dedup (giữ bản đầu — đã đã làm trong extract, double-check).
2. Cross-chunk MERGE trùng khít (cùng content+evidence) → 1, ghi `merged_ids`.
3. **Same-id conflict**: cùng id, evidence khác nhau → đa số chunks đồng thuận
   thắng; hòa → evidence có `role_in_discussion='decide'` + ts muộn nhất thắng.
   Bản thua → limitations (audit, KHÔNG xoá hẳn trace).
4. **Nối supersedes xuyên chunk**: proposal ở chunk đầu + final ở chunk cuối
   khác id → link `supersedes`.
5. **Genuine reversal (A→B→A / 2 final cùng chủ đề khác content)**: KHÔNG
   tự chọn → đánh dấu `unresolved_reversal=true` + tạo Open Issue cho host.
6. **Entity-link deterministic** (KHÔNG LLM):
   - Owner → tên trong participants (R1); ngoài → TBD.
   - Due tương đối (`thứ 2..CN`, `tuần sau`, `ngày N/M`, `cuối tháng`) → ISO
     từ `meeting.date`; mơ hồ → TBD + `due_hint`.
7. **LLM pass-2** (optional): dùng `system_resolve.md` qua `llm_fn` mock được;
   khi thiếu env → vẫn chạy deterministic (test/CI không phụ thuộc key).

Output:
- `{"items": list[dict] raw (Pydantic structure OK), "known_limitations": list[str]}`
- Items CHƯA qua verify (chưa áp R5 quote match, R1 owner canonicalize...).
- Verify sẽ làm nốt: enforce TBD canonical, check quote, compute confidence.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .extract import (
    PROMPTS_DIR,
    SYSTEM_PROMPT_FILE as _EXTRACT_PROMPT_FILE,  # noqa: F401  (giữ tương thích)
    fill_meta_placeholders,
    load_prompt,
)
from .schema import Participant, TBD_SENTINEL

logger = logging.getLogger(__name__)

# Prompt pass-2 riêng — không dùng lại system_extract.
RESOLVE_PROMPT_FILE = "system_resolve.md"

# ──────────────────────────────────────────────────────────────────────
# Phụ trợ: build messages cho LLM pass-2 (optional)
# ──────────────────────────────────────────────────────────────────────


def _build_resolve_messages(
    chunk_items: list[list[dict[str, Any]]],
    meta: dict[str, Any],
) -> list[dict[str, str]]:
    """System prompt là `system_resolve.md`; user chứa raw_items xuyên chunk."""
    system = fill_meta_placeholders(load_prompt(RESOLVE_PROMPT_FILE), meta)
    user_lines = [
        f"Meeting id: {meta.get('id', '?')}",
        f"Title: {meta.get('title', '?')}",
        f"Date: {meta.get('date', '?')}",
        "",
        f"Total chunks: {len(chunk_items)}",
        "",
        "RAW ITEMS PER CHUNK (đã dedup trong chunk, CHƯA merge xuyên chunk):",
    ]
    for ci, items in enumerate(chunk_items):
        user_lines.append(f"\n--- chunk {ci} ({len(items)} items) ---")
        for raw in items:
            user_lines.append(json.dumps(raw, ensure_ascii=False))
    user = "\n".join(user_lines)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ──────────────────────────────────────────────────────────────────────
# Deterministic rules
# ──────────────────────────────────────────────────────────────────────


def _norm_text(s: str) -> str:
    """Normalize text cho so sánh — bỏ punctuation + collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def _ev_signature(evidence_list: list[dict[str, Any]]) -> tuple[tuple[str, str, str], ...]:
    """Signature cho evidence — (quote_norm, timestamp, speaker).

    Dùng để phát hiện 'trùng khít' (merge) hoặc 'khác evidence' (same-id conflict).
    """
    sigs: list[tuple[str, str, str]] = []
    for ev in evidence_list or []:
        quote = ev.get("quote", "")
        ts = ev.get("timestamp", "")
        spk = ev.get("speaker", "")
        sigs.append((_norm_text(quote), ts, spk))
    return tuple(sorted(sigs))


def _merge_duplicates(
    chunk_items: list[list[dict[str, Any]]],
    limitations: list[str],
) -> list[dict[str, Any]]:
    """Cross-chunk: gộp các item TRÙNG KHÍT (cùng id + cùng evidence) → 1.

    Khác evidence cùng id → KHÔNG gộp ở đây, để _resolve_same_id_conflict xử.

    Returns:
        list[dict] raw items (1 per id) + đã ghi `merged_ids` cho nhóm >1.
    """
    # Group by id, giữ list các bản (kèm chunk_idx) để audit.
    by_id: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for ci, items in enumerate(chunk_items):
        for raw in items:
            iid = raw.get("id")
            if not isinstance(iid, str) or not iid:
                continue
            by_id.setdefault(iid, []).append((ci, raw))

    kept: list[dict[str, Any]] = []
    for iid, instances in by_id.items():
        if len(instances) == 1:
            kept.append(instances[0][1])
            continue

        # Nhiều bản cùng id → nhóm theo evidence signature.
        # NGOẠI LỆ: evidence rỗng KHÔNG chứng minh được trùng khít
        # (2 item khác nhau đều có thể evidence=[]) → mỗi bản 1 nhóm riêng,
        # để _resolve_same_id_conflict phân xử (arbitrate/rename theo nội dung).
        sig_groups: dict[tuple, list[dict[str, Any]]] = {}
        for _, raw in instances:
            evs = raw.get("evidence", []) or []
            if not evs:
                sig_groups.setdefault(("__no_evidence__", id(raw)), []).append(raw)
                continue
            sig = _ev_signature(evs)
            sig_groups.setdefault(sig, []).append(raw)
        sigs = list(sig_groups.keys())

        if len(sigs) == 1:
            # Tất cả trùng khít → gộp, ghi limitation (audit). KHÔNG thêm field
            # `_merged_from` vì Pydantic Decision model dùng extra=forbid.
            canonical = sig_groups[sigs[0]][0]
            kept.append(canonical)
            chunks_repr = ",".join(f"chunk{c}" for c, _ in instances)
            limitations.append(
                f"merge: id={iid} có {len(instances)} bản trùng khít "
                f"({chunks_repr}) → gộp thành 1 (giữ bản đầu)."
            )
            continue

        # Nhiều evidence signatures khác nhau → để same-id conflict xử.
        # Giữ tất cả tạm, _resolve_same_id_conflict sẽ chọn 1 winner.
        for _, raw in instances:
            kept.append(raw)
    return kept


def _pick_winner(
    instances: list[tuple[int, dict[str, Any]]],
) -> tuple[dict[str, Any], list[tuple[int, dict[str, Any]]]]:
    """Chọn 1 winner từ các bản same-id (instances = (chunk_idx, raw)).

    Quy tắc (taxonomy + plan §1):
    - Majority theo (content + speaker + evidence signature) thắng.
    - Hòa → evidence có role_in_discussion='decide' + ts muộn nhất thắng
      (tc2: bản @45:30 thắng bản @05:46 dù đến sau).
    - Nếu vẫn hòa → bản đầu tiên (deterministic).

    Returns: (winner_raw, losers).
    """
    # 1) Majority
    sig_counter: Counter[tuple] = Counter()
    for _, raw in instances:
        sig = (
            _norm_text(raw.get("content", "")),
            raw.get("evidence", [{}])[0].get("speaker", "") if raw.get("evidence") else "",
            _ev_signature(raw.get("evidence", [])),
        )
        sig_counter[sig] += 1
    top_count = max(sig_counter.values())
    top_sigs = {s for s, c in sig_counter.items() if c == top_count}

    if len(top_sigs) == 1:
        winning_sig = next(iter(top_sigs))
        # Lấy instance đầu có signature đó.
        for ci, raw in instances:
            sig = (
                _norm_text(raw.get("content", "")),
                raw.get("evidence", [{}])[0].get("speaker", "") if raw.get("evidence") else "",
                _ev_signature(raw.get("evidence", [])),
            )
            if sig == winning_sig:
                winners = [
                    (c, r) for c, r in instances
                    if (
                        _norm_text(r.get("content", "")),
                        r.get("evidence", [{}])[0].get("speaker", "") if r.get("evidence") else "",
                        _ev_signature(r.get("evidence", [])),
                    ) == winning_sig
                ]
                losers = [(c, r) for c, r in instances if (c, r) not in winners]
                return raw, losers

    # 2) Hòa → latest 'decide' evidence ts thắng
    def _ts_decide(raw: dict[str, Any]) -> tuple[int, str]:
        # Score: (1 nếu có evidence role=decide, 0 nếu không), ts HH:MM:SS so sánh được.
        evs = raw.get("evidence", []) or []
        has_decide = any(ev.get("role_in_discussion") == "decide" for ev in evs)
        latest_ts = ""
        for ev in evs:
            ts = ev.get("timestamp", "")
            if ts > latest_ts:
                latest_ts = ts
        return (1 if has_decide else 0, latest_ts)

    scored = sorted(
        instances,
        key=lambda cr: _ts_decide(cr[1]),
        reverse=True,
    )
    winner = scored[0]
    losers = scored[1:]
    return winner[1], losers


def _item_text(raw: dict[str, Any]) -> str:
    """Nội dung chính của item (task dùng `what`, còn lại dùng `content`)."""
    if raw.get("type") == "task":
        return str(raw.get("what") or "")
    return str(raw.get("content") or "")


def _sig_tokens(text: str) -> set[str]:
    """Tokens significant (len≥4) để đo overlap — dùng chung cho merge/split."""
    return {t for t in _norm_text(text or "").split() if len(t) >= 4}


def _resolve_same_id_conflict(
    items: list[dict[str, Any]],
    chunk_items: list[dict[str, Any]],
    limitations: list[str],
) -> list[dict[str, Any]]:
    """Cùng id + khác evidence → majority / latest-decide → 1 winner.

    NGOẠI LỆ (live tc4): model tái dùng id chung chung (T1..T8) cho TASK KHÁC
    NHAU ở mỗi chunk. Cùng id + nội dung KHÁC NHAU ở task (và các loại trừ
    decision) = id collision, KHÔNG phải conflict → tách cluster theo nội
    dung, cluster sau đổi id mới (giữ vết limitation). Decision giữ nguyên
    (cùng id = cùng quyết định → trọng tài).
    Loser ghi limitations (audit, KHÔNG xoá — cần trace).
    Returns list items sau resolve.
    """
    # Index chunk_idx cho từng item (best-effort: match content+id vào chunk_items)
    by_id: dict[str, list[dict[str, Any]]] = {}
    for raw in items:
        by_id.setdefault(str(raw.get("id", "")), []).append(raw)

    used_ids: set[str] = set(by_id.keys())
    out: list[dict[str, Any]] = []
    for iid, group in by_id.items():
        if len(group) == 1:
            out.append(group[0])
            continue

        first_type = group[0].get("type")
        if first_type != "decision":
            # Cluster theo nội dung: cùng nội dung → arbitrate trong cluster;
            # khác nội dung → id collision → cluster sau rename id mới.
            clusters: list[list[dict[str, Any]]] = []
            for raw in group:
                placed = False
                for cl in clusters:
                    other = _item_text(cl[0])
                    mine = _item_text(raw)
                    # Text ít hơn 2 tokens significant thì không đủ phân biệt
                    # trùng/khác → KHÔNG tách (trọng tài như cũ; mất task thật
                    # tệ hơn trùng task).
                    if min(len(_sig_tokens(mine)), len(_sig_tokens(other))) < 2:
                        cl.append(raw)
                        placed = True
                        break
                    if _contents_match(mine, other):
                        cl.append(raw)
                        placed = True
                        break
                if not placed:
                    clusters.append([raw])
            if len(clusters) > 1:
                for n, cl in enumerate(clusters):
                    if n > 0:
                        new_id = f"{iid}_{n + 1}"
                        k = 2
                        while new_id in used_ids:
                            k += 1
                            new_id = f"{iid}_{k}"
                        used_ids.add(new_id)
                        for raw in cl:
                            limitations.append(
                                f"id collision: {iid} ở chunk khác là task khác "
                                f"({str(_item_text(raw))[:50]!r}) → đổi id {new_id}"
                            )
                            raw["id"] = new_id
                    instances = [(c, r) for c, r in
                                 [(_find_chunk_idx(raw, chunk_items), raw) for raw in cl]]
                    winner, losers = _pick_winner(instances)
                    out.append(winner)
                    if losers:
                        limitations.append(
                            f"same-id conflict id={winner.get('id')}: "
                            f"giữ 1 bản, bỏ {len(losers)} bản trùng nội dung"
                        )
                continue

        # Gán chunk_idx cho từng instance để majority dựa trên xuyên chunk.
        instances: list[tuple[int, dict[str, Any]]] = []
        for raw in group:
            ci = _find_chunk_idx(raw, chunk_items)
            instances.append((ci, raw))

        winner, losers = _pick_winner(instances)
        out.append(winner)
        if losers:
            winner_ts = _winner_ts(winner)
            loser_summaries = []
            for ci, lr in losers:
                ts = _winner_ts(lr)
                role = _winner_role(lr)
                loser_summaries.append(f"chunk{ci}@{ts}/{role}")
            limitations.append(
                f"same-id conflict id={iid}: chọn bản @{winner_ts} "
                f"({len(instances) - len(losers)} winner-majority hoặc latest-decide). "
                f"Bản thua: {loser_summaries} — giữ không xóa (R4 audit)."
            )
    return out


def _demote_finals_without_decide(
    items: list[dict[str, Any]], limitations: list[str]
) -> None:
    """Hạ final không có evidence chốt THẬT → proposal (in-place).

    Luật business (glossary "Chốt vs nói chơi"): chốt cần câu chốt rõ.
    Evidence role=decide nhưng quote là TƯỜNG THUẬT ("Em note lại: chốt...",
    live tc1 D0/Nam) cũng không tính — chỉ ghi chú/đồng thuận lại ≠ chốt.
    Giữ làm proposal để audit, không xóa.
    """
    for raw in items:
        if raw.get("type") != "decision" or raw.get("status") != "final":
            continue
        real_decide = any(
            (ev.get("role_in_discussion") or "") == "decide"
            and not _is_recap(ev.get("quote", ""))
            for ev in (raw.get("evidence") or [])
        )
        if not real_decide:
            raw["status"] = "proposal"
            limitations.append(
                f"demote: {raw.get('id')} final→proposal (không có evidence "
                f"chốt thật — chỉ là ghi chú/tường thuật lại, không phải chốt)"
            )


def _contents_match(a: str, b: str, min_len: int = 12) -> bool:
    """Hai content có phải cùng một quyết định? (normalized containment).

    Chỉ containment — KHÔNG dùng token-overlap (thử nghiệm cho thấy overlap
    gộp nhầm 2 chốt thật sự khác nhau khi cùng scaffolding câu chữ).
    Diễn đạt lại nhưng cùng ý mà không chứa nhau → để host phân xử ở review
    (an toàn hơn gộp nhầm).
    """
    na, nb = _norm_text(a or ""), _norm_text(b or "")
    if len(na) < min_len or len(nb) < min_len:
        return False
    return na in nb or nb in na


# Câu tường thuật lại (recap), KHÔNG phải câu chốt — dù model có gán role=decide.
_RECAP_RE = re.compile(
    r"note lại|ghi lại|tóm lại|recap|tổng hợp lại|nhắc lại|ghi chép|tóm tắt lại"
)


def _is_recap(quote: str) -> bool:
    return bool(_RECAP_RE.search(quote or ""))


def _merge_same_content_finals(
    items: list[dict[str, Any]], limitations: list[str]
) -> None:
    """Gộp finals CÙNG nội dung khác id (in-place) — vd model đặt D0 và D1
    cho cùng một chốt ở 2 chunk. Winner = evidence decide muộn nhất;
    union evidence + supersedes (bỏ self-ref); quyết định khác nội dung
    KHÔNG đụng (để reversal detection xử — R4).
    """
    finals = [it for it in items
              if it.get("type") == "decision" and it.get("status") == "final"]
    merged_ids: set[str] = set()
    for i, a in enumerate(finals):
        if a.get("id") in merged_ids:
            continue
        group = [a]
        for b in finals[i + 1 :]:
            if b.get("id") in merged_ids:
                continue
            if _contents_match(a.get("content", ""), b.get("content", "")):
                group.append(b)
                merged_ids.add(b.get("id"))
        if len(group) < 2:
            continue

        def _decide_ts(raw: dict[str, Any]) -> str:
            # Chỉ tính evidence decide KHÔNG phải recap ("Em note lại: chốt..."
            # là tường thuật, không phải chốt — live tc1 D0/Nam thua D1/Lan).
            ts = ""
            for ev in raw.get("evidence") or []:
                if ev.get("role_in_discussion") == "decide" and not _is_recap(
                    ev.get("quote", "")
                ):
                    if ev.get("timestamp", "") > ts:
                        ts = ev["timestamp"]
            return ts

        winner = max(group, key=lambda r: (_decide_ts(r), str(r.get("id"))))
        # Union evidence (theo signature) + supersedes (bỏ self-ref).
        seen_sigs: set = set()
        merged_ev: list[dict[str, Any]] = []
        for raw in group:
            for ev in raw.get("evidence") or []:
                sig = (_norm_text(ev.get("quote", "")), ev.get("timestamp", ""),
                       ev.get("speaker", ""))
                if sig not in seen_sigs:
                    seen_sigs.add(sig)
                    merged_ev.append(ev)
        sup: list[str] = []
        for raw in group:
            for s in raw.get("supersedes") or []:
                if s not in sup:
                    sup.append(s)
        winner["evidence"] = merged_ev
        winner["supersedes"] = [s for s in sup if s != winner.get("id")]
        losers = [r.get("id") for r in group if r is not winner]
        limitations.append(
            f"merge: finals cùng nội dung {losers} → {winner.get('id')} "
            f"(decide muộn nhất {_decide_ts(winner) or '??'} thắng)"
        )
        merged_ids.add(winner.get("id"))
        for r in group:
            if r is not winner:
                items.remove(r)


def _find_chunk_idx(
    raw: dict[str, Any], chunk_items: list[list[dict[str, Any]]]
) -> int:
    """Best-effort: tìm chunk_idx cho 1 raw item (so id + content đầu)."""
    iid = str(raw.get("id", ""))
    content_head = _norm_text(raw.get("content", ""))[:40]
    for ci, items in enumerate(chunk_items):
        for r in items:
            if str(r.get("id", "")) != iid:
                continue
            r_head = _norm_text(r.get("content", ""))[:40]
            if r_head == content_head:
                return ci
    return -1


def _winner_ts(raw: dict[str, Any]) -> str:
    evs = raw.get("evidence", []) or []
    ts = ""
    for ev in evs:
        t = ev.get("timestamp", "")
        if t > ts:
            ts = t
    return ts or "??"


def _winner_role(raw: dict[str, Any]) -> str:
    evs = raw.get("evidence", []) or []
    for ev in evs:
        r = ev.get("role_in_discussion", "")
        if r:
            return r
    return "info"


def _link_supersedes_xuyen_chunk(
    items: list[dict[str, Any]],
    limitations: list[str],
) -> None:
    """Proposal ở chunk sớm + Final ở chunk muộn, khác id → link supersedes.

    Quy tắc (taxonomy §6 + plan §1):
    - Decision status=final mà `supersedes=[]` VÀ có Decision khác status=discarded
      cùng chủ đề (content gần giống) → bổ sung `supersedes=[discarded.id]`.

    Heuristic 'cùng chủ đề' (tiếng Việt, đã normalize bỏ punctuation):
    - Share ≥ 1 token dài ≥ 5 char (vd 'phương' trong 'phương án A' vs
      'phương án B') HOẶC
    - Share ≥ 2 token ≥ 3 char.
    """
    decisions = [r for r in items if r.get("type") == "decision"]
    finals = [d for d in decisions if d.get("status") == "final"]
    discardeds = [d for d in decisions if d.get("status") == "discarded"]

    for fin in finals:
        if fin.get("supersedes"):
            continue  # đã link rồi — không chồng
        fin_content_norm = _norm_text(fin.get("content", ""))
        fin_tokens_5 = {t for t in fin_content_norm.split() if len(t) >= 5}
        fin_tokens_3 = {t for t in fin_content_norm.split() if len(t) >= 3}
        candidates: list[dict[str, Any]] = []
        for dis in discardeds:
            dis_content_norm = _norm_text(dis.get("content", ""))
            dis_tokens_5 = {t for t in dis_content_norm.split() if len(t) >= 5}
            dis_tokens_3 = {t for t in dis_content_norm.split() if len(t) >= 3}
            if (
                len(fin_tokens_5 & dis_tokens_5) >= 1
                or len(fin_tokens_3 & dis_tokens_3) >= 2
            ):
                candidates.append(dis)
        if candidates:
            fin["supersedes"] = [c.get("id", "?") for c in candidates]
            limitations.append(
                f"link_supersedes: {fin.get('id')} ← {fin['supersedes']} "
                f"(heuristic share-token, xuyên chunk)."
            )


def _detect_unresolved_reversal(
    items: list[dict[str, Any]],
    limitations: list[str],
) -> list[dict[str, Any]]:
    """Phát hiện A→B→A hoặc 2 final cùng chủ đề khác content.

    KHÔNG tự chọn (R4 + taxonomy §6) — đánh `unresolved_reversal=true` + tạo
    Open Issue nhờ host.

    Heuristic (3 luật — lỏng để không miss match CÙNG CHỦ ĐỀ):
    - R1: 1 decision có ≥ 2 evidence có role=decide với quote KHÁC NHAU
      (A→B hoặc A→B→A) → reversal (ngay cả khi chỉ 1 final).
    - R2: ≥ 2 final khác id mà share ≥ 2 token (≥3 chars) → reversal.
    - R3: ≥ 2 final cùng chủ đề giống hệt → cũng reversal (để host xác nhận).
    """
    finals = [r for r in items if r.get("type") == "decision" and r.get("status") == "final"]
    flagged: set[str] = set()

    # R1: 1 decision có ≥ 3 evidence role=decide với quote khác nhau → reversal.
    # Lý do: 2 decide cùng chiều là bình thường (host restate decision).
    # 3+ decide với A→B→A là reversal thật. Heuristic dựa trên việc có
    # ít nhất 1 cặp KHÔNG chia sẻ token nào (≥3 char, trừ filler).
    _FILLER = {
        "nhé", "nha", "nhỉ", "ạ", "vậy", "thế", "rồi", "ok", "thôi",
        "đấy", "đó", "đi", "lại", "à", "ừ", "dạ", "là", "có", "không",
        "mình", "em", "anh", "chị", "ông", "bà",
    }

    def _sig_tokens_no_filler(q: str) -> set[str]:
        return {
            t for t in _norm_text(q).split()
            if len(t) >= 3 and t not in _FILLER
        }

    for f in finals:
        evs = f.get("evidence", []) or []
        decide_quotes = [
            _norm_text(ev.get("quote", ""))
            for ev in evs
            if ev.get("role_in_discussion") == "decide"
        ]
        decide_quotes = [q for q in decide_quotes if q]
        if len(decide_quotes) < 3:
            continue
        # ≥ 3 decide → check pattern A→B→A: có cả cặp SHARED và cặp NO-SHARED
        # (A→B→A: q1 q3 share, q1 q2 khác) → reversal.
        toks = [_sig_tokens_no_filler(q) for q in decide_quotes]
        has_shared_pair = False
        has_no_shared_pair = False
        for i in range(len(toks)):
            for j in range(i + 1, len(toks)):
                if toks[i] & toks[j]:
                    has_shared_pair = True
                else:
                    has_no_shared_pair = True
        if has_shared_pair and has_no_shared_pair:
            flagged.add(str(f.get("id", "?")))

    # R2 + R3: ≥ 2 final khác id mà share token chính → reversal
    def _sig(d: dict[str, Any]) -> frozenset[str]:
        toks = _norm_text(d.get("content", "")).split()
        return frozenset(t for t in toks if len(t) >= 5)

    if len(finals) >= 2:
        for i, fa in enumerate(finals):
            for fb in finals[i + 1:]:
                sia, sib = _sig(fa), _sig(fb)
                # Share ≥ 1 token ≥ 5 char (vd 'Spring' giữa 2 final) → reversal.
                if sia and sib and len(sia & sib) >= 1:
                    flagged.add(str(fa.get("id", "?")))
                    flagged.add(str(fb.get("id", "?")))

    if not flagged:
        return items

    # Đánh cờ trên TỪNG final liên quan.
    for d in items:
        if d.get("type") == "decision" and d.get("id") in flagged:
            d["unresolved_reversal"] = True

    # Tạo Open Issue cho host (audit + UI hiển thị).
    issue_id = "O_REV"
    n = 1
    while any(it.get("id") == f"{issue_id}_{n}" for it in items):
        n += 1
    issue_id = f"{issue_id}_{n}"
    items.append(
        {
            "id": issue_id,
            "type": "open_issue",
            "content": (
                f"Phát hiện mâu thuẫn / đảo chiều giữa các Decision final: "
                f"{', '.join(sorted(flagged))}. Resolve KHÔNG tự chọn "
                f"(R4 — taxonomy §6). Cần host quyết định cuối cùng."
            ),
            "next_step": (
                "Host mở transcript gốc tại các timestamp trong evidence, "
                "xác định final đúng, sửa các Decision còn lại về 'discarded'."
            ),
            "next_step_owner": TBD_SENTINEL,
            "confidence": 0.4,
            "confidence_reason": (
                "resolve phát hiện unresolved_reversal — để host xử lý "
                "(system_generated-like, evidence minh hoạ R4)."
            ),
            "evidence": [],  # không trích từ transcript — audit marker
            "system_generated": True,
        }
    )
    limitations.append(
        f"unresolved_reversal: {sorted(flagged)} — flagged + Open Issue "
        f"{issue_id} (host xử lý, R4)."
    )
    return items


# ──────────────────────────────────────────────────────────────────────
# Entity-link deterministic (KHÔNG LLM)
# ──────────────────────────────────────────────────────────────────────


_VN_DOW = {
    "thứ 2": 0, "thứ hai": 0,
    "thứ 3": 1, "thứ ba": 1,
    "thứ 4": 2, "thứ tư": 2,
    "thứ 5": 3, "thứ năm": 3,
    "thứ 6": 4, "thứ sáu": 4,
    "thứ 7": 5, "thứ bảy": 5,
    "chủ nhật": 6, "cn": 6, "chủ nhật": 6,
}
_DOW_RE = re.compile(
    r"thứ\s*(2|hai|3|ba|4|tư|5|năm|6|sáu|7|bảy)|"
    r"chủ\s*nhật|\bcn\b",
    re.IGNORECASE,
)
_TUAN_SAU_RE = re.compile(r"tuần\s*sau", re.IGNORECASE)
_CUOI_THANG_RE = re.compile(r"cuối\s*tháng|cuối\s*tháng\s*này", re.IGNORECASE)
_NGAY_RE = re.compile(r"ngày\s+(\d{1,2})\s*[/\-]\s*(\d{1,2})(?:\s*[/\-]\s*(\d{2,4}))?")
_DAYS_RE = re.compile(r"sau\s+(\d+)\s*ngày|trong\s+(\d+)\s*ngày", re.IGNORECASE)
_HINT_RE = re.compile(
    r"sớm|gấp|asap|ngay|khi\s*nào\s*xong|sớm\s*nhé",
    re.IGNORECASE,
)


def _next_weekday(base: date, target_dow: int) -> date:
    """Tính ngày thứ target_dow GẦN NHẤT trong tương lai (>= base+1).

    Python weekday(): Mon=0..Sun=6.
    Nếu hôm nay là target_dow → trả base + 7 (tuần SAU, không phải hôm nay).
    """
    delta = (target_dow - base.weekday()) % 7
    if delta == 0:
        delta = 7
    return base + timedelta(days=delta)


def parse_relative_date(
    hint: str,
    base_date_iso: str,
) -> tuple[str | None, str]:
    """Parse 'thứ 2', 'tuần sau', 'ngày 5/11', 'cuối tháng' → ISO YYYY-MM-DD.

    Returns: (iso_or_None, due_source) trong đó:
        - iso_or_None = ISO date hoặc None (không parse được)
        - due_source = 'inferred' nếu parse OK, 'tbd' nếu None.
    """
    if not hint:
        return None, "tbd"
    base = date.fromisoformat(base_date_iso)

    m = _DOW_RE.search(hint)
    if m:
        # Tìm token chính xác
        for key, dow in _VN_DOW.items():
            if re.search(rf"\b{re.escape(key)}\b", hint, re.IGNORECASE):
                target = _next_weekday(base, dow)
                return target.isoformat(), "inferred"

    if _TUAN_SAU_RE.search(hint):
        # 'tuần sau' = thứ 2 tuần kế tiếp (closest next Monday).
        # Nếu hôm nay là thứ 2 → tuần sau = thứ 2 tuần kế (= +7).
        # Nếu hôm nay là thứ khác → thứ 2 gần nhất (= 1..6 ngày).
        days_to_next_mon = (7 - base.weekday()) % 7
        if days_to_next_mon == 0:
            days_to_next_mon = 7
        target = base + timedelta(days=days_to_next_mon)
        return target.isoformat(), "inferred"

    if _CUOI_THANG_RE.search(hint):
        # Cuối tháng = ngày cuối của tháng hiện tại
        if base.month == 12:
            end = date(base.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(base.year, base.month + 1, 1) - timedelta(days=1)
        return end.isoformat(), "inferred"

    m = _NGAY_RE.search(hint)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = base.year
        if m.group(3):
            ys = m.group(3)
            year = int(ys) if len(ys) == 4 else 2000 + int(ys)
        try:
            target = date(year, month, day)
            return target.isoformat(), "inferred"
        except ValueError:
            return None, "tbd"

    m = _DAYS_RE.search(hint)
    if m:
        n = int(m.group(1) or m.group(2))
        return (base + timedelta(days=n)).isoformat(), "inferred"

    return None, "tbd"


def _entity_link_due(
    items: list[dict[str, Any]],
    meeting_date_iso: str,
    limitations: list[str],
) -> None:
    """Resolve due tương đối trong Task → ISO (R2) + kiểm tra chéo due model đã cho.

    3 việc (đều deterministic, đều ghi limitation để audit):
    1. due tương đối ("thứ 6 tuần này") → ISO từ meeting.date, giữ chữ gốc vào due_hint.
    2. due đã ISO nhưng due_hint còn pattern tương đối → recompute; khác thì OVERRIDE
       (model local hay tính nhầm thứ→ngày, vd "thứ 4 tuần sau" ra 10-29 thay vì 10-21).
    3. due ISO trước meeting.date → bất khả thi → TBD + limitation.
    """
    for it in items:
        if it.get("type") != "task":
            continue
        due = it.get("due", "")
        if not due:
            continue
        if _is_iso_like(due):
            hint = (it.get("due_hint") or "").strip()
            if hint and hint.upper() != "TBD":
                iso2, _ = parse_relative_date(hint, meeting_date_iso)
                if iso2 and iso2 != due:
                    limitations.append(
                        f"due model {due} != deterministic {iso2} từ hint "
                        f"{hint!r} → dùng {iso2} (item {it.get('id')})"
                    )
                    it["due"] = iso2
                    it["due_source"] = "inferred"
                    due = iso2
            if due < meeting_date_iso:
                # Due trước ngày họp = bất khả thi (model bịa/nhầm năm).
                limitations.append(
                    f"due {due} trước meeting.date {meeting_date_iso} → TBD "
                    f"(item {it.get('id')})"
                )
                it["due"] = "TBD"
                it["due_source"] = "tbd"
                if not it.get("due_hint"):
                    it["due_hint"] = due
            continue
        # Không phải ISO + không phải TBD → thử parse due_hint hoặc due_hint
        # (LLM có thể ghi due='thứ 6 tuần sau' nhưng cũng có thể để TBD + hint).
        hint_text = it.get("due_hint") or due
        if _HINT_RE.search(due):
            # 'sớm nhé' / 'ASAP' → TBD + giữ hint gốc (taxonomy §5 R2).
            it["due"] = "TBD"
            it["due_source"] = "tbd"
            if not it.get("due_hint"):
                it["due_hint"] = due
            continue

        iso, src = parse_relative_date(hint_text, meeting_date_iso)
        if iso:
            if not it.get("due_hint"):
                # Giữ chữ gốc để audit (vd "thứ 6 tuần này" → ISO + hint gốc).
                it["due_hint"] = due
            it["due"] = iso
            it["due_source"] = src
        # else: giữ nguyên TBD + hint (R2)


def _is_iso_like(s: str) -> bool:
    """Check YYYY-MM-DD format."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", s))


def _entity_link_owner(
    items: list[dict[str, Any]],
    participants: list[Participant],
    limitations: list[str],
) -> None:
    """Canonicalize owner từ 'em/anh/chị Tên' hoặc Tên trong evidence text → name.

    R1 (taxonomy §6): chỉ name + aliases trong participants mới OK.
    Ngoài → TBD + source=tbd.
    Quy định từ verify.canonicalize_owner (P1) đã enforce; resolve chỉ chuẩn
    hoá trước cho LLM pass-2 nếu có.
    """
    # Hiện không đụng owner đã canonicalize — để verify ép cuối.
    # Function kept cho symmetry + để LLM pass-2 hoặc post-process dùng nếu cần.
    return


# ──────────────────────────────────────────────────────────────────────
# Main: resolve
# ──────────────────────────────────────────────────────────────────────


def resolve(
    meta: dict[str, Any],
    chunk_items: list[list[dict[str, Any]]],
    *,
    llm_fn: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Trọng tài xuyên chunk + entity-link deterministic.

    Args:
        meta: meeting metadata (id, title, date, participants, glossary).
        chunk_items: list[list[dict]] raw items PER CHUNK (output `chunk_items`
                     của extract). Mỗi phần tử = list raw dicts của chunk đó,
                     đã dedup TRONG chunk.
        llm_fn: optional override cho LLM pass-2 call. Signature: (messages) -> str.
                None → chỉ chạy deterministic rules (đủ cho CI/test).

    Returns:
        dict {
          "items": list[dict] raw items (Pydantic structure OK, chưa verify R1/R2/R5),
          "known_limitations": list[str] — mọi quyết định của resolve
                                 (merge, conflict, reversal, entity-link fail).
        }

    Raises:
        RuntimeError: nếu LLM pass-2 được yêu cầu (llm_fn != None) mà lỗi.
                      Khi llm_fn=None → KHÔNG gọi LLM, không raise.
    """
    limitations: list[str] = []

    # Bước 1: merge duplicates chỉ same-id + cùng evidence (cross-chunk)
    # → items_after_merge.
    merged = _merge_duplicates(chunk_items, limitations)

    # Bước 2: same-id conflict — chọn winner, loser → limitations
    items_after_conflict = _resolve_same_id_conflict(merged, chunk_items, limitations)

    # Bước 2b: hạ final không có evidence decide nào → proposal (glossary
    # "Chốt vs nói chơi": ghi chú/đồng thuận lại ≠ chốt).
    _demote_finals_without_decide(items_after_conflict, limitations)

    # Bước 2c: gộp finals CÙNG nội dung khác id (model đặt D0/D1 cho cùng 1 chốt).
    # Khác nội dung thì giữ nguyên để reversal detection xử (R4).
    _merge_same_content_finals(items_after_conflict, limitations)

    # Bước 3: nối supersedes xuyên chunk (proposal early + final late, khác id).
    _link_supersedes_xuyen_chunk(items_after_conflict, limitations)

    # Bước 4: phát hiện A→B→A / 2 final cùng chủ đề → unresolved_reversal.
    items_after_reversal = _detect_unresolved_reversal(
        items_after_conflict, limitations
    )

    # Bước 5: entity-link deterministic (due R2).
    meeting_date_iso = meta.get("date", "1970-01-01")
    _entity_link_due(items_after_reversal, meeting_date_iso, limitations)

    # Bước 5b: gộp task trùng khác id (model local hay tách đôi 1 việc:
    # "giao" + "nhận" thành 2 task). Cùng owner + cùng due ISO + overlap
    # what → giữ bản đầu, ghi limitation (P4 live tc4: T1/T6, T3/T5).
    _merge_duplicate_tasks(items_after_reversal, limitations)

    # Bước 6: optional LLM pass-2 (mock được qua llm_fn).
    # Hiện tại LLM pass-2 chỉ dùng khi llm_fn != None; deterministic đã cover
    # P2 gate. _try_parse_items re-used từ extract (chịu think-tag/fence).
    if llm_fn is not None:
        try:
            from .extract import _try_parse_items
            messages = _build_resolve_messages(chunk_items, meta)
            content = llm_fn(messages)
            llm_items, err = _try_parse_items(content)
            if llm_items is None:
                limitations.append(
                    f"resolve LLM pass-2: parse fail ({err}); dùng deterministic."
                )
            else:
                # Merge LLM hints — deterministic vẫn authoritative cho id,
                # conflict, reversal. LLM có thể bổ sung role_in_discussion /
                # chuẩn hoá evidence.
                _apply_llm_hints(items_after_reversal, llm_items, limitations)
        except Exception as e:
            limitations.append(f"resolve LLM pass-2 lỗi: {e}; dùng deterministic.")

    return {
        "items": items_after_reversal,
        "known_limitations": limitations,
    }


def _what_tokens(what: str) -> set[str]:
    """Tokens significant của what (lowercase, len≥4, unicode-aware)."""
    return {t for t in re.findall(r"[a-z0-9à-ỹ]+", (what or "").lower()) if len(t) >= 4}


def _merge_duplicate_tasks(
    items: list[dict[str, Any]], limitations: list[str]
) -> None:
    """Gộp task trùng khác id (in-place).

    Điều kiện (cả 3): cùng owner (non-TBD) + cùng due ISO (non-TBD) +
    ≥2 shared tokens (len≥4) trong `what`. Giữ bản đầu, ghi limitation.
    Không đụng task TBD (thiếu thông tin để kết luận trùng).
    """
    tasks = [it for it in items if it.get("type") == "task"]
    drop_ids: set[str] = set()
    for i, a in enumerate(tasks):
        if a.get("id") in drop_ids:
            continue
        ta = _what_tokens(a.get("what", ""))
        for b in tasks[i + 1 :]:
            if b.get("id") in drop_ids:
                continue
            owner_a, owner_b = a.get("owner"), b.get("owner")
            due_a, due_b = a.get("due"), b.get("due")
            if not owner_a or owner_a == "TBD" or owner_a != owner_b:
                continue
            if not due_a or due_a == "TBD" or due_a != due_b:
                continue
            shared = ta & _what_tokens(b.get("what", ""))
            if len(shared) >= 2:
                drop_ids.add(b.get("id"))
                # Union trường bổ sung từ bản thua (hint/link/evidence) —
                # bản giữ thiếu gì thì lấy đó, confidence giữ nguyên bản giữ.
                if not a.get("due_hint") and b.get("due_hint"):
                    a["due_hint"] = b["due_hint"]
                if not a.get("link_to_decision") and b.get("link_to_decision"):
                    a["link_to_decision"] = b["link_to_decision"]
                seen_ev = {(e.get("timestamp"), e.get("quote"))
                           for e in (a.get("evidence") or [])}
                for e in b.get("evidence") or []:
                    if (e.get("timestamp"), e.get("quote")) not in seen_ev:
                        a.setdefault("evidence", []).append(e)
                limitations.append(
                    f"merge: task {b.get('id')} trùng {a.get('id')} "
                    f"(owner+due+overlap {sorted(shared)}) → gộp, giữ {a.get('id')}"
                )
    if drop_ids:
        items[:] = [it for it in items if it.get("id") not in drop_ids]


def _apply_llm_hints(
    items: list[dict[str, Any]],
    llm_items: list[dict[str, Any]],
    limitations: list[str],
) -> None:
    """Áp LLM hints (chỉ role_in_discussion + evidence bổ sung) — KHÔNG override id/conflict.

    LLM pass-2 có thể:
    - Gán role_in_discussion còn sót (verify đã ép default 'info' → LLM có thể sửa).
    - Bổ sung evidence (vd thêm câu xác nhận) — append nếu signature mới.
    KHÔNG được:
    - Đổi id (đã do majority/conflict arbitration).
    - Đổi status final/discarded/proposal.
    - Đổi supersedes (đã link).
    - Đổi content (taxonomy: quote nguyên văn).
    """
    by_id: dict[str, dict[str, Any]] = {str(i.get("id", "")): i for i in items}
    for hint in llm_items:
        iid = str(hint.get("id", ""))
        target = by_id.get(iid)
        if not target:
            continue  # LLM bịa id mới → bỏ
        # Áp role_in_discussion cho evidence có cùng quote
        target_evs = target.get("evidence", []) or []
        for h_ev in hint.get("evidence", []) or []:
            h_quote = (h_ev.get("quote") or "").strip()
            h_role = h_ev.get("role_in_discussion")
            if not h_quote or not h_role:
                continue
            matched = False
            for tev in target_evs:
                if (tev.get("quote") or "").strip() == h_quote:
                    if tev.get("role_in_discussion") in (None, "info") and h_role in {
                        "propose", "object", "decide", "confirm"
                    }:
                        tev["role_in_discussion"] = h_role
                        matched = True
                        break
            if not matched:
                # Append evidence mới (verify sẽ check quote).
                target_evs.append(h_ev)
                target["evidence"] = target_evs
    # Ghi limitation khi có ít nhất 1 hint
    if any(h.get("id") in by_id for h in llm_items):
        limitations.append(
            f"resolve LLM pass-2: applied hints cho {sum(1 for h in llm_items if h.get('id') in by_id)} items."
        )


__all__ = [
    "RESOLVE_PROMPT_FILE",
    "parse_relative_date",
    "resolve",
]