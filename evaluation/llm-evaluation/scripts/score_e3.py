#!/usr/bin/env python3
"""Score study E3: agreement of independent LLM coders with the author coding
of the 12 x 17 framework-concern matrix, and effect on the view selection.

Reports, for each coder and for the pair of coders: exact agreement, Cohen's
kappa (nominal, 3 categories) and quadratic-weighted kappa; Fleiss' kappa over
the three codings; per-concern first-class counts and whether criterion C1
(first-class in >= 3 frameworks) and the resulting retain/merge decision
(C1 together with the author-assessed C2-C4, unchanged) would differ.

Usage: python score_e3.py <out.json> <coding.json> [...]
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VD = ROOT / "evaluation" / "view-derivation"
NAMES = ["WRSPM", "Problem Frames", "KAOS", "iStar", "CORE", "Dey", "Contextual goal models",
         "Uncertainty taxonomy", "RELAX", "ISO 29148", "SysML v2", "Traceability reference model"]


def kappa(a, b, cats=(0, 1, 2), weights=None):
    n = len(a)
    w = weights or (lambda i, j: 0.0 if i == j else 1.0)
    po = sum(w(x, y) for x, y in zip(a, b)) / n
    pa, pb = Counter(a), Counter(b)
    pe = sum(pa[i] * pb[j] * w(i, j) for i in cats for j in cats) / (n * n)
    return round(1 - po / pe, 3) if pe else 1.0


def quad(i, j):
    return ((i - j) / 2) ** 2


def fleiss(ratings, cats=(0, 1, 2)):
    n = len(ratings[0]); N = len(ratings[0][0]) if False else None
    items = list(zip(*ratings)); k = len(ratings)
    P = [(sum(c * c for c in Counter(it).values()) - k) / (k * (k - 1)) for it in items]
    p = [sum(Counter(it)[c] for it in items) / (len(items) * k) for c in cats]
    Pbar, Pe = sum(P) / len(P), sum(x * x for x in p)
    return round((Pbar - Pe) / (1 - Pe), 3)


def main(out, *coding_files):
    rows = list(csv.DictReader(open(VD / "framework_concern_matrix.csv", encoding="utf-8")))
    concerns = [c for c in rows[0] if c not in ("framework", "bibkey")]
    crit = json.loads((VD / "criteria.json").read_text())
    author = {NAMES[i]: {c: int(r[c]) for c in concerns} for i, r in enumerate(rows)}
    coders = {"author": author}
    for f in coding_files:
        d = json.loads(Path(f).read_text())
        coders[d["coder_code"]] = {fw: {c: int(d["matrix"][fw][c]) for c in concerns} for fw in NAMES}
    vec = {k: [m[fw][c] for fw in NAMES for c in concerns] for k, m in coders.items()}
    keys = list(coders)
    pairs = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = vec[keys[i]], vec[keys[j]]
            pairs[f"{keys[i]}~{keys[j]}"] = {
                "exact_agreement": round(sum(x == y for x, y in zip(a, b)) / len(a), 3),
                "cohen_kappa": kappa(a, b), "weighted_kappa_quadratic": kappa(a, b, weights=quad),
                "first_class_agreement": round(sum((x == 2) == (y == 2) for x, y in zip(a, b)) / len(a), 3),
                "disagreements": {f"{u}-{v}": sum(1 for x, y in zip(a, b) if x != y and sorted((x, y)) == [u, v])
                                  for u, v in ((0, 1), (1, 2), (0, 2))}}
    per_concern = {}
    for c in concerns:
        a = crit["assessment"][c]
        entry = {}
        for k, m in coders.items():
            fc = sum(m[fw][c] == 2 for fw in NAMES)
            c1 = fc >= 3
            entry[k] = {"first_class": fc, "partial": sum(m[fw][c] == 1 for fw in NAMES), "C1": c1,
                        "retained": c1 and a["C2"] and a["C3_holds"] and a["C4"]}
        entry["decision_changes"] = sorted(k for k in coders if entry[k]["retained"] != entry["author"]["retained"])
        per_concern[c] = entry
    sensitivity = {}
    for th in (2, 3, 4):
        sensitivity[str(th)] = {}
        for k, m in coders.items():
            sensitivity[str(th)][k] = sorted(
                c for c in concerns if sum(m[fw][c] == 2 for fw in NAMES) >= th and crit["assessment"][c]["C2"]
                and crit["assessment"][c]["C4"] and crit["assessment"][c]["C3_holds"])
    report = {"cells": len(vec["author"]), "c1_threshold_sensitivity": sensitivity, "pairwise": pairs, "fleiss_kappa": fleiss([vec[k] for k in keys]),
              "per_concern": per_concern,
              "retained_by_coder": {k: sorted(c for c in concerns if per_concern[c][k]["retained"]) for k in keys}}
    Path(out).write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "per_concern"}, indent=1))
    for c in concerns:
        print(f"{c:15s}", {k: per_concern[c][k]["first_class"] for k in keys}, per_concern[c]["decision_changes"])


if __name__ == "__main__":
    main(*sys.argv[1:])
