#!/usr/bin/env python3
"""Extension-contract check with a vocabulary extension (temporal constraints).
1. Conservativity: loading the extension vocabulary (no instances) leaves the
   38 regression decisions and the 34 competency-question answers unchanged.
2. Recognition: an instance of the new subclass is treated as a constraint by
   the checker (subclass closure); without a registered validator an applicable
   hard instance sends the requirement to review.
Writes results/extension_results.json."""
import json, sys
from copy import deepcopy
from pathlib import Path
import rdflib
from rdflib import RDF, Literal, Namespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R
import prototype as P
import run_competency_questions as CQ
EXT = ROOT / "evaluation" / "extension" / "temporal-extension.ttl"
TX = Namespace("http://re-environment-onto.org/ext/temporal#")

def main():
    ext = R.load_graph([EXT])
    base = R.load_graph([P.BASE])
    cases = P.original_scenarios() + P.targeted_regressions()
    plain = {c.name: P.run_case(base, c, with_shacl=False)["observed"] for c in cases}
    based = deepcopy(base); based += ext
    withext = {c.name: P.run_case(based, c, with_shacl=False)["observed"] for c in cases}
    changed = [k for k in plain if plain[k] != withext[k]]
    gs = CQ.graphs(); specs = json.loads(CQ.SUITE.read_text(encoding="utf-8"))
    cq_changed = []
    for s in specs:
        g = gs[s["graph"]]; g2 = deepcopy(g); g2 += ext
        a = [sorted(map(str, r)) for r in g.query(s["query"])] if s["kind"] != "ask" else g.query(s["query"]).askAnswer
        b = [sorted(map(str, r)) for r in g2.query(s["query"])] if s["kind"] != "ask" else g2.query(s["query"]).askAnswer
        if (sorted(a) if isinstance(a, list) else a) != (sorted(b) if isinstance(b, list) else b):
            cq_changed.append(s["id"])
    # Recognition of an instance of the new subclass.
    g = deepcopy(based)
    c = R.EX["C950_NightShiftRule"]
    for t in [(c, RDF.type, TX.TemporalConstraint), (c, R.REO.constraintId, Literal("C-950")),
              (c, R.REO.constraintName, Literal("Night-shift rule")), (c, R.REO.formalExpression, Literal("manual")),
              (c, R.REO.naturalLanguage, Literal("Night-shift prescriptions need a second signature.")),
              (c, R.REO.enforcementLevel, Literal("hard")), (c, R.REO.appliesTo, R.EX.Physician),
              (c, TX.validUntil, Literal("2027-01-01T00:00:00", datatype=rdflib.XSD.dateTime))]:
        g.add(t)
    resolve = deepcopy(g); P.resolve_u001(resolve)
    env = R.project(resolve)
    res = R.validate(env, P.baseline_requirement())
    recognized = "C950_NightShiftRule" in env.constraints
    out = {"regression_cases": len(cases), "regression_changed_by_vocabulary": changed,
           "cq_total": len(specs), "cq_changed_by_vocabulary": cq_changed,
           "instance_recognized_as_constraint": recognized, "R001_with_instance": res.state,
           "pass": not changed and not cq_changed and recognized and res.state == R.PENDING_REVIEW}
    (ROOT / "results" / "extension_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
