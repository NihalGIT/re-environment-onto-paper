#!/usr/bin/env python3
"""Execute a frozen, LLM-authored test suite (study E1) against the EC-RE checker.

Input: one or more author files (JSON) written by LLM evaluators from the
specification pack only (see ../PROTOCOL.md). Each file holds
  * scenarios: Turtle snippets to remove from / add to the example environment
    (hospital.ttl + hospital-extension.ttl), optional extra requirement
    annotations, and the expected decision state for any requirement;
  * cqs: competency questions with a SPARQL encoding and the expected answer.

For every scenario the script applies the change, runs the reference checker
and the independent SPARQL oracle, and compares each expected state with the
observed one. Author files are never modified. Items that cannot be executed
(Turtle syntax errors, unknown states, SPARQL errors) stay in the denominator
and are reported as invalid.

Re-derivation follows the specification (Section III-F): requirement references
are first rewritten through reo:supersededBy, and a requirement whose reference
is split ambiguously goes to pending review. The first execution of the frozen
suites omitted this step (``--no-migration`` reproduces it; see ../README.md).

Usage: python run_llm_suite.py [--no-migration] <out.json> <author_file.json> [...]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import rdflib
from rdflib import URIRef

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reo_checker as R  # noqa: E402
import sparql_oracle as O  # noqa: E402

EXAMPLE = ROOT / "examples" / "medical-emergency"
ENV_FILES = [EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"]
REQ_FILE = EXAMPLE / "hospital-requirements.ttl"
PFX = ("@prefix reo: <http://re-environment-onto.org/ontology#> .\n"
       "@prefix ex: <http://hospital.example.org#> .\n"
       "@prefix req: <http://hospital.example.org/requirements#> .\n"
       "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
       "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
       "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
       "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n")
SPARQL_PFX = "\n".join(l.replace("@prefix", "PREFIX").rstrip(" .") for l in PFX.strip().splitlines()) + "\n"
STATES = set(R.STATES)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snippet(ttl: str) -> rdflib.Graph:
    g = rdflib.Graph()
    if ttl and ttl.strip():
        g.parse(data=PFX + ttl, format="turtle")
    return g


def norm_state(s) -> str:
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def cell(v) -> str:
    return R.local(v) if isinstance(v, URIRef) else str(v)


MIGRATE = True


def derive(env, q, mapping):
    res = R.rederive(env, q, mapping if MIGRATE else {})
    return res.state, res.justifications, sorted(res.trace)


def run_scenario(sc, base, reqg, onto):
    row = {"id": sc["id"], "description": sc.get("description", ""), "status": "ok", "items": []}
    try:
        rem, add = snippet(sc.get("remove_turtle", "")), snippet(sc.get("add_turtle", ""))
        radd = snippet(sc.get("add_requirements_turtle", ""))
    except Exception as e:  # noqa: BLE001 - any parse error makes the scenario invalid
        row["status"] = "invalid_encoding"; row["error"] = str(e).splitlines()[0][:300]
        for rid, exp in sc.get("expected", {}).items():
            row["items"].append({"requirement": rid, "expected": norm_state(exp), "checker": None,
                                 "oracle": None, "match": False, "invalid": True})
        return row
    g = rdflib.Graph(); g += base
    row["remove_absent"] = sum(1 for t in rem if t not in g)
    for t in rem:
        g.remove(t)
    for t in add:
        g.add(t)
    rg = rdflib.Graph(); rg += reqg; rg += radd
    env = R.project(g)
    reqs = {q.rid: q for q in R.load_requirements(rg)}
    og = rdflib.Graph(); og += onto; og += g; og += rg
    oracle = O.decide(og)
    mapping = R.supersession_map(g)
    for rid, exp in sc.get("expected", {}).items():
        e = norm_state(exp)
        item = {"requirement": rid, "expected": e}
        if rid not in reqs or e not in STATES:
            item.update(checker=None, oracle=oracle.get(rid), match=False, invalid=True,
                        reason="unknown requirement" if rid not in reqs else "unknown state name")
        else:
            state, just, trace = derive(env, reqs[rid], mapping)
            item.update(checker=state, oracle=oracle.get(rid), match=state == e,
                        justifications=just, trace=trace, migrated=bool(MIGRATE and mapping))
        row["items"].append(item)
    return row


def run_cq(cq, g):
    row = {"id": cq["id"], "question": cq.get("question", ""), "category": cq.get("category", "")}
    q = cq.get("sparql", "")
    try:
        res = g.query(SPARQL_PFX + q if "PREFIX" not in q.upper() else q)
    except Exception as e:  # noqa: BLE001
        row.update(status="invalid_query", error=str(e).splitlines()[0][:300], match=False)
        return row
    exp = cq.get("expected")
    if res.type == "ASK":
        obs = bool(res.askAnswer)
        row.update(status="ok", kind="ask", observed=obs, expected=exp,
                   match=isinstance(exp, bool) and obs == exp)
    else:
        obs = sorted({tuple(cell(v) for v in r) for r in res})
        if isinstance(exp, list):
            e = sorted({tuple(str(x) for x in (r if isinstance(r, list) else [r])) for r in exp})
        else:
            e = None
        row.update(status="ok", kind="select", observed=[list(r) for r in obs],
                   expected=[list(r) for r in e] if e is not None else exp, match=e == obs)
    return row


def main(*argv):
    global MIGRATE
    argv = list(argv)
    if "--no-migration" in argv:
        MIGRATE = False; argv.remove("--no-migration")
    out_path, *author_files = argv
    base = R.load_graph(ENV_FILES)
    reqg = R.load_graph([REQ_FILE])
    onto = R.load_graph(R.ONTOLOGY_FILES)
    cq_graph = R.load_graph(R.ONTOLOGY_FILES + ENV_FILES + [REQ_FILE])
    report = {"policy_version": R.POLICY_VERSION, "identity_migration": MIGRATE, "authors": []}
    for f in author_files:
        f = Path(f)
        suite = json.loads(f.read_text(encoding="utf-8"))
        a = {"file": f.name, "sha256": sha256(f), "author_code": suite.get("author_code"),
             "self_reported_model": suite.get("self_reported_model"),
             "scenarios": [run_scenario(sc, base, reqg, onto) for sc in suite.get("scenarios", [])],
             "cqs": [run_cq(cq, cq_graph) for cq in suite.get("cqs", [])]}
        items = [i for s in a["scenarios"] for i in s["items"]]
        a["summary"] = {
            "scenarios": len(a["scenarios"]),
            "scenarios_invalid": sum(s["status"] != "ok" for s in a["scenarios"]),
            "expectations": len(items),
            "expectations_invalid": sum(bool(i.get("invalid")) for i in items),
            "matches": sum(bool(i["match"]) for i in items),
            "checker_oracle_disagreements": sum(1 for i in items if i.get("checker") and not i.get("migrated")
                                                and i["checker"] != i["oracle"]),
            "scenarios_all_match": sum(all(i["match"] for i in s["items"]) for s in a["scenarios"]),
            "cqs": len(a["cqs"]),
            "cqs_invalid": sum(c["status"] != "ok" for c in a["cqs"]),
            "cqs_match": sum(bool(c["match"]) for c in a["cqs"]),
        }
        report["authors"].append(a)
    Path(out_path).write_text(json.dumps(report, indent=1), encoding="utf-8")
    for a in report["authors"]:
        print(a["author_code"], json.dumps(a["summary"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
