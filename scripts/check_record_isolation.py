#!/usr/bin/env python3
"""Check that requirement annotations and decision records do not touch the environment.

Decision records are stored with the environment (Section V-E), but the
touched-identifier diff (Section III-F) and the snapshot hash are defined over the
environment snapshot only. This script adds the annotations of the ten requirements
and the PROV-O records of their assessments to the environment graph and checks that

* the touched identifiers are empty and the snapshot hash is unchanged;
* a raw diff over all triples (without the separation) would have touched many
  environment identifiers, e.g. ex:Physician through ``reo:consulted``;
* the same holds for a single untyped record triple such as
  ``ex:ValidationActivity1 reo:consulted ex:Physician``.

Writes results/record_isolation.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import rdflib
from rdflib import BNode, RDF, URIRef

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reo_checker as R  # noqa: E402

EXAMPLE = ROOT / "examples" / "medical-emergency"


def raw_touched(g_old, g_new):
    norm = lambda g: {(s, p, o) for s, p, o in g if not isinstance(s, BNode) and not isinstance(o, BNode)}
    out = set()
    for s, p, o in norm(g_old) ^ norm(g_new):
        out.add(R.local(s))
        if isinstance(o, URIRef) and p != RDF.type:
            out.add(R.local(o))
    return out


def main() -> int:
    env_g = R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"])
    req_g = R.load_graph([EXAMPLE / "hospital-requirements.ttl"])
    env = R.project(env_g)
    records = R.record_graph([R.validate(env, q) for q in R.load_requirements(req_g)])
    union = rdflib.Graph()
    union += env_g
    union += req_g
    union += records
    env_ids = {R.local(s) for s in env_g.subjects() if isinstance(s, URIRef)}
    raw = raw_touched(env_g, union)
    single = rdflib.Graph()
    single += env_g
    single.add((R.EX.ValidationActivity1, R.REO.consulted, R.EX.Physician))
    out = {
        "added_triples": len(union) - len(env_g),
        "annotation_triples": len(req_g),
        "record_triples": len(records),
        "touched_identifiers": sorted(R.touched_identifiers(env_g, union)),
        "snapshot_hash_unchanged": R.snapshot_hash(env_g) == R.snapshot_hash(union),
        "raw_diff_touched_environment_identifiers": sorted(raw & env_ids),
        "single_untyped_record_triple": {
            "touched_identifiers": sorted(R.touched_identifiers(env_g, single)),
            "raw_diff_touched": sorted(raw_touched(env_g, single)),
            "snapshot_hash_unchanged": R.snapshot_hash(env_g) == R.snapshot_hash(single)},
    }
    ok = (not out["touched_identifiers"] and out["snapshot_hash_unchanged"]
          and not out["single_untyped_record_triple"]["touched_identifiers"]
          and out["single_untyped_record_triple"]["snapshot_hash_unchanged"])
    out["pass"] = ok
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "record_isolation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in out.items()}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
