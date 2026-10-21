"""Capture BEFORE results for tc6 by disabling M3 gates.

Uses monkey-patching on the M3 gate functions to make them no-ops,
then runs the eval pipeline to capture what M2-era behavior would be.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    # Monkey-patch M3 gates to no-ops (simulate M2 baseline)
    from pipeline import resolve as resolve_pkg
    from pipeline import verify as verify_pkg

    # Save originals
    orig_apply_decision_gate = resolve_pkg._apply_decision_gate
    orig_apply_hedge_gate = resolve_pkg._apply_hedge_gate
    orig_reclassify = resolve_pkg._reclassify_knowledge_task
    orig_apply_due_rev = resolve_pkg._apply_due_revision
    orig_check_chain = verify_pkg._check_evidence_chain_for_final

    def _noop_apply_decision_gate(items, participants, turns, limitations):
        # M2 baseline: don't run M3-A gate
        return None

    def _noop_apply_hedge_gate(items, turns, limitations):
        return None

    def _noop_reclassify(items, limitations):
        return None

    def _noop_apply_due_rev(items, meta, limitations):
        return None

    def _noop_check_chain(item_dict):
        return False, False, ""

    # Apply no-ops
    resolve_pkg._apply_decision_gate = _noop_apply_decision_gate
    resolve_pkg._apply_hedge_gate = _noop_apply_hedge_gate
    resolve_pkg._reclassify_knowledge_task = _noop_reclassify
    resolve_pkg._apply_due_revision = _noop_apply_due_rev
    verify_pkg._check_evidence_chain_for_final = _noop_check_chain

    # Also patch the names imported inside the modules
    import pipeline.resolve as r_mod
    r_mod._apply_decision_gate = _noop_apply_decision_gate
    r_mod._apply_hedge_gate = _noop_apply_hedge_gate
    r_mod._reclassify_knowledge_task = _noop_reclassify
    r_mod._apply_due_revision = _noop_apply_due_rev

    try:
        # Run eval for tc6
        from eval.runner import run_case, compare as compare_fn
        from pathlib import Path

        meta = json.loads(
            Path("data/meta/tc6_meta.json").read_text(encoding="utf-8")
        )
        golden = json.loads(
            Path("data/golden/tc6_expected.json").read_text(encoding="utf-8")
        )
        # Disable turns= so M3-A's retract check is also disabled (truly M2)
        # Actually we DO want turns here for the BEFORE state too,
        # because the M2 baseline would have the same retract signal check
        # (since M2 doesn't even know about retract — but we want consistency)
        out = run_case("tc6", live=False, chunk_size=40, overlap=10)
        state = out["state"]
        cmp = compare_fn("tc6", state, golden)

        # Output summary for the BEFORE report
        print("=" * 60)
        print("BEFORE (M2 baseline — M3 gates disabled):")
        print("=" * 60)
        items = list(state.items)
        finals = [
            i for i in items
            if getattr(i, "type", "") == "decision"
            and getattr(i, "status", "") == "final"
        ]
        tasks = [i for i in items if getattr(i, "type", "") == "task"]
        knows = [i for i in items if getattr(i, "type", "") == "knowledge"]
        ois = [i for i in items if getattr(i, "type", "") == "open_issue"]

        print(f"items_total: {len(items)}")
        print(f"finals: {len(finals)}")
        for f in finals:
            print(f"  - {f.id} status={f.status} content={f.content[:50]!r}")
        print(f"tasks: {len(tasks)}")
        for t in tasks:
            print(
                f"  - {t.id} what={t.what[:30]!r} owner={t.owner} "
                f"due={t.due} due_hint={t.due_hint!r}"
            )
        print(f"knowledge: {len(knows)}")
        for k in knows:
            print(f"  - {k.id} type={k.type} content={k.content[:50]!r}")
        print(f"open_issues: {len(ois)}")

        badges = {"red": 0, "yellow": 0, "green": 0}
        from pipeline.verify import badge_for
        for it in items:
            badges[badge_for(float(it.confidence))] += 1
        print(f"badges: {badges}")

        # Identify false_final (finals not in golden)
        matched = set()
        for gd in golden.get("decisions_final", []):
            variants = [gd.get("content", "")] + list(gd.get("content_any", []))
            for f in finals:
                if f.id in matched:
                    continue
                if any(_contains(v, f.content or "") for v in variants if v):
                    matched.add(f.id)
                    break
        false_finals = [f for f in finals if f.id not in matched]
        print(f"false_final_count: {len(false_finals)} (BEFORE)")
        for ff in false_finals:
            print(f"  - false_final: {ff.id} content={ff.content[:50]!r}")
        print(f"checks: {cmp['checks']}")

        # Save BEFORE summary
        summary = {
            "mode": "fixture-M2-baseline",
            "items_total": len(items),
            "finals_count": len(finals),
            "tasks_count": len(tasks),
            "knowledge_count": len(knows),
            "open_issues_count": len(ois),
            "badges": badges,
            "false_final_count": len(false_finals),
            "false_final_ids": [f.id for f in false_finals],
            "pass": cmp["pass"],
        }
        Path("eval/results_tc6_before.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("\nSaved to eval/results_tc6_before.json")

    finally:
        # Restore
        resolve_pkg._apply_decision_gate = orig_apply_decision_gate
        resolve_pkg._apply_hedge_gate = orig_apply_hedge_gate
        resolve_pkg._reclassify_knowledge_task = orig_reclassify
        resolve_pkg._apply_due_revision = orig_apply_due_rev
        verify_pkg._check_evidence_chain_for_final = orig_check_chain
        r_mod._apply_decision_gate = orig_apply_decision_gate
        r_mod._apply_hedge_gate = orig_apply_hedge_gate
        r_mod._reclassify_knowledge_task = orig_reclassify
        r_mod._apply_due_revision = orig_apply_due_rev


def _contains(a: str, b: str) -> bool:
    import unicodedata
    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFC", s or "").lower()
        s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
        return " ".join(s.split())
    na, nb = _norm(a), _norm(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


if __name__ == "__main__":
    main()