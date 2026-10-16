#!/usr/bin/env python3
"""Run an externally authored mutation suite (evaluation/independent-evaluation).

Each mutation lists Turtle snippets to remove/add (prefixes reo:, ex: are predefined)
and the expected decision for any subset of requirements. The script applies each
mutation to the base files, runs the checker and the SPARQL oracle, and reports
expected vs. observed without modifying the suite file. The checker re-derives
with identity migration (reo:supersededBy); the SPARQL oracle encodes the
decision policy only, so for mutations with supersession links its column is
the decision without migration."""
import json, sys
from pathlib import Path
import rdflib
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R
import sparql_oracle as O
PFX = "@prefix reo: <http://re-environment-onto.org/ontology#> .\n@prefix ex: <http://hospital.example.org#> .\n" \
      "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"

def snippet(ttl):
    g = rdflib.Graph()
    if ttl and ttl.strip():
        g.parse(data=PFX + ttl, format="turtle")
    return g

def main(path):
    suite = json.loads(Path(path).read_text(encoding="utf-8"))
    base = R.load_graph([ROOT / f for f in suite["base_files"]])
    reqg = R.load_graph([ROOT / suite["requirements_file"]])
    reqs = R.load_requirements(reqg)
    onto = R.load_graph(R.ONTOLOGY_FILES)
    report, agree, total = [], 0, 0
    for m in suite["mutations"]:
        g = rdflib.Graph(); g += base
        for t in snippet(m["encoding"].get("remove_turtle")): g.remove(t)
        for t in snippet(m["encoding"].get("add_turtle")): g.add(t)
        env = R.project(g)
        mapping = R.supersession_map(g)  # identity migration before re-derivation
        og = rdflib.Graph(); og += onto; og += g; og += reqg
        oracle = O.decide(og)
        for q in reqs:
            if q.rid not in m["expected"]:
                continue
            obs = R.rederive(env, q, mapping).state
            ok = obs == m["expected"][q.rid]
            agree += ok; total += 1
            report.append({"mutation": m["id"], "requirement": q.rid, "expected": m["expected"][q.rid],
                           "checker": obs, "oracle": oracle[q.rid], "match": ok})
    out = {"suite": suite["suite_id"], "frozen_commit": suite.get("frozen_commit"), "matches": agree,
           "total": total, "rows": report}
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main(sys.argv[1])
