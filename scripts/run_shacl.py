#!/usr/bin/env python3
"""SHACL validation of the example, its extension + requirement set + records,
the three regression fixtures, and five injected cross-view errors.

Configuration: pySHACL, RDFS inference with the ontology modules as the
entailment graph, warnings allowed. The cross-view errors are additionally
validated without inference, because RDFS range inference can satisfy an
sh:class constraint by typing the wrong node.

Writes results/shacl_results.json and the human-readable reports.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Namespace, RDF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reo_checker as R  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")
REO = R.REO
EX = R.EX
EXAMPLE = ROOT / "examples" / "medical-emergency"
SHAPES = R.load_graph([ROOT / "ontology" / "reo-shapes.ttl", ROOT / "ontology" / "reo-derivation-shapes.ttl"])
ONTO = R.load_graph(R.ONTOLOGY_FILES)


def run(g: Graph, inference: str = "rdfs", report: Path | None = None) -> dict:
    from pyshacl import validate
    conforms, rg, text = validate(g, shacl_graph=SHAPES, ont_graph=ONTO, inference=inference,
                                  allow_warnings=True)
    sev = list(rg.objects(None, SH.resultSeverity))
    comps = sorted({str(o).split("#")[-1] for o in rg.objects(None, SH.sourceConstraintComponent)})
    if report:
        report.write_text(text, encoding="utf-8")
    return {"conforms": bool(conforms), "violations": sum(s == SH.Violation for s in sev),
            "warnings": sum(s == SH.Warning for s in sev), "components": comps, "triples": len(g)}


def main() -> int:
    out = {}
    cases = {
        "main_example": ([EXAMPLE / "hospital.ttl"], EXAMPLE / "validation-report.txt", (True, 0, 1)),
        "fixture_01_success": ([ROOT / "test-cases/01-success/hospital-success.ttl"],
                               ROOT / "test-cases/01-success/report.txt", (True, 0, 0)),
        "fixture_02_warning": ([ROOT / "test-cases/02-success-with-warning/hospital-warning.ttl"],
                               ROOT / "test-cases/02-success-with-warning/report.txt", (True, 0, 1)),
        "fixture_03_violations": ([ROOT / "test-cases/03-violations/hospital-violations.ttl"],
                                  ROOT / "test-cases/03-violations/report.txt", (False, None, None)),
    }
    ok = True
    for name, (files, rep, (c, v, w)) in cases.items():
        r = run(R.load_graph(files), report=rep)
        r["pass"] = r["conforms"] == c and (v is None or r["violations"] == v) and (w is None or r["warnings"] == w)
        ok &= r["pass"]
        out[name] = r
    # Example + extension + requirements + generated decision records.
    g = R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl",
                      EXAMPLE / "hospital-requirements.ttl"])
    env = R.project(R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"]))
    reqs = R.load_requirements(g)
    g += R.record_graph([R.validate(env, q) for q in reqs])
    r = run(g, report=ROOT / "results" / "full-validation-report.txt")
    r["pass"] = r["conforms"] and r["violations"] == 0
    ok &= r["pass"]
    out["example_extension_requirements_records"] = r

    # Injected cross-view errors (same as the reasoner negatives N2-N6).
    errors = {
        "goal_used_as_interaction_source": (EX.I001_PhysicianToEHR, REO.hasSource, EX.G002),
        "goal_also_typed_constraint": (EX.G002, RDF.type, REO.Constraint),
        "actor_responsible_for_domain_concept": (EX.Physician, REO.isResponsibleFor, EX.D001_Medication),
        "uncertainty_blocks_actor": (EX.U001_DrugDBFrequency, REO.blocks, EX.Physician),
        "second_interaction_source": (EX.I001_PhysicianToEHR, REO.hasSource, EX.Pharmacist),
    }
    out["cross_view_errors"] = {}
    for name, triple in errors.items():
        g = R.load_graph([EXAMPLE / "hospital.ttl"]); g.add(triple)
        out["cross_view_errors"][name] = {"rdfs": run(g, "rdfs"), "none": run(g, "none")}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "shacl_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for k, v in out.items():
        if k != "cross_view_errors":
            print(f"{k:42s} conforms={v['conforms']!s:5s} violations={v['violations']:3d} warnings={v['warnings']} pass={v.get('pass')}")
    for k, v in out["cross_view_errors"].items():
        print(f"  {k:40s} rdfs: V={v['rdfs']['violations']:2d}  none: V={v['none']['violations']:2d}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
