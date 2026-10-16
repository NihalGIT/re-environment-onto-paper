#!/usr/bin/env python3
"""Run the competency-question suite (v1.1) and measure vocabulary coverage.

* ``base`` questions run on the core ontology + hospital.ttl (v1.0.0 suite);
* ``full`` questions run on core + derivation modules, hospital.ttl, its
  extension, the requirement set and the generated PROV-O decision records.

SELECT answers are compared as sorted rows of local names; ASK answers as
booleans. Coverage = share of REO classes and properties that occur in at
least one question. Writes results/cq_results.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rdflib import OWL, RDF, Graph, Literal, URIRef

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reo_checker as R  # noqa: E402

SUITE = ROOT / "evaluation" / "competency-questions" / "cq_suite_v1.1.json"
EXAMPLE = ROOT / "examples" / "medical-emergency"


def local(v) -> str:
    if isinstance(v, URIRef):
        s = str(v)
        return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]
    return str(v)


def graphs():
    base = R.load_graph([ROOT / "ontology" / "reo-core.ttl", EXAMPLE / "hospital.ttl"])
    env = R.project(R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"]))
    full = R.load_graph(R.ONTOLOGY_FILES + [EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl",
                                           EXAMPLE / "hospital-requirements.ttl"])
    reqs = R.load_requirements(full)
    full += R.record_graph([R.validate(env, q) for q in reqs])
    return {"base": base, "full": full}


def vocabulary() -> dict:
    g = R.load_graph(R.ONTOLOGY_FILES)
    vocab = {}
    for t, kind in ((OWL.Class, "classes"), (OWL.ObjectProperty, "object_properties"),
                    (OWL.DatatypeProperty, "datatype_properties")):
        for s in g.subjects(RDF.type, t):
            if isinstance(s, URIRef) and str(s).startswith(str(R.REO)):
                vocab[local(s)] = kind
    return vocab


def main() -> int:
    gs = graphs()
    specs = json.loads(SUITE.read_text(encoding="utf-8"))
    results, passed, used = [], 0, set()
    for spec in specs:
        res = gs[spec["graph"]].query(spec["query"])
        observed = bool(res.askAnswer) if spec["kind"] == "ask" else sorted([[local(v) for v in row] for row in res])
        ok = observed == spec["expected"]
        passed += ok
        used |= set(re.findall(r"reo:([A-Za-z]+)", spec["query"]))
        results.append({**{k: spec[k] for k in ("id", "category", "origin", "graph", "question")},
                        "expected": spec["expected"], "observed": observed, "pass": ok})
        print(f"{spec['id']:7s} {spec['category']:12s} {'PASS' if ok else 'FAIL'}")
        if not ok:
            print("   expected", spec["expected"]); print("   observed", observed)
    vocab_kind = vocabulary()
    vocab = set(vocab_kind)
    covered = sorted(used & vocab)
    per_kind = {}
    for term, kind in vocab_kind.items():
        k = per_kind.setdefault(kind, [0, 0]); k[1] += 1; k[0] += term in used
    by_cat = {}
    for r in results:
        c = by_cat.setdefault(r["category"], [0, 0]); c[0] += r["pass"]; c[1] += 1
    out = {"passed": passed, "total": len(specs), "by_category": by_cat,
           "vocabulary_size": len(vocab), "vocabulary_covered": len(covered), "coverage_by_kind": per_kind,
           "covered_terms": covered, "uncovered_terms": sorted(vocab - used), "results": results}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "cq_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Competency questions: {passed}/{len(specs)}; vocabulary coverage {len(covered)}/{len(vocab)} {per_kind}")
    return 0 if passed == len(specs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
