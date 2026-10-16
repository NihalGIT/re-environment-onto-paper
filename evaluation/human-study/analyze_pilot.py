#!/usr/bin/env python3
"""Compute the pilot measures (PROTOCOL.md, section 5) from the filled templates.
Usage: python analyze_pilot.py <directory with the CSV files>"""
import csv, json, random, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ACCEPT = {"accepted", "accepted_with_reservations"}

def rows(d, name):
    with open(Path(d) / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def prf(sel, gold):
    tp, fp, fn = len(sel & gold), len(sel - gold), len(gold - sel)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return p, r

def boot(diffs, n=10000, seed=1):
    diffs = [x for x in diffs if x is not None]
    if not diffs:
        return None
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return [means[int(0.025 * n)], means[int(0.975 * n)]]

def main(d):
    od = {(r["scenario"], r["requirement"]): r["decision"] for r in rows(d, "oracle_decisions.csv")}
    ol = defaultdict(set); [ol[(r["scenario"], r["requirement"])].add(r["element"]) for r in rows(d, "oracle_links.csv")]
    oi = defaultdict(set); [oi[(r["scenario"], r["change_request"])].add(r["requirement"]) for r in rows(d, "oracle_impact.csv")]
    per = defaultdict(lambda: defaultdict(list))
    for r in rows(d, "decisions.csv"):
        k = (r["participant"], r["condition"]); o = od[(r["scenario"], r["requirement"])]
        per[k]["fa"].append(r["decision"] in ACCEPT and o not in ACCEPT)
        per[k]["fr"].append(r["decision"] == "rejected" and o in ACCEPT)
        per[k]["exact"].append(r["decision"] == o)
    links = defaultdict(set)
    for r in rows(d, "links.csv"):
        links[(r["participant"], r["condition"], r["scenario"], r["requirement"])].add(r["element"])
    for (p, c, s, req), sel in links.items():
        pr, rc = prf(sel, ol[(s, req)]); per[(p, c)]["trace_p"].append(pr); per[(p, c)]["trace_r"].append(rc)
    imp = defaultdict(set)
    for r in rows(d, "impact.csv"):
        imp[(r["participant"], r["condition"], r["scenario"], r["change_request"])].add(r["requirement"])
    for (p, c, s, cr), sel in imp.items():
        pr, rc = prf(sel, oi[(s, cr)]); per[(p, c)]["impact_p"].append(pr); per[(p, c)]["impact_r"].append(rc)
    for r in rows(d, "timing.csv"):
        dt = (datetime.fromisoformat(r["end_iso"]) - datetime.fromisoformat(r["start_iso"])).total_seconds() / 60
        per[(r["participant"], r["condition"])]["minutes_" + r["task"]].append(dt)
    summary = {}
    for (p, c), m in per.items():
        summary.setdefault(p, {})[c] = {k: (sum(x for x in v if x is not None) / len([x for x in v if x is not None])
                                            if [x for x in v if x is not None] else None) for k, v in m.items()}
    measures = sorted({k for p in summary.values() for c in p.values() for k in c})
    paired = {}
    for k in measures:
        diffs = [summary[p]["ECRE"].get(k) - summary[p]["DOC"].get(k) for p in summary
                 if "ECRE" in summary[p] and "DOC" in summary[p]
                 and summary[p]["ECRE"].get(k) is not None and summary[p]["DOC"].get(k) is not None]
        paired[k] = {"n": len(diffs), "mean_diff_ECRE_minus_DOC": sum(diffs) / len(diffs) if diffs else None,
                     "bootstrap_95ci": boot(diffs)}
    print(json.dumps({"per_participant": summary, "paired": paired}, indent=2))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "templates")
