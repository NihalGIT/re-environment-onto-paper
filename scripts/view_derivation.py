#!/usr/bin/env python3
"""Apply the view-selection criteria to the framework x concern coding.
Writes results/view_derivation.json."""
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "evaluation" / "view-derivation"
rows = list(csv.DictReader(open(D / "framework_concern_matrix.csv", encoding="utf-8")))
crit = json.loads((D / "criteria.json").read_text(encoding="utf-8"))
concerns = [c for c in rows[0] if c not in ("framework", "bibkey")]
out = {}
for c in concerns:
    first = [r["framework"] for r in rows if r[c] == "2"]
    partial = [r["framework"] for r in rows if r[c] == "1"]
    a = crit["assessment"][c]
    c1 = len(first) >= 3
    retained = c1 and a["C2"] and a["C3_holds"] and a["C4"]
    out[c] = {"first_class": len(first), "partial": len(partial), "C1": c1, "C2": a["C2"],
              "C3": a["C3"], "C3_holds": a["C3_holds"], "C4": a["C4"], "retained_by_rule": retained, "decision": a["decision"]}
    assert retained == a["decision"].startswith("view"), (c, retained, a["decision"])
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "view_derivation.json").write_text(json.dumps({"frameworks": len(rows), "concerns": out}, indent=2))
for c, v in out.items():
    print(f"{c:16s} first={v['first_class']} partial={v['partial']} retained={v['retained_by_rule']!s:5s} {v['decision']}")
