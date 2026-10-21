"""
eval/runner.py — Chạy eval 5 ca tc1..tc5 → so với data/golden/ → JSON + bảng tóm tắt.

Theo `docs/spec/eval-plan.md` + `docs/spec/acceptance.md` (#2 tc2 là kill-criterion).

Chế độ:
- fixture (default): mock LLM từ data/fixtures/ (deterministic, CI-friendly).
  tc2 dùng fixture multichunk (3 responses cho chunk_size=40/overlap=10).
- live (--live): gọi LLM thật qua .env (Ollama/hosted).

Chạy:  python -m eval.runner [--live] [--cases tc1,tc2] [--chunk-size 40]
        python -m pipeline.cli eval [--live]   (wrapper)
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline.extract import extract
from pipeline.ingest import parse_transcript
from pipeline.resolve import resolve
from pipeline.schema import Meeting, Participant
from pipeline.verify import badge_for, verify_state

CASES = ["tc1", "tc2", "tc3", "tc4", "tc5"]

# Fixture mock cho từng case ở chunk_size=40/overlap=10 (khớp số chunk thực tế).
_FIXTURE_FOR = {
    "tc1": "data/fixtures/tc1_llm.json",
    "tc2": "data/fixtures/tc2_llm_multichunk.json",
    "tc3": "data/fixtures/tc3_llm.json",
    "tc4": "data/fixtures/tc4_llm.json",
    "tc5": "data/fixtures/tc5_llm.json",
}

# Optional M3 transcript: ca dài 110 turns cho BEFORE/AFTER Mission 3.
# Theo PLAN_M3 §4.4: tc6 test 2 final ca đạt chain, 0 false final từ chốt giả,
# 1 knowledge đúng loại, due revision đúng.
_M3_CASES = ["tc6"]
_M3_FIXTURE_FOR = {
    "tc6": "data/fixtures/tc6_llm.json",
}

ALL_CASES = CASES + _M3_CASES
ALL_FIXTURE_FOR = {**_FIXTURE_FOR, **_M3_FIXTURE_FOR}


def _norm(s: str) -> str:
    """Normalize để so sánh chứa đựng: lowercase, bỏ dấu câu/khoảng trắng dư."""
    s = unicodedata.normalize("NFC", s or "").lower()
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
    return " ".join(s.split())


def _contains(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _make_fixture_llm(fixture_path: Path):
    """Mock LLM: trả responses tuần tự theo chunk (hết thì lặp lại cuối)."""
    data = _load_json(fixture_path)
    if not isinstance(data, list) or not data:
        raise ValueError(f"fixture phải là JSON array không rỗng: {fixture_path}")
    responses = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in data]
    idx = {"n": 0}

    def llm_fn(messages):
        i = idx["n"]
        idx["n"] = i + 1
        return responses[i] if i < len(responses) else responses[-1]

    return llm_fn


def run_case(
    tc_id: str,
    *,
    live: bool = False,
    chunk_size: int = 40,
    overlap: int = 10,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Chạy full pipeline ingest→extract→resolve→verify cho 1 case (in-memory)."""
    data_dir = root / "data"
    meta = _load_json(data_dir / "meta" / f"{tc_id}_meta.json")
    transcript = next(
        (data_dir / "transcripts").glob(f"{tc_id}*.txt"),
        next((data_dir / "transcripts").glob(f"{tc_id}*.srt"), None),
    )
    if transcript is None:
        raise FileNotFoundError(f"transcript for {tc_id} not found")

    turns, ingest_lims = parse_transcript(transcript)
    llm_fn = None
    if not live:
        # Chọn fixture từ M3 set nếu có, không thì M2 set.
        fixture_path = ALL_FIXTURE_FOR.get(tc_id) or _FIXTURE_FOR.get(tc_id)
        if fixture_path is None:
            raise FileNotFoundError(f"no fixture for {tc_id}")
        llm_fn = _make_fixture_llm(root / fixture_path)

    extraction = extract(
        meta, turns, log_path=None, llm_fn=llm_fn,
        chunk_size=chunk_size, overlap=overlap,
    )
    # Brief: live mode gọi LLM 1 call toàn transcript; fixture mode bỏ qua.
    brief_raw = None
    if live:
        from pipeline.extract import extract_brief

        try:
            brief_raw = extract_brief(meta, turns)
        except RuntimeError:
            brief_raw = None
    meeting = Meeting(
        id=meta["id"],
        title=meta.get("title", tc_id),
        date=meta["date"],
        participants=[Participant(**p) for p in meta.get("participants", [])],
        source_file=str(transcript),
        pipeline_version="eval",
    )
    resolution = resolve(meta, extraction["chunk_items"], llm_fn=None,
                        turns=turns)
    state = verify_state(
        meeting=meeting,
        items_raw=resolution["items"],
        conf_llm_map=extraction["conf_llm_map"],
        turns=turns,
        limitations=list(ingest_lims)
        + extraction["known_limitations"]
        + resolution["known_limitations"],
        brief_raw=brief_raw,
    )
    return {"state": state, "turns": len(turns)}


def _badge(conf: float) -> str:
    return badge_for(conf)


def compare(tc_id: str, state, golden: dict[str, Any]) -> dict[str, Any]:
    """So state với golden → từng check pass/fail + chi tiết (trung thực)."""
    checks: dict[str, dict[str, Any]] = {}

    def put(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"pass": bool(ok), "detail": detail}

    items = list(state.items)
    finals = [i for i in items if getattr(i, "type", "") == "decision"
              and getattr(i, "status", "") == "final"]

    # no_decision
    if "no_decision" in golden:
        put("no_decision", state.no_decision == golden["no_decision"],
            f"expected={golden['no_decision']} actual={state.no_decision}")

    # decisions_final (content_any/evidence_ts_any: biến thể ngữ nghĩa tương đương,
    # vd live paraphrase "vendor Y" thay vì "phương án B" — đúng ý vẫn đạt).
    # Best-match (không greedy-first): ứng viên đúng nhiều sub-check nhất thắng.
    for idx, gd in enumerate(golden.get("decisions_final", [])):
        variants = [gd.get("content", "")] + list(gd.get("content_any", []))
        cands = [f for f in finals
                 if any(_contains(v, f.content or "") for v in variants if v)]
        if not cands:
            put(f"decision[{idx}]", False,
                f"không tìm thấy final khớp content~{gd.get('content', '')!r}")
            continue

        def _dscore(f) -> int:
            s = 0
            if gd.get("decided_by") and f.decided_by == gd["decided_by"]:
                s += 1
            if gd.get("supersedes") and set(f.supersedes or []) == set(gd["supersedes"]):
                s += 1
            want = list(gd.get("evidence_ts_any") or ([gd["evidence_ts"]] if gd.get("evidence_ts") else []))
            if want and any((ev.timestamp if ev else None) in want for ev in (f.evidence or [])):
                s += 1
            return s

        f = max(cands, key=_dscore)
        ok = True
        notes = [f"{f.id} content~ok"]
        if gd.get("decided_by"):
            match = f.decided_by == gd["decided_by"]
            ok &= match
            notes.append(f"decided_by={f.decided_by} (expect {gd['decided_by']})")
        if gd.get("supersedes"):
            match = set(f.supersedes or []) == set(gd["supersedes"])
            ok &= match
            notes.append(f"supersedes={f.supersedes} (expect {gd['supersedes']})")
        if gd.get("evidence_ts") or gd.get("evidence_ts_any"):
            want = list(gd.get("evidence_ts_any") or [gd.get("evidence_ts")])
            got = [(ev.timestamp if ev else None) for ev in (f.evidence or [])]
            match = any(t in want for t in got)
            ok &= match
            notes.append(f"evidence_ts~{got} (expect một trong {want} ở ≥1 evidence)")
        put(f"decision[{idx}]", ok, "; ".join(notes))

    # tasks (what dùng content_any tương tự decisions; best-match).
    # Lọc ứng viên theo owner+due TRƯỚC (hard identifiers), rồi mới xét what —
    # vì model paraphrase what (thậm chí EN↔VN) nhưng owner/due là sự thật
    # kiểm chứng được. what vẫn phải khớp biến thể mới đạt.
    for idx, gt in enumerate(golden.get("tasks", [])):
        variants = [gt.get("what", "")] + list(gt.get("content_any", []))
        pool = [i for i in items if getattr(i, "type", "") == "task"]

        def _check_task(t) -> None:
            ok = True
            notes = [f"{t.id} what~ok"]
            if gt.get("owner"):
                match = t.owner == gt["owner"]
                ok &= match
                notes.append(f"owner={t.owner} (expect {gt['owner']})")
            if gt.get("due"):
                match = t.due == gt["due"]
                ok &= match
                notes.append(f"due={t.due} (expect {gt['due']})")
            if gt.get("link_to_decision"):
                match = t.link_to_decision == gt["link_to_decision"]
                ok &= match
                notes.append(f"link={t.link_to_decision} (expect {gt['link_to_decision']})")
            # due_hint: hỗ trợ cả "due_hint" (exact) và "due_hint_any" (list of variants)
            if gt.get("due_hint_any") is not None:
                want_hints = list(gt["due_hint_any"])
                actual_hint = t.due_hint or ""
                match = any(_contains(h, actual_hint) for h in want_hints if h)
                ok &= match
                notes.append(
                    f"due_hint~{actual_hint!r} (expect~một trong {want_hints})"
                )
            elif gt.get("due_hint") is not None:
                match = _contains(gt["due_hint"], t.due_hint or "")
                ok &= match
                notes.append(f"due_hint~{t.due_hint!r} (expect~{gt['due_hint']!r})")
            put(f"task[{idx}]", ok, "; ".join(notes))

        def _content_ok(t) -> bool:
            return any(_contains(v, getattr(t, "what", "") or "") for v in variants if v)

        def _hard_ok(t) -> bool:
            if gt.get("owner") and t.owner != gt["owner"]:
                return False
            if gt.get("due") and t.due != gt["due"]:
                return False
            return True

        def _tscore(t) -> int:
            s = 0
            if gt.get("owner") and t.owner == gt["owner"]:
                s += 1
            if gt.get("due") and t.due == gt["due"]:
                s += 1
            if gt.get("link_to_decision") and t.link_to_decision == gt["link_to_decision"]:
                s += 1
            if gt.get("due_hint") is not None and _contains(gt["due_hint"], t.due_hint or ""):
                s += 1
            return s

        hard = [t for t in pool if _hard_ok(t) and _content_ok(t)]
        if hard:
            _check_task(max(hard, key=_tscore))
            continue
        # Fallback: nới owner/due để báo chi tiết (phân biệt "sai task" vs "sai field").
        loose = [t for t in pool if _content_ok(t)]
        if not loose:
            put(f"task[{idx}]", False, f"không tìm thấy task~{gt.get('what', '')!r}")
            continue
        _check_task(max(loose, key=_tscore))

    # open_issues_min (chấp nhận cả 2 tên key do golden viết không nhất quán)
    oi_min = golden.get("open_issues_min", golden.get("expected_open_issues_min"))
    if oi_min:
        n = sum(1 for i in items if getattr(i, "type", "") == "open_issue")
        put("open_issues_min", n >= oi_min, f"found={n}")

    # unresolved_reversal_expected (tc5 — pass = flag trung thực, không phải "đúng đáp án").
    # Hành vi cốt lõi: CÓ flag + CÓ Open Issue O_REV cho host + export bị khóa (còn đỏ).
    # (Kể từ merge-ratio: 2 cách nói cùng 1 chốt được gộp trước nên số final bị flag
    # có thể ít đi — quan trọng là flag tồn tại, không phải đếm.)
    if golden.get("unresolved_reversal_expected"):
        flagged = [i for i in finals if getattr(i, "unresolved_reversal", False)]
        has_orev = any(getattr(i, "type", "") == "open_issue" and "REV" in (i.id or "")
                       for i in items)
        ok = len(flagged) >= 1 and has_orev
        put("unresolved_reversal", ok,
            f"flagged={len(flagged)} finals, O_REV={'có' if has_orev else 'THIẾU'} "
            f"(tc5 DỰ KIẾN không chốt được)")

    # expected_red_min (số thẻ đỏ TỐI THIỂU — model có thể flag thêm, không phạt thừa)
    red_min = golden.get("expected_red_min", golden.get("expected_red_count"))
    if red_min is not None:
        reds = sum(1 for i in items if _badge(float(i.confidence)) == "red")
        put("red_count", reds >= red_min,
            f"red={reds} (expect≥{red_min})")

    # M3: false_final_count — số Decision final KHÔNG match content nào trong golden.
    # Đếm từ `finals` survivors (đã verify xong). Mục tiêu = 0 nếu golden có
    # decisions_final; nếu golden trống thì 0 final cũng đạt.
    expected_finals_in_golden = len(golden.get("decisions_final", []))
    matched_final_ids: set[str] = set()
    for gd in golden.get("decisions_final", []):
        variants = [gd.get("content", "")] + list(gd.get("content_any", []))
        for f in finals:
            if f.id in matched_final_ids:
                continue
            if any(_contains(v, f.content or "") for v in variants if v):
                matched_final_ids.add(f.id)
                break
    false_finals = [f for f in finals if f.id not in matched_final_ids]
    # Chỉ fail khi golden kỳ vọng có final mà có extra. Nếu golden kỳ vọng
    # KHÔNG có final (vd tc3), false_finals có thể > 0 do final cũ bị trả.
    # Bài test M3 trên tc6: 2 final expected, M3-A hạ Stripe → false = 2? đếm
    # xem có khớp expected không.
    false_final_max = golden.get("false_final_count_max")
    if false_final_max is not None:
        put("false_final_count", len(false_finals) <= false_final_max,
            f"false_final={len(false_finals)} (expect≤{false_final_max}, "
            f"matched={len(matched_final_ids)}, golden_finals={expected_finals_in_golden})")
    # Always log false_final as informational metric (không tính fail).
    checks.setdefault("_info_false_final", {
        "pass": True,
        "detail": (
            f"false_final={len(false_finals)} (info-only); "
            f"ids={[f.id for f in false_finals]}"
        ),
    })

    # brief (taxonomy §8): có thì outcomes phải trỏ ID tồn tại (verify đã enforce).
    # Golden chưa có brief → chỉ ghi nhận thông tin, không tính fail.
    brief = getattr(state, "brief", None)
    if brief is not None:
        ids = {i.id for i in items}
        bad_refs = [r for o in brief.outcomes for r in (o.ref_ids or []) if r not in ids]
        put("brief", not bad_refs,
            f"problem={bool(brief.problem.strip())} outcomes={len(brief.outcomes)} "
            f"bad_refs={bad_refs or 'không có'}")

    badges = {"red": 0, "yellow": 0, "green": 0}
    for i in items:
        badges[_badge(float(i.confidence))] += 1
    return {
        "case": tc_id,
        "items_total": len(items),
        "badges": badges,
        "no_decision": state.no_decision,
        "limitations": list(state.known_limitations),
        "checks": checks,
        "pass": all(c["pass"] for c in checks.values()) if checks else True,
    }


def run_all(
    cases: list[str] | None = None,
    *,
    live: bool = False,
    chunk_size: int = 40,
    overlap: int = 10,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Chạy toàn bộ cases → compare golden → dict kết quả."""
    cases = cases or CASES
    results = []
    for tc in cases:
        out = run_case(tc, live=live, chunk_size=chunk_size, overlap=overlap, root=root)
        golden = _load_json(root / "data" / "golden" / f"{tc}_expected.json")
        cmp = compare(tc, out["state"], golden)
        cmp["turns"] = out["turns"]
        results.append(cmp)
    return {
        "mode": "live" if live else "fixture",
        "chunk_size": chunk_size,
        "overlap": overlap,
        "results": results,
        "all_pass": all(r["pass"] for r in results),
    }


def print_table(report: dict[str, Any]) -> None:
    print(f"== eval ({report['mode']}) ==")
    for r in report["results"]:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"[{mark}] {r['case']}: {r['items_total']} items "
              f"(R/Y/G={r['badges']['red']}/{r['badges']['yellow']}/{r['badges']['green']}) "
              f"no_decision={r['no_decision']}")
        for name, c in r["checks"].items():
            print(f"       {'ok ' if c['pass'] else 'X  '} {name}: {c['detail']}")
    print("ALL PASS" if report["all_pass"] else "SOME FAILED")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Eval 5 ca meet2note")
    ap.add_argument("--live", action="store_true", help="dùng LLM thật thay vì fixture")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--chunk-size", type=int, default=40)
    ap.add_argument("--overlap", type=int, default=10)
    ap.add_argument("--out", default="eval/results.json")
    args = ap.parse_args(argv)

    report = run_all(
        args.cases.split(","), live=args.live,
        chunk_size=args.chunk_size, overlap=args.overlap,
    )
    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_table(report)
    print(f"wrote {out_path}")
    # tc2 là kill-criterion (acceptance #2): tc2 fail → exit 1 (tc5 fail-dự-kiến không tính).
    tc2 = next((r for r in report["results"] if r["case"] == "tc2"), None)
    return 0 if (tc2 and tc2["pass"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
