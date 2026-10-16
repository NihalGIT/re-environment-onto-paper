#!/usr/bin/env python3
"""Collect the results of studies E1-E3 into results/llm_evaluation_summary.json
(the file read by scripts/export_paper_macros.py)."""
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RES = HERE / "results"
RAW = HERE / "raw"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    base = load(ROOT / "results" / "evaluation_summary.json")["baseline_decisions"]
    audit = load(RAW / "audit.json")
    by_folder = {a["folder"].rstrip("/").rsplit("/", 1)[-1]: a for a in audit}
    e1, e1i = load(RES / "e1_run.json"), load(RES / "e1_run_initial_no_migration.json")
    authors = []
    targeted, states_nt = Counter(), Counter()
    vocab_terms = set()
    for a, ai in zip(e1["authors"], e1i["authors"]):
        suite = load(RAW / a["file"])
        items = [i for s in a["scenarios"] for i in s["items"]]
        nontrivial = [i for i in items if i["requirement"] not in base or i["expected"] != base[i["requirement"]]]
        for s in suite["scenarios"]:
            targeted.update(set(s.get("obligations_targeted", [])))
        states_nt.update(i["checker"] for i in nontrivial)
        for cq in suite["cqs"]:
            vocab_terms |= set(re.findall(r"reo:(\w+)", cq["sparql"]))
        au = by_folder["E1-" + a["author_code"]]
        authors.append({"author": a["author_code"], "model": ",".join(au["models"]),
                        "scenarios": a["summary"]["scenarios"],
                        "new_requirements": len({i["requirement"] for i in items if i["requirement"] not in base}),
                        "expectations": a["summary"]["expectations"], "nontrivial": len(nontrivial),
                        "matches_initial": ai["summary"]["matches"], "matches_final": a["summary"]["matches"],
                        "cqs": a["summary"]["cqs"], "cqs_match": a["summary"]["cqs_match"],
                        "invalid": a["summary"]["scenarios_invalid"] + a["summary"]["cqs_invalid"],
                        "seconds": round(load(RAW / "agent_usage.json")["E1-" + a["author_code"]]["duration_ms"] / 1000)})
    e2, e3 = load(RES / "e2_scores.json"), load(RES / "e3_scores.json")
    adj = load(RAW / "ADJ_1_adjudication.json") + load(RAW / "ADJ_2_adjudication.json")
    def answers(code):
        return {x["case"]: x["decisions"] for x in load(RAW / f"E2_{code}_answers.json")["answers"]}
    firsts = [a["analyst"] for a in e2["analysts"] if not a["analyst"].endswith("r")]
    same = total = 0
    for c in firsts:
        x, y = answers(c), answers(c + "r")
        for case in x:
            for r in x[case]:
                total += 1; same += x[case][r] == y[case][r]
    amb = sum(answers(a["analyst"])["C09"]["R001"] != "conditional" for a in e2["analysts"])
    summary = {
        "agents": len(audit), "tool_calls": sum(len(a["tool_calls"]) for a in audit),
        "blinding_violations": sum(len(a["violations"]) for a in audit),
        "models": sorted({m for a in audit for m in a["models"]}),
        "frozen_files": len(load(HERE / "freeze_record.json")["entries"]),
        "e1": {"authors": authors,
               "totals": {k: sum(a[k] for a in authors) for k in
                          ("scenarios", "new_requirements", "expectations", "nontrivial", "matches_initial",
                           "matches_final", "cqs", "cqs_match", "invalid")},
               "obligations_targeted": sorted(targeted), "states_in_nontrivial": dict(states_nt),
               "cq_reo_terms": len(vocab_terms)},
        "e2": {k: e2[k] for k in ("cases", "pairs", "changing_pairs")} | {
            "analysts": [{k: v for k, v in a.items() if k != "errors"} | {"n_errors": len(a["errors"])}
                         for a in e2["analysts"]],
            "runs": len(e2["analysts"]), "run_to_run_identical": same, "run_to_run_pairs": total,
            "ambiguous_item_runs": amb,
            "errors_outside_ambiguous_item": sum(1 for a in e2["analysts"] for e in a["errors"]
                                                 if (e["case"], e["requirement"]) != ("C09", "R001"))},
        "e3": {"cells": e3["cells"], "pairwise": e3["pairwise"], "fleiss_kappa": e3["fleiss_kappa"],
               "retained_by_coder": e3["retained_by_coder"],
               "first_class": {c: {k: v["first_class"] for k, v in d.items() if k != "decision_changes"}
                               for c, d in e3["per_concern"].items()},
               "c1_threshold_sensitivity": e3["c1_threshold_sensitivity"]},
        "adjudication": [{k: e[k] for k in ("item", "verdict")} for e in adj],
    }
    (RES / "llm_evaluation_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["e1"]["totals"]), summary["e1"]["obligations_targeted"], summary["e1"]["states_in_nontrivial"],
          "cq terms", summary["e1"]["cq_reo_terms"])
    print("agents", summary["agents"], "calls", summary["tool_calls"], "violations", summary["blinding_violations"],
          summary["models"])
    for a in summary["e2"]["analysts"]:
        print(a["analyst"], a["model"], a["decision_accuracy"], a["impact"]["f1"], a["seconds"], a["seconds_per_decision"])


if __name__ == "__main__":
    main()
