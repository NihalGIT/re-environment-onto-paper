#!/usr/bin/env python3
"""Sensitivity of the document-based (TF-IDF) impact baseline to its threshold tau.

Table 15 of the paper reports the document baseline at tau = 0.10, whereas the
trace evaluation (Table 14) scans a grid of thresholds. This script recomputes,
for every mutant of the schema-derived corpus, the requirements whose assessment
or decision changes (reference checker only) and the requirements selected by
TF-IDF links at every threshold of that grid. It cross-checks tau = 0.10 against
results/evaluation_summary.json and writes results/ir_sensitivity.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import rdflib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R  # noqa: E402
import run_evaluation as E  # noqa: E402

GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def main() -> int:
    g0 = R.load_graph(E.ENV_FILES)
    reqs = R.load_requirements(R.load_graph([E.REQ_FILE]))
    rids = [q.rid for q in reqs]
    env0 = R.project(g0)
    base = {q.rid: R.validate(env0, q) for q in reqs}
    base_assess = {rid: E.assessment(r) for rid, r in base.items()}
    sims = E.tfidf_links(E.ir_documents(g0), reqs)
    links = {tau: {rid: {e for e, s in sims[rid].items() if s >= tau} for rid in rids} for tau in GRID}
    acc = {gk: {tau: [0, 0, 0, 0] for tau in GRID} for gk in ("assessment", "decision")}
    muts = E.generate_corpus(g0)
    for m in muts:
        g = rdflib.Graph()
        g += g0
        for t in m["remove"]:
            g.remove(t)
        for t in m["add"]:
            g.add(t)
        env = R.project(g)
        res = {q.rid: R.validate(env, q) for q in reqs}
        gold = {"assessment": {r for r in rids if E.assessment(res[r]) != base_assess[r]},
                "decision": {r for r in rids if res[r].state != base[r].state}}
        subjects = {R.local(s) for s, _, _ in list(m["remove"]) + list(m["add"])}
        for tau in GRID:
            sel = {r for r in rids if links[tau][r] & subjects}
            for gk, gs in gold.items():
                a = acc[gk][tau]
                a[0] += len(sel & gs)
                a[1] += len(sel - gs)
                a[2] += len(gs - sel)
                a[3] += len(sel)
    out = {"grid": GRID, "mutants": len(muts)}
    for gk, by_tau in acc.items():
        out[gk] = {}
        for tau, (tp, fp, fn, nsel) in by_tau.items():
            out[gk][f"{tau:.2f}"] = {**E.prf(tp, fp, fn), "miss_rate": fn / (tp + fn) if tp + fn else None,
                                     "mean_revalidations": nsel / len(muts)}
    ref = json.loads((ROOT / "results" / "evaluation_summary.json").read_text())["impact"]
    for gk in ("assessment", "decision"):
        m5, x = ref[gk]["M5_document_IR_tau_0.10"], out[gk]["0.10"]
        assert (x["tp"], x["fp"], x["fn"]) == (m5["tp"], m5["fp"], m5["fn"]), (gk, x, m5)
    out["cross_check_tau_0.10"] = "identical to results/evaluation_summary.json (M5)"
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "ir_sensitivity.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for gk in ("assessment", "decision"):
        for tau in GRID:
            v = out[gk][f"{tau:.2f}"]
            print(f"{gk:10s} tau={tau:.2f} P={v['precision']:.3f} R={v['recall']:.3f} "
                  f"miss={v['miss_rate']:.1%} cost={v['mean_revalidations']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
