#!/usr/bin/env python3
"""Identity-migration cases: rename, split and merge of environment elements.

Each case builds a successor snapshot E1 from E0 (hospital + extension) in
which the changed element is replaced and linked to its successor(s) with
reo:supersededBy. For every requirement, the script compares

* the baseline decision on E0;
* a naive re-derivation on E1 that ignores identity (annotations unchanged);
* an identity-aware re-derivation that rewrites references through the
  supersession map (a split is resolved only if the referenced properties
  identify the successor; otherwise the requirement goes to review);

and the records selected by direct impact analysis (touched-identifier diff).
A test-only requirement R011 references the split concept without a property.

Writes results/migration_results.json.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import rdflib
from rdflib import RDF, RDFS, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reo_checker as R  # noqa: E402

REO, EX = R.REO, R.EX
EXAMPLE = ROOT / "examples" / "medical-emergency"


def e(x):
    return EX[x]


def rename(g, old, new):
    for s, p, o in list(g.triples((e(old), None, None))):
        g.remove((s, p, o)); g.add((e(new), p, o))
    for s, p, o in list(g.triples((None, None, e(old)))):
        g.remove((s, p, o)); g.add((s, p, e(new)))
    g.add((e(old), REO.supersededBy, e(new)))


def case_rename(g):
    rename(g, "C002_FDA", "C002_PrescribingAuthority")


def case_split(g):
    old = e("D002_Patient")
    for s, p, o in list(g.triples((old, None, None))) + list(g.triples((None, None, old))):
        g.remove((s, p, o))
    for cid, name, props in (("D002a_PatientIdentity", "Patient identity", ["Prop_PatientId", "Prop_MedicalHistory"]),
                             ("D002b_PatientMedicationProfile", "Patient medication profile",
                              ["Prop_Allergies", "Prop_CurrentMedications"])):
        g.add((e(cid), RDF.type, REO.DomainConcept))
        g.add((e(cid), REO.conceptId, Literal(cid)))
        g.add((e(cid), REO.conceptName, Literal(name)))
        for p in props:
            g.add((e(cid), REO.hasProperty, e(p)))
        g.add((e("I001_PhysicianToEHR"), REO.exchangesData, e(cid)))
        g.add((old, REO.supersededBy, e(cid)))
    g.add((e("D002a_PatientIdentity"), REO.hasInvariant, e("Inv_PatientIdUnique")))
    g.add((e("D002b_PatientMedicationProfile"), REO.relatedTo, e("D001_Medication")))
    g.add((e("D001_Medication"), REO.relatedTo, e("D002b_PatientMedicationProfile")))


def case_merge(g):
    new = e("Action_DispenseVerified")
    g.add((new, RDF.type, REO.Action))
    g.add((new, RDFS.label, Literal("dispense_verified")))
    for old in ("Action_VerifyPrescription", "Action_Dispense"):
        for s, p, o in list(g.triples((e(old), None, None))) + list(g.triples((None, None, e(old)))):
            g.remove((s, p, o))
        g.add((e(old), REO.supersededBy, new))
    g.add((e("Pharmacist"), REO.hasCapability, new))


CASES = {"rename_C002": case_rename, "split_D002": case_split, "merge_pharmacist_actions": case_merge}


def main() -> int:
    g0 = R.load_graph([EXAMPLE / "hospital.ttl", EXAMPLE / "hospital-extension.ttl"])
    env0 = R.project(g0)
    reqs = R.load_requirements(R.load_graph([EXAMPLE / "hospital-requirements.ttl"]))
    reqs.append(R.Requirement(rid="R011", text="The Physician shall access the Patient record before prescribing.",
                              seed_goal="G003", context="X001_EmergencyDept", actor="Physician",
                              actions=["Action_AccessRecords"], concepts=["D002_Patient"],
                              interaction="I001_PhysicianToEHR", interaction_source="Physician"))
    base = {q.rid: R.validate(env0, q) for q in reqs}
    out = {"baseline": {rid: r.state for rid, r in base.items()}, "cases": {}}
    ok = True
    for name, fn in CASES.items():
        g1 = deepcopy(g0); fn(g1)
        env1 = R.project(g1)
        mapping = R.supersession_map(g1)
        delta = R.touched_identifiers(g0, g1)
        selected = sorted(R.direct_reevaluation(delta, {rid: r.trace for rid, r in base.items()}))
        rows = {}
        for q in reqs:
            naive = R.validate(env1, q).state
            q2, notes = R.migrate_requirement(q, env1, mapping)
            if any(n.startswith("AMBIGUOUS") for n in notes):
                aware = R.PENDING_REVIEW
            else:
                aware = R.validate(env1, q2).state
            rows[q.rid] = {"baseline": base[q.rid].state, "naive": naive, "identity_aware": aware,
                           "selected_for_reevaluation": q.rid in selected, "migration_notes": notes}
        preserved = sum(r["identity_aware"] == r["baseline"] for r in rows.values())
        spurious_naive = sum(r["naive"] != r["baseline"] for r in rows.values())
        ambiguous = [rid for rid, r in rows.items() if any(n.startswith("AMBIGUOUS") for n in r["migration_notes"])]
        affected_refs = [rid for rid, r in rows.items() if r["migration_notes"]]
        missed = [rid for rid in affected_refs if not rows[rid]["selected_for_reevaluation"]]
        ok &= not missed
        out["cases"][name] = {"supersession": mapping, "touched": sorted(delta), "selected": selected,
                              "requirements_with_migrated_references": affected_refs,
                              "missed_by_impact_query": missed, "ambiguous": ambiguous,
                              "decisions_preserved_identity_aware": preserved,
                              "decisions_changed_naive": spurious_naive, "rows": rows}
        print(f"{name:26s} selected={len(selected):2d} migrated={affected_refs} naive_changed={spurious_naive} "
              f"aware_preserved={preserved}/{len(rows)} ambiguous={ambiguous} missed={missed}")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "migration_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
