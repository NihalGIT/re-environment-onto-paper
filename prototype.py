#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REO Reference Derivation Checker
================================

A minimal, deterministic reference implementation of the environment-bounded
derivation contract defined in the accompanying paper (Environment Engineering
for Requirements Engineering). It complements the OWL/SHACL layer: SHACL decides
whether an environment *model* conforms; this checker decides the *requirement
state* (accepted / conditional / rejected / not-derived) that the derivation
contract assigns to a candidate requirement, given an environment.

Design principles
-----------------
* Single source of truth. The checker consumes the very same Turtle instance
  that the SHACL layer validates (examples/medical-emergency/hospital.ttl),
  parsed with rdflib. There is no parallel hand-coded model, so agreement
  between checker and ontology is a genuine result, not a coincidence.
* Executable semantics. slice(), Validate(), and requirements() implement,
  respectively, Definition (Environment slice), Definition (Validation
  contract) + Algorithm 1, and the trace-relative change-impact function.
* Determinism. No LLM is invoked. Candidate generation is fixed so the
  acceptance semantics can be tested in isolation from generator quality.

Outputs
-------
* prints "Scenario checks: X/Y passed" and the baseline status/trace size;
* writes evaluation_results.csv with one row per scenario and per impact query.

Usage
-----
    python prototype.py
    python prototype.py --instance examples/medical-emergency/hospital.ttl

Requires: rdflib (same dependency as the SHACL layer).
"""

from __future__ import annotations

import argparse
import csv
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import rdflib
    from rdflib import Namespace, RDF
except ImportError:  # pragma: no cover
    print("ERROR: rdflib not installed. Run: pip install rdflib")
    sys.exit(1)

REO = Namespace("http://re-environment-onto.org/ontology#")
EX = Namespace("http://hospital.example.org#")

DEFAULT_INSTANCE = "examples/medical-emergency/hospital.ttl"


# ---------------------------------------------------------------------------
# Environment: a typed projection of the RDF instance into the seven views.
# ---------------------------------------------------------------------------
@dataclass
class Environment:
    """Seven-view environment extracted from an RDF graph.

    Each element is stored by its local identifier (the fragment after '#').
    Only the attributes the derivation contract reads are projected; the graph
    remains the authoritative artifact and can be re-validated with SHACL.
    """

    actors: Dict[str, dict] = field(default_factory=dict)
    goals: Dict[str, dict] = field(default_factory=dict)
    domain: Dict[str, dict] = field(default_factory=dict)
    constraints: Dict[str, dict] = field(default_factory=dict)
    contexts: Dict[str, dict] = field(default_factory=dict)
    uncertainties: Dict[str, dict] = field(default_factory=dict)
    interactions: Dict[str, dict] = field(default_factory=dict)

    def exists(self, eid: str) -> bool:
        return any(
            eid in view
            for view in (
                self.actors, self.goals, self.domain, self.constraints,
                self.contexts, self.uncertainties, self.interactions,
            )
        )

    def all_ids(self) -> Set[str]:
        out: Set[str] = set()
        for view in (
            self.actors, self.goals, self.domain, self.constraints,
            self.contexts, self.uncertainties, self.interactions,
        ):
            out |= set(view)
        return out


def _local(term) -> str:
    s = str(term)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


def _objs(g, s, p) -> List[str]:
    return [_local(o) for o in g.objects(s, p)]


def _obj(g, s, p) -> Optional[str]:
    for o in g.objects(s, p):
        return _local(o) if isinstance(o, rdflib.URIRef) else str(o)
    return None


def load_environment(path: str) -> Environment:
    """Project the RDF instance at *path* into a typed Environment."""
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    env = Environment()

    actor_types = {REO.Actor, REO.HumanActor, REO.SystemActor, REO.OrganizationActor}
    goal_types = {REO.Goal, REO.StrategicGoal, REO.OperationalGoal}
    unc_types = {
        REO.Uncertainty, REO.AssumptionUncertainty, REO.UnknownUncertainty,
        REO.AmbiguityUncertainty, REO.RiskUncertainty,
    }
    con_types = {
        REO.Constraint, REO.RegulatoryConstraint, REO.BusinessConstraint,
        REO.TechnicalConstraint, REO.QualityConstraint,
    }
    inter_types = {
        REO.Interaction, REO.CommunicationInteraction, REO.DataFlowInteraction,
        REO.ControlFlowInteraction, REO.ServiceCallInteraction,
    }

    for s in set(g.subjects(RDF.type, None)):
        types = set(g.objects(s, RDF.type))
        eid = _local(s)
        if types & actor_types:
            env.actors[eid] = {
                "authority": _obj(g, s, REO.authorityLevel),
                "capabilities": _objs(g, s, REO.hasCapability),
                "responsibleFor": _objs(g, s, REO.isResponsibleFor),
                "subjectTo": _objs(g, s, REO.isSubjectTo),
            }
        elif types & goal_types:
            env.goals[eid] = {
                "strategic": REO.StrategicGoal in types,
                "refinementType": _obj(g, s, REO.refinementType),
                "refines": _objs(g, s, REO.refines),
                "stakeholders": _objs(g, s, REO.hasStakeholder),
                "priority": _obj(g, s, REO.priority),
            }
        elif types & unc_types:
            env.uncertainties[eid] = {
                "status": _obj(g, s, REO.status),
                "impact": _obj(g, s, REO.impactLevel),
                "affects": _objs(g, s, REO.affects),
                "blocks": _objs(g, s, REO.blocks),
            }
        elif types & con_types:
            env.constraints[eid] = {
                "regulatory": REO.RegulatoryConstraint in types,
                "enforcement": _obj(g, s, REO.enforcementLevel),
                "authoritativeText": _obj(g, s, REO.hasAuthoritativeText),
                "appliesTo": _objs(g, s, REO.appliesTo),
                "exceptions": _objs(g, s, REO.hasException),
            }
        elif types & inter_types:
            env.interactions[eid] = {
                "source": _obj(g, s, REO.hasSource),
                "target": _obj(g, s, REO.hasTarget),
                "data": _objs(g, s, REO.exchangesData),
                "protocol": _obj(g, s, REO.protocol),
                "governedBy": _objs(g, s, REO.governedBy),
            }
        elif REO.DomainConcept in types:
            env.domain[eid] = {
                "properties": _objs(g, s, REO.hasProperty),
                "invariants": _objs(g, s, REO.hasInvariant),
                "relatedTo": _objs(g, s, REO.relatedTo),
            }
        elif REO.Context in types:
            env.contexts[eid] = {
                "activeConstraints": _objs(g, s, REO.hasActiveConstraint),
                "activeActors": _objs(g, s, REO.hasActiveActor),
            }
    return env


# ---------------------------------------------------------------------------
# Candidate requirement: fixed, deterministic obligations over the slice.
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    """A candidate requirement and the environment obligations it induces.

    A candidate declares which elements it *uses*; the checker turns these into
    hard obligations. This stands in for LLM proposition extraction while
    keeping the acceptance test deterministic.
    """

    rid: str
    text: str
    seed_goal: str
    needs_actor: Optional[str] = None
    needs_capability: Optional[str] = None       # (actor, capability)
    needs_authority: Optional[str] = None         # actor must have an authority level
    needs_domain: List[str] = field(default_factory=list)
    needs_domain_property: List[Tuple[str, str]] = field(default_factory=list)  # (concept, property)
    needs_interaction: Optional[str] = None
    needs_protocol: Optional[str] = None          # interaction must declare a protocol
    hard_constraints: List[str] = field(default_factory=list)
    # Record-access obligation: constraint that requires consent unless the
    # active context is declared an exception (models HIPAA emergency override).
    record_access_constraint: Optional[str] = None


# The baseline candidate R001 of the worked example (all obligations satisfiable
# in the released instance under the emergency context, but blocked by U001).
def baseline_candidate() -> Candidate:
    return Candidate(
        rid="R001",
        text=("The Physician shall verify Medication.contraindications against "
              "Patient.current_medications before prescribing."),
        seed_goal="G002",
        needs_actor="Physician",
        needs_capability="Action_Prescribe",
        needs_authority="Physician",
        needs_domain=["D001_Medication", "D002_Patient"],
        needs_domain_property=[("D001_Medication", "Prop_Contraindications"),
                               ("D002_Patient", "Prop_CurrentMedications")],
        needs_interaction="I001_PhysicianToEHR",
        needs_protocol="I001_PhysicianToEHR",
        hard_constraints=["C002_FDA"],
        record_access_constraint="C001_HIPAA",
    )


# ---------------------------------------------------------------------------
# slice(): goal-seeded relevance policy (Definition: Environment slice).
# ---------------------------------------------------------------------------
def slice_env(env: Environment, seed_goal: str, context: str) -> Set[str]:
    """Return the identifiers relevant to *seed_goal* under *context*.

    Policy: the goal and its ancestors; actors responsible for it; domain
    concepts referenced by the candidate; constraints applicable to involved
    actors or active in the context; the active context; interactions whose
    source/target is an involved actor; and uncertainties affecting any
    included element.
    """
    S: Set[str] = set()
    if seed_goal in env.goals:
        S.add(seed_goal)
        # ancestors via refines
        frontier = list(env.goals[seed_goal].get("refines", []))
        while frontier:
            g = frontier.pop()
            if g in env.goals and g not in S:
                S.add(g)
                frontier.extend(env.goals[g].get("refines", []))
    if context in env.contexts:
        S.add(context)
    involved_actors: Set[str] = set()
    for a, ad in env.actors.items():
        if seed_goal in ad.get("responsibleFor", []):
            involved_actors.add(a)
    if context in env.contexts:
        involved_actors |= set(env.contexts[context].get("activeActors", []))
    S |= involved_actors
    # constraints: applicable to involved actors or active in context
    for c, cd in env.constraints.items():
        if involved_actors & set(cd.get("appliesTo", [])):
            S.add(c)
    if context in env.contexts:
        S |= set(env.contexts[context].get("activeConstraints", []))
    # interactions involving an involved actor
    for i, idd in env.interactions.items():
        if idd.get("source") in involved_actors or idd.get("target") in involved_actors:
            S.add(i)
            S |= set(idd.get("data", []))
    # uncertainties affecting anything already in S
    for u, ud in env.uncertainties.items():
        if (set(ud.get("affects", [])) | set(ud.get("blocks", []))) & S:
            S.add(u)
    return S


# ---------------------------------------------------------------------------
# Validate(): the acceptance contract (Algorithm 1).
# ---------------------------------------------------------------------------
ACCEPTED, CONDITIONAL, REJECTED, NOT_DERIVED = (
    "accepted", "conditional", "rejected", "not_derived",
)


def validate(env: Environment, S: Set[str], q: Candidate,
             context: str) -> Tuple[str, List[str], Set[str]]:
    """Return (status, justifications, trace) for candidate *q*.

    Hard-obligation failure -> rejected. Otherwise, an unresolved uncertainty
    blocking the seed goal -> conditional. Otherwise -> accepted. The trace
    accumulates every element read as evidence (provenance completeness by
    construction).
    """
    trace: Set[str] = {q.seed_goal}
    if context in env.contexts:
        trace.add(context)
    justifications: List[str] = []
    hard_fail = False

    def fail(msg: str) -> None:
        nonlocal hard_fail
        hard_fail = True
        justifications.append(f"REJECT: {msg}")

    # Seed goal must be active (present in the sliced environment).
    if q.seed_goal not in env.goals or q.seed_goal not in S:
        return (NOT_DERIVED, [f"NOT DERIVED: seed goal {q.seed_goal} inactive"], trace)

    # Actor obligation.
    if q.needs_actor:
        if q.needs_actor not in env.actors:
            fail(f"actor {q.needs_actor} undefined")
        else:
            trace.add(q.needs_actor)

    # Capability obligation.
    if q.needs_capability and q.needs_actor:
        ad = env.actors.get(q.needs_actor, {})
        if q.needs_capability not in ad.get("capabilities", []):
            fail(f"actor {q.needs_actor} lacks capability {q.needs_capability}")

    # Authority obligation.
    if q.needs_authority:
        ad = env.actors.get(q.needs_authority, {})
        if not ad.get("authority"):
            fail(f"actor {q.needs_authority} lacks an authority level")

    # Domain concept obligations.
    for d in q.needs_domain:
        if d not in env.domain:
            fail(f"domain concept {d} undefined")
        else:
            trace.add(d)

    # Domain property obligations.
    for concept, prop in q.needs_domain_property:
        dd = env.domain.get(concept, {})
        if prop not in dd.get("properties", []):
            fail(f"concept {concept} lacks property {prop}")

    # Interaction obligation.
    if q.needs_interaction:
        if q.needs_interaction not in env.interactions:
            fail(f"interaction {q.needs_interaction} undefined")
        else:
            trace.add(q.needs_interaction)

    # Protocol obligation.
    if q.needs_protocol:
        idd = env.interactions.get(q.needs_protocol, {})
        if not idd.get("protocol"):
            fail(f"interaction {q.needs_protocol} declares no protocol")

    # Hard applicable constraints must exist and be satisfiable.
    for c in q.hard_constraints:
        if c not in env.constraints:
            fail(f"hard constraint {c} undefined")
        else:
            trace.add(c)
            # FDA-style: prescriber must be licensed (authority present).
            if env.constraints[c].get("regulatory") and q.needs_authority:
                ad = env.actors.get(q.needs_authority, {})
                if not ad.get("authority"):
                    fail(f"constraint {c}: {q.needs_authority} not licensed")

    # Record-access obligation with context exception (HIPAA emergency override).
    if q.record_access_constraint:
        c = q.record_access_constraint
        if c not in env.constraints:
            fail(f"record-access constraint {c} undefined")
        else:
            trace.add(c)
            exceptions = env.constraints[c].get("exceptions", [])
            if context not in exceptions:
                # consent required; the model has no consent fact -> reject.
                fail(f"constraint {c}: consent required outside exception "
                     f"context (active={context})")
            else:
                justifications.append(
                    f"OK: {c} waived — {context} is a declared exception")

    if hard_fail:
        return (REJECTED, justifications, trace)

    # Uncertainty: unresolved uncertainty blocking the seed goal -> conditional.
    open_u: Set[str] = set()
    for u, ud in env.uncertainties.items():
        if q.seed_goal in ud.get("blocks", []) and ud.get("status") == "unvalidated":
            open_u.add(u)
            trace.add(u)
    if open_u:
        justifications.append(
            f"CONDITIONAL: unresolved uncertainty {sorted(open_u)} blocks "
            f"{q.seed_goal}")
        return (CONDITIONAL, justifications, trace)

    justifications.append("ACCEPT: all hard obligations discharged")
    return (ACCEPTED, justifications, trace)


# ---------------------------------------------------------------------------
# requirements(): trace-relative change impact.
# ---------------------------------------------------------------------------
def requirements_of(element: str,
                    records: List[Tuple[str, Set[str]]]) -> List[str]:
    """Return the ids of requirement records whose trace contains *element*."""
    return [rid for rid, trace in records if element in trace]


# ---------------------------------------------------------------------------
# Scenario harness: 15 state scenarios + 4 impact queries.
# ---------------------------------------------------------------------------
@dataclass
class Scenario:
    name: str
    expected: str
    mutate: object  # Callable[[Environment, Candidate, str], tuple]


def _mut(env: Environment) -> Environment:
    return deepcopy(env)


def build_scenarios() -> List[Scenario]:
    """15 scenarios: 2 accepted, 2 conditional, 10 rejected, 1 not-derived."""
    S: List[Scenario] = []

    # --- 2 ACCEPTED ------------------------------------------------------
    def acc_freshness_resolved(env, q, ctx):
        e = _mut(env)
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        return e, q, ctx
    S.append(Scenario("accepted_freshness_resolved", ACCEPTED, acc_freshness_resolved))

    def acc_outpatient_consent(env, q, ctx):
        # Outpatient context that declares consent as an exception AND freshness resolved.
        e = _mut(env)
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        e.contexts["X002_Outpatient"] = {
            "activeConstraints": ["C002_FDA"],
            "activeActors": ["Physician"],
        }
        e.constraints["C001_HIPAA"]["exceptions"].append("X002_Outpatient")
        return e, q, "X002_Outpatient"
    S.append(Scenario("accepted_outpatient_consent_and_freshness", ACCEPTED, acc_outpatient_consent))

    # --- 2 CONDITIONAL ---------------------------------------------------
    def cond_baseline(env, q, ctx):
        return _mut(env), q, ctx  # unresolved freshness, emergency context
    S.append(Scenario("conditional_baseline_unresolved_freshness", CONDITIONAL, cond_baseline))

    def cond_outpatient_unresolved(env, q, ctx):
        e = _mut(env)
        e.contexts["X002_Outpatient"] = {
            "activeConstraints": ["C002_FDA"],
            "activeActors": ["Physician"],
        }
        e.constraints["C001_HIPAA"]["exceptions"].append("X002_Outpatient")
        # freshness still unvalidated -> conditional
        return e, q, "X002_Outpatient"
    S.append(Scenario("conditional_outpatient_consent_unresolved_freshness", CONDITIONAL, cond_outpatient_unresolved))

    # --- 10 REJECTED -----------------------------------------------------
    def rej_missing_actor(env, q, ctx):
        e = _mut(env); del e.actors["Physician"]; return e, q, ctx
    S.append(Scenario("rejected_missing_actor", REJECTED, rej_missing_actor))

    def rej_missing_capability(env, q, ctx):
        e = _mut(env)
        e.actors["Physician"]["capabilities"] = [
            c for c in e.actors["Physician"]["capabilities"] if c != "Action_Prescribe"]
        return e, q, ctx
    S.append(Scenario("rejected_missing_capability", REJECTED, rej_missing_capability))

    def rej_missing_authority(env, q, ctx):
        e = _mut(env); e.actors["Physician"]["authority"] = None; return e, q, ctx
    S.append(Scenario("rejected_missing_authority", REJECTED, rej_missing_authority))

    def rej_missing_domain(env, q, ctx):
        e = _mut(env); del e.domain["D001_Medication"]; return e, q, ctx
    S.append(Scenario("rejected_missing_domain_concept", REJECTED, rej_missing_domain))

    def rej_missing_domain_prop(env, q, ctx):
        e = _mut(env)
        e.domain["D002_Patient"]["properties"] = [
            p for p in e.domain["D002_Patient"]["properties"] if p != "Prop_CurrentMedications"]
        return e, q, ctx
    S.append(Scenario("rejected_missing_domain_property", REJECTED, rej_missing_domain_prop))

    def rej_missing_interaction(env, q, ctx):
        e = _mut(env); del e.interactions["I001_PhysicianToEHR"]; return e, q, ctx
    S.append(Scenario("rejected_missing_interaction", REJECTED, rej_missing_interaction))

    def rej_missing_protocol(env, q, ctx):
        e = _mut(env); e.interactions["I001_PhysicianToEHR"]["protocol"] = None; return e, q, ctx
    S.append(Scenario("rejected_missing_protocol", REJECTED, rej_missing_protocol))

    def rej_missing_hard_constraint(env, q, ctx):
        e = _mut(env); del e.constraints["C002_FDA"]; return e, q, ctx
    S.append(Scenario("rejected_missing_hard_constraint", REJECTED, rej_missing_hard_constraint))

    def rej_consent_no_exception(env, q, ctx):
        # Emergency context no longer declared an exception of HIPAA -> consent fails.
        e = _mut(env); e.constraints["C001_HIPAA"]["exceptions"] = []; return e, q, ctx
    S.append(Scenario("rejected_consent_without_exception", REJECTED, rej_consent_no_exception))

    def rej_unlicensed_prescriber(env, q, ctx):
        e = _mut(env); e.actors["Physician"]["authority"] = ""; return e, q, ctx
    S.append(Scenario("rejected_unlicensed_prescriber", REJECTED, rej_unlicensed_prescriber))

    # --- 1 NOT DERIVED ---------------------------------------------------
    def notderived_inactive_seed(env, q, ctx):
        e = _mut(env); del e.goals["G002"]; return e, q, ctx
    S.append(Scenario("not_derived_inactive_seed_goal", NOT_DERIVED, notderived_inactive_seed))

    return S


def run(instance_path: str) -> int:
    base_env = load_environment(instance_path)
    q = baseline_candidate()
    context = "X001_EmergencyDept"

    rows: List[dict] = []
    scenarios = build_scenarios()
    passed = 0
    for sc in scenarios:
        env2, q2, ctx2 = sc.mutate(base_env, q, context)
        S = slice_env(env2, q2.seed_goal, ctx2)
        status, just, trace = validate(env2, S, q2, ctx2)
        ok = status == sc.expected
        passed += int(ok)
        rows.append({
            "kind": "scenario",
            "name": sc.name,
            "expected": sc.expected,
            "observed": status,
            "pass": ok,
            "trace_size": len(trace),
            "detail": " | ".join(just),
        })

    # Baseline record for impact queries (unresolved freshness -> conditional).
    S0 = slice_env(base_env, q.seed_goal, context)
    base_status, base_just, base_trace = validate(base_env, S0, q, context)
    records = [(q.rid, base_trace)]

    # 4 direct impact queries: 3 hits + 1 miss.
    impact_queries = [
        ("C002_FDA", True),               # licensing constraint change -> hits R001
        ("D001_Medication", True),        # Medication concept change  -> hits R001
        ("U001_DrugDBFrequency", True),   # freshness uncertainty change -> hits R001
        ("G005", False),                  # unrelated goal change -> no hit
    ]
    impact_pass = 0
    for element, should_hit in impact_queries:
        hit = q.rid in requirements_of(element, records)
        ok = hit == should_hit
        impact_pass += int(ok)
        rows.append({
            "kind": "impact_query",
            "name": f"change::{element}",
            "expected": "hit" if should_hit else "miss",
            "observed": "hit" if hit else "miss",
            "pass": ok,
            "trace_size": len(base_trace),
            "detail": f"requirements({element}) -> {requirements_of(element, records)}",
        })

    out_csv = Path(instance_path).resolve().parents[1] / "evaluation_results.csv"
    # place CSV at repo root regardless of instance location
    repo_root = Path(__file__).resolve().parent
    out_csv = repo_root / "evaluation_results.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "kind", "name", "expected", "observed", "pass", "trace_size", "detail"])
        w.writeheader()
        w.writerows(rows)

    total = len(scenarios)
    print(f"Scenario checks: {passed}/{total} passed")
    print(f"Impact queries : {impact_pass}/{len(impact_queries)} passed")
    print(f"Baseline status: {base_status.upper()}; trace size: {len(base_trace)}")
    print(f"Results written: {out_csv.name}")

    return 0 if (passed == total and impact_pass == len(impact_queries)) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="REO reference derivation checker")
    ap.add_argument("--instance", default=DEFAULT_INSTANCE,
                    help="Path to the RDF environment instance (Turtle).")
    args = ap.parse_args()
    if not Path(args.instance).exists():
        print(f"ERROR: instance not found: {args.instance}")
        sys.exit(2)
    sys.exit(run(args.instance))


if __name__ == "__main__":
    main()
