#!/usr/bin/env python3
"""Regenerate reproducible REO v1.1.0 artifact metrics from the Turtle corpus.
Writes results/artifact_metrics.json and generated/reo_inventory.{csv,tex}."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from rdflib import OWL, RDF, RDFS, SH, Graph, URIRef

ROOT = Path(__file__).resolve().parents[1]
REO = "http://re-environment-onto.org/ontology#"
MODULES = {"core": "ontology/reo-core.ttl", "derivation": "ontology/reo-derivation.ttl",
           "shapes": "ontology/reo-shapes.ttl", "derivation_shapes": "ontology/reo-derivation-shapes.ttl"}


def load(*paths) -> Graph:
    g = Graph()
    for p in paths:
        g.parse(ROOT / p, format="turtle")
    return g


def own(s):
    return isinstance(s, URIRef) and str(s).startswith(REO)


def onto_metrics(g: Graph) -> dict:
    return {"triples": len(g),
            "classes": len({s for s in g.subjects(RDF.type, OWL.Class) if own(s)}),
            "object_properties": len({s for s in g.subjects(RDF.type, OWL.ObjectProperty) if own(s)}),
            "datatype_properties": len({s for s in g.subjects(RDF.type, OWL.DatatypeProperty) if own(s)}),
            "named_individuals": len({s for s in g.subjects(RDF.type, OWL.NamedIndividual) if own(s)}),
            "restrictions": len(set(g.subjects(RDF.type, OWL.Restriction))),
            "disjointness_axioms": len(set(g.subject_objects(OWL.disjointWith)))
            + len(set(g.subjects(RDF.type, OWL.AllDisjointClasses)))}


def shape_metrics(g: Graph) -> dict:
    return {"triples": len(g), "node_shapes": len(set(g.subjects(RDF.type, SH.NodeShape))),
            "property_shapes": len(set(g.subjects(SH.path, None))),
            "sparql_constraints": len(set(g.objects(None, SH.sparql)))}


def main() -> None:
    files = sorted(list((ROOT / "ontology").glob("*.ttl")) + list((ROOT / "examples").glob("**/*.ttl"))
                   + list((ROOT / "test-cases").glob("**/*.ttl")))
    per_file = {p.relative_to(ROOT).as_posix(): len(load(p.relative_to(ROOT))) for p in files}
    m = {"reo_version": "1.1.0", "turtle_file_count": len(files), "total_triples": sum(per_file.values()),
         "triples_by_file": per_file,
         "core": onto_metrics(load(MODULES["core"])), "derivation": onto_metrics(load(MODULES["derivation"])),
         "ontology_total": onto_metrics(load(MODULES["core"], MODULES["derivation"])),
         "shapes": shape_metrics(load(MODULES["shapes"])),
         "derivation_shapes": shape_metrics(load(MODULES["derivation_shapes"]))}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "artifact_metrics.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    # Vocabulary inventory (domain, range, module) for the supplementary material.
    rows = []
    for mod in ("core", "derivation"):
        g = load(MODULES[mod])
        for kind, t in (("Class", OWL.Class), ("Object property", OWL.ObjectProperty),
                        ("Datatype property", OWL.DatatypeProperty)):
            for s in sorted({x for x in g.subjects(RDF.type, t) if own(x)}, key=str):
                sh = lambda v: "--" if v is None else str(v).replace(REO, "reo:").replace(
                    "http://www.w3.org/2001/XMLSchema#", "xsd:").replace("http://www.w3.org/2002/07/owl#", "owl:")
                rows.append({"module": mod, "kind": kind, "element": sh(s),
                             "domain_or_parent": sh(g.value(s, RDFS.domain) or next(
                                 (o for o in g.objects(s, RDFS.subClassOf) if isinstance(o, URIRef)), None)),
                             "range": sh(g.value(s, RDFS.range)),
                             "definition": str(g.value(s, URIRef("http://www.w3.org/2004/02/skos/core#definition")) or "")})
    (ROOT / "generated").mkdir(exist_ok=True)
    with open(ROOT / "generated" / "reo_inventory.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(json.dumps({k: v for k, v in m.items() if k != "triples_by_file"}, indent=1))


if __name__ == "__main__":
    main()
