#!/usr/bin/env python3
"""OWL 2 DL consistency and classification checks with HermiT (via Owlready2).

Positive cases: the ontology modules alone, and together with the example,
its extension, the requirement set and the generated decision records.
Negative cases: eight injected modelling errors that an OWL reasoner should
detect. Each negative case is also run against the REO v1.0.0 core
(``--baseline`` path) to show what the v1.1.0 axioms add.

Writes results/reasoner_results.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from rdflib import OWL, Graph, Literal, Namespace, RDF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reo_checker as R  # noqa: E402

REO = Namespace("http://re-environment-onto.org/ontology#")
EX = Namespace("http://hospital.example.org#")
REC = Namespace("http://hospital.example.org/requirements/records#")
EXAMPLE = ROOT / "examples" / "medical-emergency"


def run_hermit(g: Graph):
    from owlready2 import World, sync_reasoner, OwlReadyInconsistentOntologyError
    with tempfile.NamedTemporaryFile(suffix=".owl", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        # All modules are loaded locally; owl:imports would make Owlready2 try
        # to download the (non-resolving) ontology IRIs.
        g = Graph() + g
        g.remove((None, OWL.imports, None))
        g.serialize(destination=str(path), format="xml")
        world = World()
        onto = world.get_ontology(path.as_uri()).load()
        try:
            sync_reasoner([onto], debug=0)
        except OwlReadyInconsistentOntologyError:
            return {"consistent": False, "unsatisfiable_classes": []}
        unsat = sorted(str(c.iri) for c in world.inconsistent_classes()
                       if str(c.iri) != "http://www.w3.org/2002/07/owl#Nothing")
        return {"consistent": True, "unsatisfiable_classes": unsat}
    finally:
        path.unlink(missing_ok=True)


def records_graph() -> Graph:
    g = R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"])
    env = R.project(g)
    reqs = R.load_requirements(R.load_graph([EXAMPLE / "hospital-requirements.ttl"]))
    return R.record_graph([R.validate(env, q) for q in reqs])


NEGATIVES = {
    "N1_actor_typed_human_and_system": lambda g: g.add((EX.Physician, RDF.type, REO.SystemActor)),
    "N2_goal_used_as_interaction_source": lambda g: g.add((EX.I001_PhysicianToEHR, REO.hasSource, EX.G002)),
    "N3_goal_also_typed_constraint": lambda g: g.add((EX.G002, RDF.type, REO.Constraint)),
    "N4_actor_responsible_for_domain_concept": lambda g: g.add((EX.Physician, REO.isResponsibleFor, EX.D001_Medication)),
    "N5_uncertainty_blocks_actor": lambda g: g.add((EX.U001_DrugDBFrequency, REO.blocks, EX.Physician)),
    "N6_second_interaction_source": lambda g: g.add((EX.I001_PhysicianToEHR, REO.hasSource, EX.Pharmacist)),
    "N7_record_with_two_decisions": lambda g: (g.add((REC["R001-x"], REO.hasDecision, REO.Accepted)),
                                               g.add((REC["R001-x"], REO.hasDecision, REO.Rejected))),
    "N8_requirement_seeded_by_actor": lambda g: (g.add((EX.R_bad, REO.hasSeedGoal, EX.Physician)),
                                                 g.add((EX.R_bad, RDF.type, REO.Requirement))),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(ROOT / "evaluation" / "baseline-v1.0.0"),
                    help="Directory holding the REO v1.0.0 core ontology and example.")
    args = ap.parse_args()

    core = R.load_graph([ROOT / "ontology" / "reo-core.ttl"])
    deriv = R.load_graph([ROOT / "ontology" / "reo-core.ttl", ROOT / "ontology" / "reo-derivation.ttl"])
    full = R.load_graph(R.ONTOLOGY_FILES + [EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl",
                                           EXAMPLE / "hospital-requirements.ttl"])
    full += records_graph()

    positives = {
        "P1_core": (core, True), "P2_core_plus_derivation": (deriv, True),
        "P3_all_modules_example_extension_requirements_records": (full, True),
    }
    out = {"engine": "HermiT via Owlready2", "positive": {}, "negative": {}}
    ok = True
    for name, (g, expected) in positives.items():
        r = run_hermit(g)
        r["triples"] = len(g)
        r["pass"] = r["consistent"] == expected and not r["unsatisfiable_classes"]
        ok &= r["pass"]
        out["positive"][name] = r
    base_v10 = None
    if args.baseline:
        b = Path(args.baseline)
        base_v10 = R.load_graph([b / "reo-core-1.0.0.ttl", b / "hospital-1.0.0.ttl"])
    for name, mutate in NEGATIVES.items():
        g = Graph(); g += full
        mutate(g)
        r = run_hermit(g)
        entry = {"v1_1_detected": not r["consistent"]}
        ok &= entry["v1_1_detected"]
        if base_v10 is not None and not name.startswith(("N7", "N8")):
            gb = Graph(); gb += base_v10
            mutate(gb)
            entry["v1_0_detected"] = not run_hermit(gb)["consistent"]
        out["negative"][name] = entry
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "reasoner_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
