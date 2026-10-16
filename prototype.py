#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression harness for the REO derivation contract (v1.1.0).

* 18 decision scenarios (the original scenario set, now applied end-to-end as
  RDF graph mutations: mutate the Turtle graph -> SHACL -> project -> decide);
* 4 direct impact queries on the baseline record of R001;
* targeted regressions covering the corrections made in this revision.

For every case the SHACL verdict of the mutated graph is recorded next to the
requirement-level decision, which makes the difference between graph
conformance and requirement acceptance observable.

Usage:  python prototype.py            (writes evaluation_results.csv and
                                         results/regression_results.json)
"""
from __future__ import annotations

import csv
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import rdflib
from rdflib import RDF, Literal, URIRef

import reo_checker as R
from reo_checker import EX, REO

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "examples" / "medical-emergency" / "hospital.ttl"
REQS = ROOT / "examples" / "medical-emergency" / "hospital-requirements.ttl"
SHAPES = [ROOT / "ontology" / "reo-shapes.ttl", ROOT / "ontology" / "reo-derivation-shapes.ttl"]


# ---------------------------------------------------------------------------
# SHACL helper
# ---------------------------------------------------------------------------
_SH = {}


def shacl(g: rdflib.Graph) -> dict:
    from pyshacl import validate
    if "shapes" not in _SH:
        _SH["shapes"] = R.load_graph(SHAPES)
        _SH["onto"] = R.load_graph(R.ONTOLOGY_FILES)
    conforms, rg, _ = validate(g, shacl_graph=_SH["shapes"], ont_graph=_SH["onto"],
                               inference="rdfs", allow_warnings=True)
    sh = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    sev = [o for o in rg.objects(None, sh.resultSeverity)]
    return {"conforms": bool(conforms),
            "violations": sum(1 for s in sev if s == sh.Violation),
            "warnings": sum(1 for s in sev if s == sh.Warning)}


def shacl_verdict(s: dict) -> str:
    if s["violations"]:
        return "non-conforming"
    return "conforming with warning" if s["warnings"] else "conforming"


# ---------------------------------------------------------------------------
# Graph mutation helpers
# ---------------------------------------------------------------------------
def e(x: str) -> URIRef:
    return EX[x]


def set_value(g, s, p, value):
    g.remove((e(s), p, None))
    if value is not None:
        g.add((e(s), p, value))


def drop_subject(g, s):
    g.remove((e(s), None, None))


def baseline_requirement() -> R.Requirement:
    reqs = {q.rid: q for q in R.load_requirements(R.load_graph([REQS]))}
    return deepcopy(reqs["R001"])


@dataclass
class Case:
    suite: str
    name: str
    expected: str
    mutate: Callable[[rdflib.Graph, R.Requirement], Tuple[rdflib.Graph, R.Requirement]]
    note: str = ""


def add_context(g, cid, active_constraints, active_actors, props=()):
    g.add((e(cid), RDF.type, REO.Context))
    g.add((e(cid), REO.contextId, Literal(cid)))
    g.add((e(cid), REO.contextName, Literal(cid)))
    for c in active_constraints:
        g.add((e(cid), REO.hasActiveConstraint, e(c)))
    for a in active_actors:
        g.add((e(cid), REO.hasActiveActor, e(a)))
    for p in props:
        g.add((e(cid), REO.contextProperty, Literal(p)))


def add_constraint(g, cid, level="hard", cls=REO.BusinessConstraint, applies=(), validator=None):
    g.add((e(cid), RDF.type, cls))
    g.add((e(cid), REO.constraintId, Literal(cid)))
    g.add((e(cid), REO.constraintName, Literal(cid)))
    g.add((e(cid), REO.formalExpression, Literal("manual_review")))
    g.add((e(cid), REO.naturalLanguage, Literal("Constraint added by a regression case.")))
    g.add((e(cid), REO.enforcementLevel, Literal(level)))
    for x in applies:
        g.add((e(cid), REO.appliesTo, e(x)))
    if validator:
        g.add((e(cid), REO.validatorKey, Literal(validator)))


def add_uncertainty(g, uid, status, impact, affects=(), blocks=(), cls=REO.AssumptionUncertainty):
    g.add((e(uid), RDF.type, cls))
    g.add((e(uid), REO.uncertaintyId, Literal(uid)))
    g.add((e(uid), REO.uncertaintyName, Literal(uid)))
    g.add((e(uid), REO.subject, Literal(f"Regression uncertainty {uid}")))
    g.add((e(uid), REO.status, Literal(status)))
    g.add((e(uid), REO.impactLevel, Literal(impact)))
    g.add((e(uid), REO.validationPlan, Literal("Analyst review.")))
    for x in affects:
        g.add((e(uid), REO.affects, e(x)))
    for x in blocks:
        g.add((e(uid), REO.blocks, e(x)))


def resolve_u001(g):
    set_value(g, "U001_DrugDBFrequency", REO.status, Literal("validated"))


# ---------------------------------------------------------------------------
# The 18 original decision scenarios (now RDF mutations)
# ---------------------------------------------------------------------------
def original_scenarios() -> List[Case]:
    S = "original-18"
    cases: List[Case] = []

    def m(fn):
        def wrap(g, q):
            fn(g, q)
            return g, q
        return wrap

    cases.append(Case(S, "accepted_freshness_resolved", R.ACCEPTED, m(lambda g, q: resolve_u001(g))))

    def outpatient_exc(g, q, resolve=True):
        add_context(g, "X002_Outpatient", ["C002_FDA"], ["Physician"])
        g.add((e("C001_HIPAA"), REO.hasException, e("X002_Outpatient")))
        if resolve:
            resolve_u001(g)
        q.context = "X002_Outpatient"
    cases.append(Case(S, "accepted_outpatient_exception_and_freshness", R.ACCEPTED, m(outpatient_exc)))

    def soft(g, q):
        resolve_u001(g)
        set_value(g, "C001_HIPAA", REO.enforcementLevel, Literal("soft"))
        g.remove((e("C001_HIPAA"), REO.hasException, None))
    cases.append(Case(S, "accepted_with_reservations_soft_constraint", R.ACCEPTED_WITH_RESERVATIONS, m(soft)))

    cases.append(Case(S, "conditional_baseline_unresolved_freshness", R.CONDITIONAL, m(lambda g, q: None)))
    cases.append(Case(S, "conditional_outpatient_exception_unresolved_freshness", R.CONDITIONAL,
                      m(lambda g, q: outpatient_exc(g, q, resolve=False))))

    cases.append(Case(S, "pending_review_missing_hard_constraint", R.PENDING_REVIEW,
                      m(lambda g, q: drop_subject(g, "C002_FDA"))))

    def orphan(g, q):
        g.add((e("G999_Orphan"), RDF.type, REO.OperationalGoal))
        add_context(g, "X999_EmptyContext", [], [])
        q.__init__(rid="R999", text="An unanchored candidate statement.", seed_goal="G999_Orphan",
                   context="X999_EmptyContext")
    cases.append(Case(S, "pending_review_no_induced_obligations", R.PENDING_REVIEW, m(orphan)))

    def nochecker(g, q):
        resolve_u001(g)
        add_constraint(g, "C900_ManualSafetyReview", applies=["Physician"])
        g.add((e("X001_EmergencyDept"), REO.hasActiveConstraint, e("C900_ManualSafetyReview")))
        q.hard.append("C900_ManualSafetyReview")
    cases.append(Case(S, "pending_review_hard_constraint_without_checker", R.PENDING_REVIEW, m(nochecker)))

    cases.append(Case(S, "rejected_missing_actor", R.REJECTED, m(lambda g, q: drop_subject(g, "Physician"))))
    cases.append(Case(S, "rejected_missing_capability", R.REJECTED,
                      m(lambda g, q: g.remove((e("Physician"), REO.hasCapability, e("Action_Prescribe"))))))
    cases.append(Case(S, "rejected_missing_authority", R.REJECTED,
                      m(lambda g, q: set_value(g, "Physician", REO.authorityLevel, None))))
    cases.append(Case(S, "rejected_missing_domain_concept", R.REJECTED,
                      m(lambda g, q: drop_subject(g, "D001_Medication"))))
    cases.append(Case(S, "rejected_missing_domain_property", R.REJECTED,
                      m(lambda g, q: g.remove((e("D002_Patient"), REO.hasProperty, e("Prop_CurrentMedications"))))))
    cases.append(Case(S, "rejected_missing_interaction", R.REJECTED,
                      m(lambda g, q: drop_subject(g, "I001_PhysicianToEHR"))))
    cases.append(Case(S, "rejected_missing_protocol", R.REJECTED,
                      m(lambda g, q: set_value(g, "I001_PhysicianToEHR", REO.protocol, None))))
    cases.append(Case(S, "rejected_consent_without_exception", R.REJECTED,
                      m(lambda g, q: g.remove((e("C001_HIPAA"), REO.hasException, None)))))
    cases.append(Case(S, "rejected_wrong_authority_value", R.REJECTED,
                      m(lambda g, q: set_value(g, "Physician", REO.authorityLevel, Literal("licensed_pharmacist"))),
                      note="v1.0.0 used an empty string, which duplicated rejected_missing_authority"))
    cases.append(Case(S, "not_derived_inactive_seed_goal", R.NOT_DERIVED,
                      m(lambda g, q: drop_subject(g, "G002"))))
    return cases


# ---------------------------------------------------------------------------
# Targeted regressions for the revision
# ---------------------------------------------------------------------------
def targeted_regressions() -> List[Case]:
    S = "targeted"
    c: List[Case] = []

    def m(fn):
        def wrap(g, q):
            fn(g, q)
            return g, q
        return wrap

    c.append(Case(S, "T01_hard_rule_via_interaction_governedBy_without_validator", R.PENDING_REVIEW,
                  m(lambda g, q: (add_constraint(g, "C901_Interop"),
                                  g.add((e("I001_PhysicianToEHR"), REO.governedBy, e("C901_Interop")))))))
    c.append(Case(S, "T02_hard_rule_via_actor_isSubjectTo_without_validator", R.PENDING_REVIEW,
                  m(lambda g, q: (add_constraint(g, "C902_Audit"),
                                  g.add((e("Physician"), REO.isSubjectTo, e("C902_Audit")))))))
    c.append(Case(S, "T03_hard_rule_only_on_unreferenced_Pharmacist", R.CONDITIONAL,
                  m(lambda g, q: (add_constraint(g, "C903_PharmacyOnly"),
                                  g.add((e("Pharmacist"), REO.isSubjectTo, e("C903_PharmacyOnly"))))),
                  note="v1.0.0 revision patch returned pending_review (over-inclusive applicability)"))
    c.append(Case(S, "T04_hard_rule_appliesTo_unreferenced_EHR_only", R.CONDITIONAL,
                  m(lambda g, q: add_constraint(g, "C904_EHROnly", applies=["EHR_System"])),
                  note="v1.0.0 returned pending_review"))
    c.append(Case(S, "T05_blocking_premise_refuted", R.REJECTED,
                  m(lambda g, q: set_value(g, "U001_DrugDBFrequency", REO.status, Literal("rejected"))),
                  note="v1.0.0 returned accepted"))
    c.append(Case(S, "T06_critical_uncertainty_affects_actor_without_blocking", R.CONDITIONAL,
                  m(lambda g, q: (resolve_u001(g),
                                  add_uncertainty(g, "U900_AuthorityCurrent", "unvalidated", "critical",
                                                  affects=["Physician"]))),
                  note="v1.0.0 returned accepted"))
    c.append(Case(S, "T07_low_uncertainty_affects_concept", R.ACCEPTED_WITH_RESERVATIONS,
                  m(lambda g, q: (resolve_u001(g),
                                  add_uncertainty(g, "U901_RouteVocabulary", "unvalidated", "low",
                                                  affects=["D001_Medication"])))))
    c.append(Case(S, "T08_uncertainty_blocks_parent_goal", R.CONDITIONAL,
                  m(lambda g, q: (resolve_u001(g),
                                  add_uncertainty(g, "U902_StaffingPolicy", "unvalidated", "high", blocks=["G001"]))),
                  note="v1.0.0 returned accepted"))

    def nonparticipant(g, q):
        resolve_u001(g)
        g.remove((e("X001_EmergencyDept"), REO.hasActiveActor, e("Physician")))
        for goal in ("G001", "G002"):
            g.remove((e("Physician"), REO.isResponsibleFor, e(goal)))
    c.append(Case(S, "T09_actor_neither_active_nor_responsible", R.REJECTED, m(nonparticipant),
                  note="v1.0.0 returned accepted"))

    def reverse(g, q):
        resolve_u001(g)
        set_value(g, "I001_PhysicianToEHR", REO.hasSource, e("EHR_System"))
        set_value(g, "I001_PhysicianToEHR", REO.hasTarget, e("Physician"))
    c.append(Case(S, "T10_interaction_direction_reversed", R.REJECTED, m(reverse), note="v1.0.0 returned accepted"))
    c.append(Case(S, "T11_interaction_exchanges_no_referenced_concept", R.REJECTED,
                  m(lambda g, q: (resolve_u001(g), set_value(g, "I001_PhysicianToEHR", REO.exchangesData, None))),
                  note="v1.0.0 returned accepted"))

    def rename(g, q):
        new = "C002_PrescribingAuthority"
        for s, p, o in list(g.triples((e("C002_FDA"), None, None))):
            g.remove((s, p, o)); g.add((e(new), p, o))
        for s, p, o in list(g.triples((None, None, e("C002_FDA")))):
            g.remove((s, p, o)); g.add((s, p, e(new)))
        q.hard = [new if x == "C002_FDA" else x for x in q.hard]
    c.append(Case(S, "T12_constraint_identifier_renamed", R.CONDITIONAL, m(rename),
                  note="v1.0.0 returned pending_review (validator registry keyed by instance identifier)"))
    c.append(Case(S, "T13_conflicting_authority_values", R.PENDING_REVIEW,
                  m(lambda g, q: (resolve_u001(g),
                                  g.add((e("Physician"), REO.authorityLevel, Literal("resident_physician")))))))
    c.append(Case(S, "T14_ambiguous_reference_modelled_as_ambiguity", R.CONDITIONAL,
                  m(lambda g, q: (resolve_u001(g),
                                  add_uncertainty(g, "U903_WhichMedicationList", "unvalidated", "high",
                                                  affects=["D002_Patient"], cls=REO.AmbiguityUncertainty)))))
    c.append(Case(S, "T15_goal_also_typed_as_constraint", R.PENDING_REVIEW,
                  m(lambda g, q: (resolve_u001(g), g.add((e("G002"), RDF.type, REO.Constraint))))))
    c.append(Case(S, "T16_refinement_cycle_through_seed", R.PENDING_REVIEW,
                  m(lambda g, q: g.add((e("G001"), REO.refines, e("G002"))))))

    def seed_only(g, q):
        q.__init__(rid="R998", text="Anything at all.", seed_goal="G002", context="X001_EmergencyDept")
    c.append(Case(S, "T17_requirement_without_references", R.PENDING_REVIEW, m(seed_only)))

    def text_only(g, q):
        resolve_u001(g)
        q.text = "The Pharmacist may ignore contraindications."
    c.append(Case(S, "T18_text_changed_annotation_unchanged", R.ACCEPTED, m(text_only),
                  note="documents that the text is not parsed (annotation fidelity is an input assumption)"))
    c.append(Case(S, "T19_uncertainty_reopened_after_resolution", R.CONDITIONAL,
                  m(lambda g, q: (resolve_u001(g), set_value(g, "U001_DrugDBFrequency", REO.status,
                                                             Literal("unvalidated"))))))
    return c


# ---------------------------------------------------------------------------
def run_case(base: rdflib.Graph, case: Case, with_shacl: bool = True) -> dict:
    g = deepcopy(base)
    q = baseline_requirement()
    g, q = case.mutate(g, q)
    env = R.project(g)
    res = R.validate(env, q)
    row = {"suite": case.suite, "name": case.name, "expected": case.expected, "observed": res.state,
           "pass": res.state == case.expected, "trace_size": len(res.trace),
           "trace": sorted(res.trace), "justifications": res.justifications, "note": case.note}
    if with_shacl:
        s = shacl(g)
        row.update({"shacl_conforms": s["conforms"], "shacl_violations": s["violations"],
                    "shacl_warnings": s["warnings"], "shacl_verdict": shacl_verdict(s)})
    return row


def impact_queries(base: rdflib.Graph) -> List[dict]:
    env = R.project(base)
    q = baseline_requirement()
    res = R.validate(env, q)
    records = {q.rid: res.trace}
    rows = []
    for element, should in [("C002_FDA", True), ("D001_Medication", True),
                            ("U001_DrugDBFrequency", True), ("G005", False)]:
        hit = q.rid in R.requirements_of(element, records)
        rows.append({"suite": "impact-4", "name": f"change::{element}", "expected": "hit" if should else "miss",
                     "observed": "hit" if hit else "miss", "pass": hit == should, "trace_size": len(res.trace)})
    # Lifecycle: resolve U001, query on U001, reopen.
    g2 = deepcopy(base); resolve_u001(g2)
    r2 = R.validate(R.project(g2), q)
    hit = q.rid in R.requirements_of("U001_DrugDBFrequency", {q.rid: r2.trace})
    rows.append({"suite": "targeted", "name": "T20_impact_query_on_resolved_uncertainty", "expected": "hit",
                 "observed": "hit" if hit else "miss", "pass": hit, "trace_size": len(r2.trace)})
    return rows


def main() -> int:
    base = R.load_graph([BASE])
    rows = [run_case(base, c) for c in original_scenarios()]
    rows += impact_queries(base)
    rows += [run_case(base, c) for c in targeted_regressions()]
    base_res = R.validate(R.project(base), baseline_requirement())

    out_csv = ROOT / "evaluation_results.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["suite", "name", "expected", "observed", "pass", "trace_size",
                                          "shacl_verdict", "note"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "regression_results.json").write_text(json.dumps({
        "policy_version": R.POLICY_VERSION, "baseline": {"rid": "R001", "state": base_res.state,
                                                          "trace": sorted(base_res.trace),
                                                          "justifications": base_res.justifications},
        "rows": rows}, indent=2), encoding="utf-8")

    def summary(suite):
        sel = [r for r in rows if r["suite"] == suite]
        return sum(r["pass"] for r in sel), len(sel)
    for suite, label in [("original-18", "Scenario checks"), ("impact-4", "Impact queries "),
                         ("targeted", "Targeted regressions")]:
        p, n = summary(suite)
        print(f"{label}: {p}/{n} passed")
    print(f"Baseline status: {base_res.state.upper()}; trace size: {len(base_res.trace)}")
    failed = [r for r in rows if not r["pass"]]
    for r in failed:
        print("  FAILED:", r["suite"], r["name"], "expected", r["expected"], "observed", r["observed"])
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
