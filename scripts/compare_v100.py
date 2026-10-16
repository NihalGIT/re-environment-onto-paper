#!/usr/bin/env python3
"""Run the behaviours cited in Section VIII-C on the REO v1.0.0 checker
(evaluation/baseline-v1.0.0/prototype-1.0.0.py) to document how v1.0.0 decided
them. Mutations are applied to v1.0.0's in-memory environment, as its harness did.
Writes results/v100_targeted.json."""
import copy, importlib.util, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "evaluation" / "baseline-v1.0.0"
spec = importlib.util.spec_from_file_location("proto100", B / "prototype-1.0.0.py")
P = importlib.util.module_from_spec(spec); sys.modules["proto100"] = P; spec.loader.exec_module(P)
base = P.load_environment(str(B / "hospital-1.0.0.ttl"))
q0 = P.baseline_candidate(); ctx = "X001_EmergencyDept"
def run(env, q=q0):
    return P.validate(env, P.slice_env(env, q.seed_goal, ctx), q, ctx)[0]
def resolved():
    e = copy.deepcopy(base); e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"; return e
cases = {}
e = resolved(); e.uncertainties["U900"] = {"status": "unvalidated", "impact": "critical", "affects": ["Physician"], "blocks": []}
cases["critical_uncertainty_affects_actor"] = run(e)
e = resolved(); e.uncertainties["U902"] = {"status": "unvalidated", "impact": "high", "affects": [], "blocks": ["G001"]}
cases["uncertainty_blocks_parent_goal"] = run(e)
e = copy.deepcopy(base); e.uncertainties["U001_DrugDBFrequency"]["status"] = "rejected"
cases["blocking_premise_refuted"] = run(e)
e = resolved(); i = e.interactions["I001_PhysicianToEHR"]; i["source"], i["target"] = i["target"], i["source"]
cases["interaction_direction_reversed"] = run(e)
e = resolved(); e.interactions["I001_PhysicianToEHR"]["data"] = []
cases["interaction_exchanges_no_concept"] = run(e)
e = resolved(); e.contexts[ctx]["activeActors"].remove("Physician"); e.actors["Physician"]["responsibleFor"] = []
cases["actor_neither_active_nor_responsible"] = run(e)
e = resolved(); e.constraints["C002_Prescribing"] = e.constraints.pop("C002_FDA")
for x in e.contexts.values(): x["activeConstraints"] = ["C002_Prescribing" if c == "C002_FDA" else c for c in x["activeConstraints"]]
for a in e.actors.values(): a["subjectTo"] = ["C002_Prescribing" if c == "C002_FDA" else c for c in a["subjectTo"]]
q = copy.deepcopy(q0); q.hard_constraints = ["C002_Prescribing"]
cases["constraint_identifier_renamed"] = run(e, q)
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "v100_targeted.json").write_text(json.dumps(cases, indent=2))
print(json.dumps(cases, indent=2))
