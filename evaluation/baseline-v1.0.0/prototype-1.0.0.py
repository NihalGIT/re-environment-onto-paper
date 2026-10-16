#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REO Reference Derivation Checker
================================

A minimal, deterministic reference implementation of the environment-bounded
derivation contract defined in the accompanying paper (Environment Engineering
for Requirements Engineering). It complements the OWL/SHACL layer: SHACL decides
whether an environment *model* conforms; this checker decides the *requirement
state* (accepted / accepted-with-reservations / conditional / pending-review /
rejected / not-derived) that the derivation contract assigns to a candidate
requirement, given an environment.

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
from typing import Callable, Dict, List, Optional, Set, Tuple

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
    soft_constraints: List[str] = field(default_factory=list)
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
# slice(): goal-seeded relevance policy and candidate-specific closure.
# ---------------------------------------------------------------------------
def slice_env(env: Environment, seed_goal: str, context: str) -> Set[str]:
    """Return the initial seed slice S0 for *seed_goal* under *context*.

    This is the executable counterpart of the paper's explicit relevance policy
    rho.  The slice is the least set reached by the following deterministic
    closure used in the reference checker:

    * include the seed goal, its goal ancestors, and the active context;
    * include actors responsible for the seed or active in the context;
    * include constraints applying to those actors or activated by the context;
    * include interactions involving those actors and their exchanged concepts;
    * include uncertainties affecting or blocking any included element.

    An undefined seed or context yields the empty set.  This guard prevents the
    pipeline from generating or accepting a candidate without an anchoring slice.
    """
    if seed_goal not in env.goals or context not in env.contexts:
        return set()

    slice_ids: Set[str] = {seed_goal, context}

    # Goal closure: the seed and its ancestors through ``refines``.
    frontier = list(env.goals[seed_goal].get("refines", []))
    while frontier:
        goal_id = frontier.pop()
        if goal_id in env.goals and goal_id not in slice_ids:
            slice_ids.add(goal_id)
            frontier.extend(env.goals[goal_id].get("refines", []))

    # Actors responsible for the seed or active in the selected context.
    involved_actors: Set[str] = {
        actor_id
        for actor_id, actor_data in env.actors.items()
        if seed_goal in actor_data.get("responsibleFor", [])
    }
    involved_actors |= set(env.contexts[context].get("activeActors", []))
    slice_ids |= {actor_id for actor_id in involved_actors if actor_id in env.actors}

    # Constraints applicable to involved actors or explicitly active in context.
    for constraint_id, constraint_data in env.constraints.items():
        if involved_actors & set(constraint_data.get("appliesTo", [])):
            slice_ids.add(constraint_id)
    slice_ids |= {
        constraint_id
        for constraint_id in env.contexts[context].get("activeConstraints", [])
        if constraint_id in env.constraints
    }

    # Interactions involving an included actor, plus exchanged domain concepts.
    for interaction_id, interaction_data in env.interactions.items():
        if (interaction_data.get("source") in involved_actors
                or interaction_data.get("target") in involved_actors):
            slice_ids.add(interaction_id)
            slice_ids |= {
                domain_id
                for domain_id in interaction_data.get("data", [])
                if domain_id in env.domain
            }

    # Uncertainty closure. Iterate to a fixed point because an uncertainty may
    # affect an element introduced by another closure step.
    changed = True
    while changed:
        changed = False
        for uncertainty_id, uncertainty_data in env.uncertainties.items():
            touched = (
                set(uncertainty_data.get("affects", []))
                | set(uncertainty_data.get("blocks", []))
            )
            if touched & slice_ids and uncertainty_id not in slice_ids:
                slice_ids.add(uncertainty_id)
                changed = True

    return slice_ids


def _constraint_level(constraint_data: dict) -> str:
    """Normalize a REO hard/soft enforcement value."""
    return str(constraint_data.get("enforcement") or "hard").strip().lower()


def candidate_references(q: Candidate) -> Set[str]:
    """Return environment identifiers explicitly referenced by candidate *q*."""
    refs: Set[str] = {q.seed_goal}
    for value in (
        q.needs_actor,
        q.needs_authority,
        q.needs_interaction,
        q.needs_protocol,
        q.record_access_constraint,
    ):
        if value:
            refs.add(value)
    refs |= set(q.needs_domain)
    refs |= {concept for concept, _ in q.needs_domain_property}
    refs |= set(q.hard_constraints)
    refs |= set(q.soft_constraints)
    return refs


def applicable_constraint_ids(
    env: Environment,
    q: Candidate,
    context: str,
    scope_ids: Optional[Set[str]] = None,
) -> Tuple[Set[str], Set[str]]:
    """Return hard and soft constraints applicable to candidate *q*.

    Applicability combines explicit candidate declarations, context activation,
    and ``appliesTo`` links to candidate-referenced elements.  For constraints
    that exist in the environment, ``enforcementLevel`` is authoritative.
    Missing declared or context-active constraints are conservatively classified
    from the candidate declaration (soft only when explicitly declared soft;
    otherwise hard), so they cannot disappear silently.
    """
    declared_hard: Set[str] = set(q.hard_constraints)
    declared_soft: Set[str] = set(q.soft_constraints)
    if q.record_access_constraint:
        declared_hard.add(q.record_access_constraint)

    active_ids: Set[str] = set()
    if context in env.contexts:
        active_ids = set(env.contexts[context].get("activeConstraints", []))

    refs = candidate_references(q) | set(scope_ids or set())
    applicable_ids: Set[str] = declared_hard | declared_soft | active_ids
    for constraint_id, constraint_data in env.constraints.items():
        if set(constraint_data.get("appliesTo", [])) & refs:
            applicable_ids.add(constraint_id)

    hard_ids: Set[str] = set()
    soft_ids: Set[str] = set()
    for constraint_id in applicable_ids:
        constraint_data = env.constraints.get(constraint_id)
        if constraint_data is not None:
            if _constraint_level(constraint_data) == "soft":
                soft_ids.add(constraint_id)
            else:
                hard_ids.add(constraint_id)
        elif constraint_id in declared_soft:
            soft_ids.add(constraint_id)
        else:
            hard_ids.add(constraint_id)

    return hard_ids, soft_ids


def validation_closure(
    env: Environment,
    initial_slice: Set[str],
    q: Candidate,
    context: str,
) -> Set[str]:
    """Return the least candidate-specific validation slice ``Sq``.

    Starting from the seed slice and candidate references, the function reaches
    a fixed point over applicable constraints, the elements needed to evaluate
    them, interaction dependencies, and uncertainties.  The fixed-point form is
    important: a newly included interaction or governed element may reveal an
    additional applicable constraint that was not present in the initial slice.
    """
    validation_slice = set(initial_slice)
    validation_slice |= {
        element_id
        for element_id in candidate_references(q)
        if env.exists(element_id)
    }

    changed = True
    while changed:
        before = set(validation_slice)

        hard_ids, soft_ids = applicable_constraint_ids(
            env, q, context, validation_slice
        )
        for constraint_id in hard_ids | soft_ids:
            constraint_data = env.constraints.get(constraint_id)
            if constraint_data is None:
                continue
            validation_slice.add(constraint_id)
            validation_slice |= {
                element_id
                for element_id in constraint_data.get("appliesTo", [])
                if env.exists(element_id)
            }
            validation_slice |= {
                exception_id
                for exception_id in constraint_data.get("exceptions", [])
                if exception_id in env.contexts
            }

        for interaction_id in list(validation_slice & set(env.interactions)):
            interaction_data = env.interactions[interaction_id]
            for element_id in (
                interaction_data.get("source"), interaction_data.get("target")
            ):
                if element_id and env.exists(element_id):
                    validation_slice.add(element_id)
            validation_slice |= {
                domain_id
                for domain_id in interaction_data.get("data", [])
                if domain_id in env.domain
            }
            validation_slice |= {
                constraint_id
                for constraint_id in interaction_data.get("governedBy", [])
                if constraint_id in env.constraints
            }

        for uncertainty_id, uncertainty_data in env.uncertainties.items():
            touched = (
                set(uncertainty_data.get("affects", []))
                | set(uncertainty_data.get("blocks", []))
            )
            if touched & validation_slice:
                validation_slice.add(uncertainty_id)

        changed = validation_slice != before

    return validation_slice


# ---------------------------------------------------------------------------
# Explicit constraint-checker registry.
# ---------------------------------------------------------------------------
CHECK_PASS = "pass"
CHECK_FAIL = "fail"
CHECK_UNCHECKED = "unchecked"

ConstraintChecker = Callable[
    [Environment, Candidate, str, dict],
    Tuple[str, str],
]


def check_record_access_constraint(
    env: Environment,
    q: Candidate,
    context: str,
    constraint_data: dict,
) -> Tuple[str, str]:
    """Check consent unless the active context is an explicit exception."""
    exceptions = set(constraint_data.get("exceptions", []))
    if context in exceptions:
        return (
            CHECK_PASS,
            f"constraint {q.record_access_constraint} waived: "
            f"{context} is a declared exception",
        )
    return (
        CHECK_FAIL,
        f"consent required outside an exception context (active={context})",
    )


def check_prescriber_authority(
    env: Environment,
    q: Candidate,
    context: str,
    constraint_data: dict,
) -> Tuple[str, str]:
    """Check that the actor referenced by the candidate has authority."""
    del context, constraint_data  # checker signature is uniform across rules
    if not q.needs_authority:
        return (CHECK_UNCHECKED, "candidate identifies no actor for authority check")
    actor_data = env.actors.get(q.needs_authority)
    if actor_data is None:
        return (
            CHECK_FAIL,
            f"actor {q.needs_authority} is undefined",
        )
    if not actor_data.get("authority"):
        return (
            CHECK_FAIL,
            f"{q.needs_authority} is not licensed",
        )
    return (
        CHECK_PASS,
        f"{q.needs_authority} has authority "
        f"{actor_data.get('authority')}",
    )


# The reference artifact deliberately registers only the two domain-specific
# checks used by the medical example.  Any applicable hard constraint without
# a registered checker becomes ``pending_review`` rather than being treated as
# satisfied by default.
CONSTRAINT_CHECKERS: Dict[str, ConstraintChecker] = {
    "C001_HIPAA": check_record_access_constraint,
    "C002_FDA": check_prescriber_authority,
}


# ---------------------------------------------------------------------------
# Validate(): the acceptance contract (Algorithm 1).
# ---------------------------------------------------------------------------
(
    ACCEPTED,
    ACCEPTED_WITH_RESERVATIONS,
    CONDITIONAL,
    PENDING_REVIEW,
    REJECTED,
    NOT_DERIVED,
) = (
    "accepted",
    "accepted_with_reservations",
    "conditional",
    "pending_review",
    "rejected",
    "not_derived",
)


def validate(
    env: Environment,
    initial_slice: Set[str],
    q: Candidate,
    context: str,
) -> Tuple[str, List[str], Set[str]]:
    """Return ``(status, justifications, trace)`` for candidate *q*.

    Decision priority is:

    ``rejected > pending_review > conditional >
    accepted_with_reservations > accepted``.

    ``not_derived`` is returned before candidate validation when no valid seed
    slice exists.  Missing or unchecked mandatory evidence never defaults to
    acceptance.  The trace accumulates every environment element actually read
    as evidence.
    """
    trace: Set[str] = set()
    justifications: List[str] = []

    if not initial_slice or q.seed_goal not in env.goals or q.seed_goal not in initial_slice:
        return (
            NOT_DERIVED,
            [f"NOT DERIVED: no active anchoring slice for seed {q.seed_goal}"],
            trace,
        )

    validation_slice = validation_closure(env, initial_slice, q, context)
    trace.add(q.seed_goal)
    if context in env.contexts:
        trace.add(context)

    failed_hard: List[str] = []
    failed_soft: List[str] = []
    unchecked_hard: List[str] = []
    open_uncertainties: Set[str] = set()
    obligation_count = 0
    checked_count = 0

    def hard_fail(msg: str) -> None:
        failed_hard.append(msg)
        justifications.append(f"REJECT: {msg}")

    def soft_fail(msg: str) -> None:
        failed_soft.append(msg)
        justifications.append(f"RESERVATION: {msg}")

    def unchecked(msg: str) -> None:
        unchecked_hard.append(msg)
        justifications.append(f"PENDING REVIEW: {msg}")

    # Actor obligation.
    if q.needs_actor:
        obligation_count += 1
        checked_count += 1
        if q.needs_actor not in env.actors:
            hard_fail(f"actor {q.needs_actor} undefined")
        elif q.needs_actor not in validation_slice:
            unchecked(f"actor {q.needs_actor} absent from validation slice")
        else:
            trace.add(q.needs_actor)

    # Capability obligation.
    if q.needs_capability and q.needs_actor:
        obligation_count += 1
        checked_count += 1
        actor_data = env.actors.get(q.needs_actor)
        if actor_data is None:
            hard_fail(f"actor {q.needs_actor} undefined for capability check")
        elif q.needs_capability not in actor_data.get("capabilities", []):
            hard_fail(
                f"actor {q.needs_actor} lacks capability {q.needs_capability}"
            )

    # Authority obligation.
    if q.needs_authority:
        obligation_count += 1
        checked_count += 1
        actor_data = env.actors.get(q.needs_authority)
        if actor_data is None:
            hard_fail(f"actor {q.needs_authority} undefined for authority check")
        elif not actor_data.get("authority"):
            hard_fail(f"actor {q.needs_authority} lacks an authority level")
        else:
            trace.add(q.needs_authority)

    # Domain concept obligations.
    for domain_id in q.needs_domain:
        obligation_count += 1
        checked_count += 1
        if domain_id not in env.domain:
            hard_fail(f"domain concept {domain_id} undefined")
        elif domain_id not in validation_slice:
            unchecked(f"domain concept {domain_id} absent from validation slice")
        else:
            trace.add(domain_id)

    # Domain property obligations.
    for concept_id, property_id in q.needs_domain_property:
        obligation_count += 1
        checked_count += 1
        concept_data = env.domain.get(concept_id)
        if concept_data is None:
            hard_fail(f"domain concept {concept_id} undefined for property check")
        elif property_id not in concept_data.get("properties", []):
            hard_fail(f"concept {concept_id} lacks property {property_id}")
        else:
            trace.add(concept_id)

    # Interaction obligation.
    if q.needs_interaction:
        obligation_count += 1
        checked_count += 1
        if q.needs_interaction not in env.interactions:
            hard_fail(f"interaction {q.needs_interaction} undefined")
        elif q.needs_interaction not in validation_slice:
            unchecked(
                f"interaction {q.needs_interaction} absent from validation slice"
            )
        else:
            trace.add(q.needs_interaction)

    # Protocol obligation.
    if q.needs_protocol:
        obligation_count += 1
        checked_count += 1
        interaction_data = env.interactions.get(q.needs_protocol)
        if interaction_data is None:
            hard_fail(
                f"interaction {q.needs_protocol} undefined for protocol check"
            )
        elif not interaction_data.get("protocol"):
            hard_fail(f"interaction {q.needs_protocol} declares no protocol")
        else:
            trace.add(q.needs_protocol)

    hard_constraint_ids, soft_constraint_ids = applicable_constraint_ids(
        env, q, context, validation_slice
    )

    # Hard applicable constraints must be present, included, and discharged by
    # an explicit checker.  Presence in the graph is not proof of satisfaction.
    for constraint_id in sorted(hard_constraint_ids):
        obligation_count += 1
        constraint_data = env.constraints.get(constraint_id)
        if constraint_data is None:
            unchecked(f"hard constraint {constraint_id} undefined")
            continue
        if constraint_id not in validation_slice:
            unchecked(f"hard constraint {constraint_id} absent from validation slice")
            continue

        trace.add(constraint_id)
        checker = CONSTRAINT_CHECKERS.get(constraint_id)
        if checker is None:
            unchecked(f"hard constraint {constraint_id} has no registered checker")
            continue

        checked_count += 1
        outcome, explanation = checker(env, q, context, constraint_data)
        if outcome == CHECK_FAIL:
            hard_fail(f"constraint {constraint_id}: {explanation}")
        elif outcome == CHECK_UNCHECKED:
            unchecked(f"constraint {constraint_id}: {explanation}")
        else:
            justifications.append(f"OK: {constraint_id}: {explanation}")

    # Soft obligations cannot reject a candidate.  A failed or unchecked soft
    # obligation is retained as a reservation and produces
    # ``accepted_with_reservations`` when no higher-priority state applies.
    for constraint_id in sorted(soft_constraint_ids):
        obligation_count += 1
        constraint_data = env.constraints.get(constraint_id)
        if constraint_data is None:
            soft_fail(f"soft constraint {constraint_id} undefined")
            continue
        if constraint_id not in validation_slice:
            soft_fail(f"soft constraint {constraint_id} absent from validation slice")
            continue

        trace.add(constraint_id)
        checker = CONSTRAINT_CHECKERS.get(constraint_id)
        if checker is None:
            soft_fail(f"soft constraint {constraint_id} has no registered checker")
            continue

        checked_count += 1
        outcome, explanation = checker(env, q, context, constraint_data)
        if outcome in {CHECK_FAIL, CHECK_UNCHECKED}:
            soft_fail(f"constraint {constraint_id}: {explanation}")
        else:
            justifications.append(f"OK: {constraint_id}: {explanation}")

    # Explicitly modeled unresolved uncertainty produces ``conditional``.
    for uncertainty_id, uncertainty_data in env.uncertainties.items():
        if (
            q.seed_goal in uncertainty_data.get("blocks", [])
            and uncertainty_data.get("status") == "unvalidated"
        ):
            obligation_count += 1
            checked_count += 1
            open_uncertainties.add(uncertainty_id)
            trace.add(uncertainty_id)

    # A candidate with no induced/checkable obligation is never accepted by
    # default.  It requires model completion or explicit human review.
    if obligation_count == 0 or checked_count == 0:
        justifications.append(
            "PENDING REVIEW: no validation obligation could be discharged"
        )
        return (PENDING_REVIEW, justifications, trace)

    if failed_hard:
        return (REJECTED, justifications, trace)
    if unchecked_hard:
        return (PENDING_REVIEW, justifications, trace)
    if open_uncertainties:
        justifications.append(
            "CONDITIONAL: unresolved uncertainty "
            f"{sorted(open_uncertainties)} blocks {q.seed_goal}"
        )
        return (CONDITIONAL, justifications, trace)
    if failed_soft:
        justifications.append(
            "ACCEPT WITH RESERVATIONS: all hard obligations discharged; "
            "one or more soft obligations remain unsatisfied"
        )
        return (ACCEPTED_WITH_RESERVATIONS, justifications, trace)

    justifications.append("ACCEPT: all mandatory obligations discharged")
    return (ACCEPTED, justifications, trace)


# ---------------------------------------------------------------------------
# requirements(): trace-relative change impact.
# ---------------------------------------------------------------------------
def requirements_of(element: str,
                    records: List[Tuple[str, Set[str]]]) -> List[str]:
    """Return the ids of requirement records whose trace contains *element*."""
    return [rid for rid, trace in records if element in trace]


# ---------------------------------------------------------------------------
# Scenario harness: 18 state scenarios + 4 impact queries.
# ---------------------------------------------------------------------------
@dataclass
class Scenario:
    name: str
    expected: str
    mutate: Callable[[Environment, Candidate, str], Tuple[Environment, Candidate, str]]


def _mut(env: Environment) -> Environment:
    return deepcopy(env)


def build_scenarios() -> List[Scenario]:
    """18 scenarios covering all six derivation/validation outcomes.

    Distribution: 2 accepted, 1 accepted-with-reservations, 2 conditional,
    3 pending-review, 9 rejected, and 1 not-derived.
    """
    scenarios: List[Scenario] = []

    # --- 2 ACCEPTED ------------------------------------------------------
    def acc_freshness_resolved(env, q, ctx):
        e = _mut(env)
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "accepted_freshness_resolved", ACCEPTED, acc_freshness_resolved
    ))

    def acc_outpatient_consent(env, q, ctx):
        e = _mut(env)
        q2 = deepcopy(q)
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        e.contexts["X002_Outpatient"] = {
            "activeConstraints": ["C002_FDA"],
            "activeActors": ["Physician"],
        }
        e.constraints["C001_HIPAA"]["exceptions"].append("X002_Outpatient")
        return e, q2, "X002_Outpatient"

    scenarios.append(Scenario(
        "accepted_outpatient_consent_and_freshness",
        ACCEPTED,
        acc_outpatient_consent,
    ))

    # --- 1 ACCEPTED WITH RESERVATIONS -----------------------------------
    def reserve_soft_privacy_failure(env, q, ctx):
        e = _mut(env)
        q2 = deepcopy(q)
        # Controlled mutation: exercise the soft branch by making the existing
        # record-access rule soft and removing its emergency exception.
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        e.constraints["C001_HIPAA"]["enforcement"] = "soft"
        e.constraints["C001_HIPAA"]["exceptions"] = []
        return e, q2, ctx


    scenarios.append(Scenario(
        "accepted_with_reservations_soft_constraint",
        ACCEPTED_WITH_RESERVATIONS,
        reserve_soft_privacy_failure,
    ))

    # --- 2 CONDITIONAL ---------------------------------------------------
    def cond_baseline(env, q, ctx):
        return _mut(env), deepcopy(q), ctx

    scenarios.append(Scenario(
        "conditional_baseline_unresolved_freshness", CONDITIONAL, cond_baseline
    ))

    def cond_outpatient_unresolved(env, q, ctx):
        e = _mut(env)
        q2 = deepcopy(q)
        e.contexts["X002_Outpatient"] = {
            "activeConstraints": ["C002_FDA"],
            "activeActors": ["Physician"],
        }
        e.constraints["C001_HIPAA"]["exceptions"].append("X002_Outpatient")
        return e, q2, "X002_Outpatient"

    scenarios.append(Scenario(
        "conditional_outpatient_consent_unresolved_freshness",
        CONDITIONAL,
        cond_outpatient_unresolved,
    ))

    # --- 3 PENDING REVIEW ------------------------------------------------
    def pending_missing_hard_constraint(env, q, ctx):
        e = _mut(env)
        q2 = deepcopy(q)
        del e.constraints["C002_FDA"]
        # The candidate and context still declare C002_FDA as applicable.
        return e, q2, ctx

    scenarios.append(Scenario(
        "pending_review_missing_hard_constraint",
        PENDING_REVIEW,
        pending_missing_hard_constraint,
    ))

    def pending_no_obligations(env, q, ctx):
        e = _mut(env)
        orphan_goal = "G999_Orphan"
        empty_context = "X999_EmptyContext"
        e.goals[orphan_goal] = {
            "strategic": False,
            "refinementType": None,
            "refines": [],
            "stakeholders": [],
            "priority": "1",
        }
        e.contexts[empty_context] = {
            "activeConstraints": [],
            "activeActors": [],
        }
        q2 = Candidate(
            rid="R999",
            text="An unanchored candidate statement.",
            seed_goal=orphan_goal,
        )
        return e, q2, empty_context

    scenarios.append(Scenario(
        "pending_review_no_induced_obligations",
        PENDING_REVIEW,
        pending_no_obligations,
    ))

    def pending_hard_constraint_without_checker(env, q, ctx):
        e = _mut(env)
        q2 = deepcopy(q)
        e.uncertainties["U001_DrugDBFrequency"]["status"] = "validated"
        constraint_id = "C900_ManualSafetyReview"
        e.constraints[constraint_id] = {
            "regulatory": False,
            "enforcement": "hard",
            "authoritativeText": None,
            "appliesTo": ["Physician"],
            "exceptions": [],
        }
        e.contexts[ctx]["activeConstraints"].append(constraint_id)
        q2.hard_constraints.append(constraint_id)
        return e, q2, ctx

    scenarios.append(Scenario(
        "pending_review_hard_constraint_without_checker",
        PENDING_REVIEW,
        pending_hard_constraint_without_checker,
    ))

    # --- 9 REJECTED ------------------------------------------------------
    def rej_missing_actor(env, q, ctx):
        e = _mut(env)
        del e.actors["Physician"]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario("rejected_missing_actor", REJECTED, rej_missing_actor))

    def rej_missing_capability(env, q, ctx):
        e = _mut(env)
        e.actors["Physician"]["capabilities"] = [
            capability
            for capability in e.actors["Physician"]["capabilities"]
            if capability != "Action_Prescribe"
        ]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_capability", REJECTED, rej_missing_capability
    ))

    def rej_missing_authority(env, q, ctx):
        e = _mut(env)
        e.actors["Physician"]["authority"] = None
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_authority", REJECTED, rej_missing_authority
    ))

    def rej_missing_domain(env, q, ctx):
        e = _mut(env)
        del e.domain["D001_Medication"]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_domain_concept", REJECTED, rej_missing_domain
    ))

    def rej_missing_domain_prop(env, q, ctx):
        e = _mut(env)
        e.domain["D002_Patient"]["properties"] = [
            prop
            for prop in e.domain["D002_Patient"]["properties"]
            if prop != "Prop_CurrentMedications"
        ]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_domain_property", REJECTED, rej_missing_domain_prop
    ))

    def rej_missing_interaction(env, q, ctx):
        e = _mut(env)
        del e.interactions["I001_PhysicianToEHR"]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_interaction", REJECTED, rej_missing_interaction
    ))

    def rej_missing_protocol(env, q, ctx):
        e = _mut(env)
        e.interactions["I001_PhysicianToEHR"]["protocol"] = None
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_missing_protocol", REJECTED, rej_missing_protocol
    ))

    def rej_consent_no_exception(env, q, ctx):
        e = _mut(env)
        e.constraints["C001_HIPAA"]["exceptions"] = []
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_consent_without_exception", REJECTED, rej_consent_no_exception
    ))

    def rej_unlicensed_prescriber(env, q, ctx):
        e = _mut(env)
        e.actors["Physician"]["authority"] = ""
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "rejected_unlicensed_prescriber", REJECTED, rej_unlicensed_prescriber
    ))

    # --- 1 NOT DERIVED ---------------------------------------------------
    def notderived_inactive_seed(env, q, ctx):
        e = _mut(env)
        del e.goals["G002"]
        return e, deepcopy(q), ctx

    scenarios.append(Scenario(
        "not_derived_inactive_seed_goal", NOT_DERIVED, notderived_inactive_seed
    ))

    return scenarios


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

    # Place the CSV at the repository root regardless of instance location.
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