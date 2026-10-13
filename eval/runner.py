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
        llm_fn = _make_fixture_llm(root / _FIXTURE_FOR[tc_id])

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
    resolution = resolve(meta, extraction["chunk_items"], llm_fn=None)
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
    # vd live paraphrase "vendor Y" thay vì "phương án B" — đúng ý vẫn đạt)
    for idx, gd in enumerate(golden.get("decisions_final", [])):
        variants = [gd.get("content", "")] + list(gd.get("content_any", []))
        cand = [f for f in finals
                if any(_contains(v, f.content or "") for v in variants if v)]
        if not cand:
            put(f"decision[{idx}]", False,
                f"không tìm thấy final khớp content~{gd.get('content', '')!r}")
            continue
        f = cand[0]
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

    # tasks (what dùng content_any tương tự decisions)
    for idx, gt in enumerate(golden.get("tasks", [])):
        variants = [gt.get("what", "")] + list(gt.get("content_any", []))
        cand = [i for i in items if getattr(i, "type", "") == "task"
                and any(_contains(v, getattr(i, "what", "") or "") for v in variants if v)]
        if not cand:
            put(f"task[{idx}]", False, f"không tìm thấy task~{gt.get('what', '')!r}")
            continue
        t = cand[0]
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
        if gt.get("due_hint") is not None:
            match = _contains(gt["due_hint"], t.due_hint or "")
            ok &= match
            notes.append(f"due_hint~{t.due_hint!r} (expect~{gt['due_hint']!r})")
        put(f"task[{idx}]", ok, "; ".join(notes))

    # open_issues_min
    if golden.get("open_issues_min"):
        n = sum(1 for i in items if getattr(i, "type", "") == "open_issue")
        put("open_issues_min", n >= golden["open_issues_min"], f"found={n}")

    # unresolved_reversal_expected (tc5 — pass = flag trung thực, không phải "đúng đáp án")
    if golden.get("unresolved_reversal_expected"):
        flagged = [i for i in finals if getattr(i, "unresolved_reversal", False)]
        put("unresolved_reversal", len(flagged) >= 2,
            f"flagged={len(flagged)} finals (expect≥2, tc5 DỰ KIẾN không chốt được)")

    # expected_red_count
    if golden.get("expected_red_count") is not None:
        reds = sum(1 for i in items if _badge(float(i.confidence)) == "red")
        put("red_count", reds == golden["expected_red_count"],
            f"red={reds} (expect {golden['expected_red_count']})")

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
