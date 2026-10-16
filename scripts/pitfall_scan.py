#!/usr/bin/env python3
"""Local pitfall scan following a subset of the OOPS! pitfall catalogue
(Poveda-Villalon et al., 2014). The OOPS! web service is not called; the
checks below are re-implemented so that they run offline and reproducibly.

P04 unconnected ontology elements     P08 missing annotations (label/definition)
P10 missing disjointness              P11 missing domain or range
P13 inverse relationships not declared (informative)
P22 inconsistent naming conventions   P41 no license declared

The scan is applied to REO v1.0.0 (baseline copy) and to v1.1.0 (core +
derivation module). Writes results/pitfall_results.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, Namespace, URIRef

ROOT = Path(__file__).resolve().parents[1]
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
DCT = Namespace("http://purl.org/dc/terms/")
REO = "http://re-environment-onto.org/ontology#"


def scan(files) -> dict:
    g = Graph()
    for f in files:
        g.parse(f, format="turtle")
    own = lambda s: isinstance(s, URIRef) and str(s).startswith(REO)
    classes = {s for s in g.subjects(RDF.type, OWL.Class) if own(s)}
    oprops = {s for s in g.subjects(RDF.type, OWL.ObjectProperty) if own(s)}
    dprops = {s for s in g.subjects(RDF.type, OWL.DatatypeProperty) if own(s)}
    props = oprops | dprops
    used = set()
    for p in (RDFS.subClassOf, RDFS.domain, RDFS.range, OWL.disjointWith, OWL.equivalentClass):
        for s, o in g.subject_objects(p):
            used |= {s, o}
    for lst in g.objects(None, OWL.members):
        used |= set(g.items(lst))
    p04 = sorted(str(c).split("#")[1] for c in classes if c not in used)
    p08 = sorted(str(t).split("#")[1] for t in classes | props
                 if not (set(g.objects(t, RDFS.label)) and (set(g.objects(t, SKOS.definition)) | set(g.objects(t, RDFS.comment)))))
    disjoint = set()
    for s, o in g.subject_objects(OWL.disjointWith):
        disjoint |= {s, o}
    for lst in g.objects(None, OWL.members):
        disjoint |= set(g.items(lst))
    top = {c for c in classes if not any(own(o) for o in g.objects(c, RDFS.subClassOf))}
    p10 = sorted(str(c).split("#")[1] for c in top if c not in disjoint)
    p11 = sorted(str(p).split("#")[1] for p in props
                 if not (set(g.objects(p, RDFS.domain)) and set(g.objects(p, RDFS.range))))
    p13 = sorted(str(p).split("#")[1] for p in oprops
                 if not set(g.objects(p, OWL.inverseOf)) and not set(g.subjects(OWL.inverseOf, p)))
    p22 = sorted([str(c).split("#")[1] for c in classes if not re.match(r"^[A-Z][A-Za-z0-9]*$", str(c).split("#")[1])] +
                 [str(p).split("#")[1] for p in props if not re.match(r"^[a-z][A-Za-z0-9]*$", str(p).split("#")[1])])
    onts = list(g.subjects(RDF.type, OWL.Ontology))
    p41 = [str(o) for o in onts if not (set(g.objects(o, DCT.license)))]
    return {"classes": len(classes), "properties": len(props),
            "P04_unconnected": p04, "P08_missing_annotations": p08, "P10_top_classes_without_disjointness": p10,
            "P11_missing_domain_or_range": p11, "P13_no_inverse_declared_count": len(p13),
            "P22_naming": p22, "P41_no_license": p41}


def main() -> int:
    base = ROOT / "evaluation" / "baseline-v1.0.0" / "reo-core-1.0.0.ttl"
    out = {"v1.0.0": scan([base]),
           "v1.1.0": scan([ROOT / "ontology" / "reo-core.ttl", ROOT / "ontology" / "reo-derivation.ttl"])}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "pitfall_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for v, r in out.items():
        print(v, {k: (len(x) if isinstance(x, list) else x) for k, x in r.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
