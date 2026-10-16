#!/usr/bin/env python3
"""Score study E2: LLM analysts' hand-applied decisions against the contract.

Ground truth = decisions of the reference checker on each mutant (identical to
the independent SPARQL oracle on every pair). Metrics per analyst:
decision accuracy over all (case, requirement) pairs, accuracy on pairs whose
decision changes, impact precision/recall/F1 (requirements whose decision
changes), cases answered without any error, and wall-clock time per decision
(from the agent runtime's metadata, raw/agent_usage.json).

Usage: python score_e2.py <out.json> <truth.json> <audit.json> <agent_usage.json> <answers.json> [...]
"""
import json
import sys
from pathlib import Path


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


def main(out, truth_path, audit_path, usage_path, *answer_files):
    usage = json.loads(Path(usage_path).read_text())
    T = json.loads(Path(truth_path).read_text())
    base = T["base_decisions"]
    truth = {c["case"]: c["truth"] for c in T["cases"]}
    audit = {a["folder"].rstrip("/").rsplit("/", 1)[-1]: a for a in json.loads(Path(audit_path).read_text())}
    report = {"cases": len(truth), "pairs": len(truth) * len(base),
              "changing_pairs": sum(truth[c][r] != base[r] for c in truth for r in base), "analysts": []}
    for f in answer_files:
        A = json.loads(Path(f).read_text())
        code = A["analyst_code"]
        ans = {a["case"]: {r: str(s).strip().lower().replace(" ", "_") for r, s in a["decisions"].items()}
               for a in A["answers"]}
        pairs = correct = ch_total = ch_correct = perfect = 0
        tp = fp = fn = 0
        errors = []
        for c, tv in truth.items():
            ok_case = True
            for r in base:
                got = ans.get(c, {}).get(r)
                pairs += 1
                hit = got == tv[r]
                correct += hit
                if tv[r] != base[r]:
                    ch_total += 1; ch_correct += hit
                pred_changed, true_changed = got is not None and got != base[r], tv[r] != base[r]
                tp += pred_changed and true_changed; fp += pred_changed and not true_changed
                fn += true_changed and not pred_changed
                if not hit:
                    ok_case = False
                    errors.append({"case": c, "requirement": r, "base": base[r], "truth": tv[r], "analyst": got})
            perfect += ok_case
        folder = "E2-" + code
        au = audit.get(folder, {})
        report["analysts"].append({
            "analyst": code, "condition": code.split("-")[0], "model": ",".join(au.get("models", [])),
            "decision_accuracy": round(correct / pairs, 3), "correct": correct, "pairs": pairs,
            "changing_pair_accuracy": round(ch_correct / ch_total, 3) if ch_total else None,
            "impact": prf(tp, fp, fn), "cases_without_error": perfect,
            "seconds": round(usage[folder]["duration_ms"] / 1000, 1),
            "seconds_per_decision": round(usage[folder]["duration_ms"] / 1000 / pairs, 2),
            "runtime_tokens": usage[folder]["subagent_tokens"],
            "errors": errors})
    Path(out).write_text(json.dumps(report, indent=1))
    for a in report["analysts"]:
        print(a["analyst"], a["model"], "acc", a["decision_accuracy"], "chg-acc", a["changing_pair_accuracy"],
              "impact", a["impact"]["precision"], a["impact"]["recall"], a["impact"]["f1"],
              "perfect cases", a["cases_without_error"], "errors", len(a["errors"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
