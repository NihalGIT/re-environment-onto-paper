#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REO reference checker, version 1.1.0
====================================

Deterministic reference implementation of the EC-RE derivation contract.

The checker evaluates a *requirement* (a candidate statement together with its
explicit mapping to environment elements, see ``reo-derivation.ttl``) against
an RDF environment snapshot typed with REO, and returns

    (decision state, justifications, trace)

The trace is the *read set*: every environment identifier whose description
was consulted to reach the decision. Read-set recording is what makes direct
change-impact analysis sound (see ``touched_identifiers`` and the paper's
Proposition 2): the decision is a function of the requirement annotation, the
policy, and the triples whose subject or object belongs to the trace.

Policy (version ``POLICY_VERSION``) — decision order:

    not_derived      seed goal or context undefined
    pending_review   the requirement references no environment element
    rejected         a checked hard obligation failed, or a premise blocking
                     the seed lineage was refuted (status "rejected")
    pending_review   a hard obligation could not be checked (undefined rule,
                     no registered validator, conflicting values, invalidated
                     affected evidence, uninterpretable uncertainty status)
    conditional      an unvalidated uncertainty blocks the seed lineage, or an
                     unvalidated high/critical uncertainty affects consulted
                     evidence
    accepted_with_reservations
                     a soft obligation failed or is unchecked, or a
                     low/medium unvalidated uncertainty affects evidence
    accepted         none of the above

No language model is invoked. The natural-language text is not parsed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import rdflib
from rdflib import RDF, RDFS, Namespace, URIRef, Literal

REO = Namespace("http://re-environment-onto.org/ontology#")
PROV = Namespace("http://www.w3.org/ns/prov#")
EX = Namespace("http://hospital.example.org#")
REQ = Namespace("http://hospital.example.org/requirements#")

POLICY_VERSION = "ecre-policy-1.1.0"
ROOT = Path(__file__).resolve().parent
ONTOLOGY_FILES = [ROOT / "ontology" / "reo-core.ttl", ROOT / "ontology" / "reo-derivation.ttl"]

ACCEPTED = "accepted"
ACCEPTED_WITH_RESERVATIONS = "accepted_with_reservations"
CONDITIONAL = "conditional"
PENDING_REVIEW = "pending_review"
REJECTED = "rejected"
NOT_DERIVED = "not_derived"
STATES = [ACCEPTED, ACCEPTED_WITH_RESERVATIONS, CONDITIONAL, PENDING_REVIEW, REJECTED, NOT_DERIVED]
STATE_IRI = {
    ACCEPTED: REO.Accepted, ACCEPTED_WITH_RESERVATIONS: REO.AcceptedWithReservations,
    CONDITIONAL: REO.Conditional, PENDING_REVIEW: REO.PendingReview,
    REJECTED: REO.Rejected, NOT_DERIVED: REO.NotDerived,
}

PASS, FAIL, UNCHECKED, NOT_TRIGGERED = "pass", "fail", "unchecked", "not_triggered"

# View roots. Membership is computed with the rdfs:subClassOf closure of the
# loaded ontology, so project-specific subclasses (extensions) are recognised.
VIEW_ROOTS = {
    "actors": REO.Actor, "goals": REO.Goal, "domain": REO.DomainConcept,
    "constraints": REO.Constraint, "contexts": REO.Context,
    "uncertainties": REO.Uncertainty, "interactions": REO.Interaction,
    "actions": REO.Action, "properties": REO.DomainProperty, "invariants": REO.DomainInvariant,
}
SEVEN_VIEWS = ["actors", "goals", "domain", "constraints", "contexts", "uncertainties", "interactions"]

# Attributes that must be single-valued for the checker to interpret them.
FUNCTIONAL = {
    "actors": ["authority"], "constraints": ["enforcement", "validatorKey", "formalExpression"],
    "uncertainties": ["status", "impact"], "interactions": ["source", "target", "protocol"],
    "goals": [], "domain": [], "contexts": [], "actions": ["label"], "properties": [], "invariants": [],
}


def local(term) -> str:
    s = str(term)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Environment projection
# ---------------------------------------------------------------------------
@dataclass
class Environment:
    views: Dict[str, Dict[str, dict]] = field(default_factory=lambda: {v: {} for v in VIEW_ROOTS})
    conflicts: Dict[str, List[str]] = field(default_factory=dict)   # id -> conflicting attributes
    multi_typed: Dict[str, List[str]] = field(default_factory=dict)  # id -> several views
    snapshot: str = ""

    def __getattr__(self, name):  # env.actors, env.goals, ...
        if name in VIEW_ROOTS:
            return self.__dict__["views"][name]
        raise AttributeError(name)

    def view_of(self, eid: str) -> Optional[str]:
        for v, d in self.views.items():
            if eid in d:
                return v
        return None

    def exists(self, eid: str) -> bool:
        return self.view_of(eid) is not None

    def all_ids(self) -> Set[str]:
        out: Set[str] = set()
        for d in self.views.values():
            out |= set(d)
        return out


_ONTO_CACHE: Dict[str, rdflib.Graph] = {}


def ontology_graph() -> rdflib.Graph:
    if "g" not in _ONTO_CACHE:
        g = rdflib.Graph()
        for f in ONTOLOGY_FILES:
            g.parse(f, format="turtle")
        _ONTO_CACHE["g"] = g
    return _ONTO_CACHE["g"]


def _view_of_class(onto: rdflib.Graph, data: rdflib.Graph) -> Dict[URIRef, str]:
    """Map every class (ontology or data-declared subclass) to its view."""
    sub: Dict[URIRef, Set[URIRef]] = {}
    for g in (onto, data):
        for s, o in g.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                sub.setdefault(s, set()).add(o)
    roots = {r: v for v, r in VIEW_ROOTS.items()}
    memo: Dict[URIRef, Optional[str]] = {}

    def find(c, seen=()):
        if c in roots:
            return roots[c]
        if c in memo:
            return memo[c]
        memo[c] = None
        for p in sub.get(c, ()):
            if p not in seen:
                v = find(p, seen + (c,))
                if v:
                    memo[c] = v
                    break
        return memo[c]

    classes = set(sub) | set(roots)
    for g in (onto, data):
        classes |= {o for o in g.objects(None, RDF.type) if isinstance(o, URIRef)}
    return {c: find(c) for c in classes if find(c)}


# Requirement annotations and decision records may share a dataset (or a graph) with
# the environment, but they are not part of the environment snapshot: the snapshot
# hash and the touched-identifier diff ignore them (Sections III-F and V-E).
DERIVATION_TYPES = {REO.Requirement, REO.DerivationRecord, REO.ValidationActivity}
DERIVATION_PREDICATES = {REO[n] for n in (
    "assesses", "hasDecision", "environmentSnapshot", "policyVersion", "hasJustification", "consulted",
    "supersedes", "requirementId", "requirementText", "hasSeedGoal", "assessedInContext", "hasResponsibleActor",
    "performsAction", "requiresAuthorityOf", "refersToConcept", "refersToProperty", "usesInteraction",
    "expectsInteractionSource", "requiresProtocol", "declaresHardConstraint", "declaresSoftConstraint")} | {
    PROV.wasGeneratedBy, PROV.startedAtTime, PROV.endedAtTime, PROV.used}


def environment_triples(g: rdflib.Graph) -> Set[Tuple]:
    """The environment snapshot of a graph: every triple without blank nodes, except
    requirement annotations and decision records (subjects typed as Requirement,
    DerivationRecord or ValidationActivity, and derivation-module predicates)."""
    excluded = {s for t in DERIVATION_TYPES for s in g.subjects(RDF.type, t)}
    return {(s, p, o) for s, p, o in g
            if not isinstance(s, rdflib.BNode) and not isinstance(o, rdflib.BNode)
            and s not in excluded and p not in DERIVATION_PREDICATES}


def snapshot_hash(g: rdflib.Graph) -> str:
    """SHA-256 over the sorted N-Triples lines of the environment snapshot."""
    lines = sorted(f"{s.n3()} {p.n3()} {o.n3()} ." for s, p, o in environment_triples(g))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def load_graph(paths: Iterable) -> rdflib.Graph:
    g = rdflib.Graph()
    for p in paths:
        g.parse(str(p), format="turtle")
    return g


def project(g: rdflib.Graph) -> Environment:
    """Project an RDF environment graph into the seven views (+ auxiliary)."""
    env = Environment()
    vmap = _view_of_class(ontology_graph(), g)

    def vals(s, p) -> List[str]:
        out = []
        for o in g.objects(s, p):
            out.append(local(o) if isinstance(o, URIRef) else str(o))
        return sorted(set(out))

    for s in set(g.subjects(RDF.type, None)):
        if not isinstance(s, URIRef):
            continue
        views = sorted({vmap[t] for t in g.objects(s, RDF.type) if t in vmap})
        if not views:
            continue
        def _store(view):
            if view == "actors":
                d = {"authority": vals(s, REO.authorityLevel), "capabilities": vals(s, REO.hasCapability),
                     "responsibleFor": vals(s, REO.isResponsibleFor), "subjectTo": vals(s, REO.isSubjectTo),
                     "name": vals(s, REO.actorName)}
            elif view == "goals":
                d = {"refines": vals(s, REO.refines), "stakeholders": vals(s, REO.hasStakeholder),
                     "priority": vals(s, REO.priority), "name": vals(s, REO.goalName),
                     "strategic": REO.StrategicGoal in set(g.objects(s, RDF.type))}
            elif view == "domain":
                d = {"properties": vals(s, REO.hasProperty), "invariants": vals(s, REO.hasInvariant),
                     "relatedTo": vals(s, REO.relatedTo), "name": vals(s, REO.conceptName)}
            elif view == "constraints":
                d = {"enforcement": vals(s, REO.enforcementLevel), "validatorKey": vals(s, REO.validatorKey),
                     "formalExpression": vals(s, REO.formalExpression), "appliesTo": vals(s, REO.appliesTo),
                     "exceptions": vals(s, REO.hasException), "name": vals(s, REO.constraintName),
                     "naturalLanguage": vals(s, REO.naturalLanguage)}
            elif view == "contexts":
                d = {"activeConstraints": vals(s, REO.hasActiveConstraint), "activeActors": vals(s, REO.hasActiveActor),
                     "properties": vals(s, REO.contextProperty), "name": vals(s, REO.contextName)}
            elif view == "uncertainties":
                d = {"status": vals(s, REO.status), "impact": vals(s, REO.impactLevel),
                     "affects": vals(s, REO.affects), "blocks": vals(s, REO.blocks),
                     "name": vals(s, REO.uncertaintyName), "subject": vals(s, REO.subject)}
            elif view == "interactions":
                d = {"source": vals(s, REO.hasSource), "target": vals(s, REO.hasTarget),
                     "data": vals(s, REO.exchangesData), "protocol": vals(s, REO.protocol),
                     "governedBy": vals(s, REO.governedBy), "name": vals(s, REO.interactionName)}
            elif view == "actions":
                d = {"label": vals(s, RDFS.label)}
            elif view == "properties":
                d = {"name": vals(s, REO.propertyName)}
            else:
                d = {"expression": vals(s, REO.invariantExpression)}
            env.views[view][eid] = d
            bad = [a for a in FUNCTIONAL.get(view, []) if len(d.get(a, [])) > 1]
            if bad:
                env.conflicts[eid] = bad
        eid = local(s)
        if len(views) > 1:
            env.multi_typed[eid] = views
        for view in views:
            _store(view)
        continue
    env.snapshot = snapshot_hash(g)
    return env


def one(values: List[str]) -> Optional[str]:
    return values[0] if values else None


# ---------------------------------------------------------------------------
# Requirement (candidate + explicit mapping)
# ---------------------------------------------------------------------------
@dataclass
class Requirement:
    rid: str
    text: str
    seed_goal: str
    context: str
    actor: Optional[str] = None
    actions: List[str] = field(default_factory=list)
    authority_of: Optional[str] = None
    concepts: List[str] = field(default_factory=list)
    properties: List[str] = field(default_factory=list)
    interaction: Optional[str] = None
    interaction_source: Optional[str] = None
    requires_protocol: bool = False
    hard: List[str] = field(default_factory=list)
    soft: List[str] = field(default_factory=list)

    def references(self) -> Set[str]:
        refs = {x for x in (self.actor, self.authority_of, self.interaction, self.interaction_source) if x}
        return refs | set(self.actions) | set(self.concepts) | set(self.properties)


def load_requirements(g: rdflib.Graph) -> List[Requirement]:
    out = []
    for r in sorted(set(g.subjects(RDF.type, REO.Requirement))):
        def o1(p):
            v = next(iter(sorted(g.objects(r, p))), None)
            return None if v is None else (local(v) if isinstance(v, URIRef) else str(v))

        def om(p):
            return sorted(local(v) for v in g.objects(r, p))
        out.append(Requirement(
            rid=o1(REO.requirementId) or local(r), text=o1(REO.requirementText) or "",
            seed_goal=o1(REO.hasSeedGoal), context=o1(REO.assessedInContext),
            actor=o1(REO.hasResponsibleActor), actions=om(REO.performsAction),
            authority_of=o1(REO.requiresAuthorityOf), concepts=om(REO.refersToConcept),
            properties=om(REO.refersToProperty), interaction=o1(REO.usesInteraction),
            interaction_source=o1(REO.expectsInteractionSource),
            requires_protocol=(o1(REO.requiresProtocol) or "false").lower() == "true",
            hard=om(REO.declaresHardConstraint), soft=om(REO.declaresSoftConstraint)))
    return out


# ---------------------------------------------------------------------------
# Validators (bound to constraints through reo:validatorKey)
# ---------------------------------------------------------------------------
@dataclass
class Assessment:
    env: Environment
    req: Requirement
    reads: Set[str] = field(default_factory=set)
    log: List[Tuple[str, str, str]] = field(default_factory=list)  # (level, outcome, message)

    def read(self, *ids):
        for i in ids:
            if i:
                self.reads.add(i)

    def record(self, level: str, outcome: str, msg: str):
        self.log.append((level, outcome, msg))


_RULE = re.compile(r"^\s*([A-Za-z_][\w]*)\s*(?:\(.*?\))?\s*→\s*(.+)$")


def _antecedent(expr: Optional[str]) -> Optional[str]:
    m = _RULE.match(expr or "")
    return m.group(1) if m else None


def _triggered(a: Assessment, antecedent: str) -> Optional[bool]:
    """True/False, or None when an action label is conflicting (undecidable)."""
    hit = False
    for act in a.req.actions:
        a.read(act)
        labels = a.env.actions.get(act, {}).get("label", [])
        if len(labels) > 1:
            return None
        hit |= one(labels) == antecedent
    return hit


def v_authority_equals(a: Assessment, cid: str, c: dict) -> Tuple[str, str]:
    expr = one(c["formalExpression"])
    ant = _antecedent(expr)
    m = re.search(r"actor\.authority\s*=\s*([\w-]+)", expr or "")
    if not ant or not m:
        return UNCHECKED, f"{cid}: formal expression not interpretable by authority-equals"
    trig = _triggered(a, ant)
    if trig is None:
        return UNCHECKED, f"{cid}: conflicting action labels; antecedent '{ant}' undecidable"
    if not trig:
        return NOT_TRIGGERED, f"{cid}: antecedent '{ant}' not performed by the requirement"
    who = a.req.authority_of or a.req.actor
    a.read(who)
    actor = a.env.actors.get(who)
    if actor is None:
        return FAIL, f"{cid}: actor {who} undefined"
    if len(actor["authority"]) > 1:
        return UNCHECKED, f"{cid}: conflicting authority values for {who}"
    if one(actor["authority"]) != m.group(1):
        return FAIL, f"{cid}: {who} authority {one(actor['authority'])!r} differs from required {m.group(1)!r}"
    return PASS, f"{cid}: {who} has authority {m.group(1)}"


def v_consent_or_exception(a: Assessment, cid: str, c: dict) -> Tuple[str, str]:
    ant = _antecedent(one(c["formalExpression"]))
    if not ant:
        return UNCHECKED, f"{cid}: formal expression not interpretable by consent-or-exception"
    trig = _triggered(a, ant)
    if trig is None:
        return UNCHECKED, f"{cid}: conflicting action labels; antecedent '{ant}' undecidable"
    if not trig:
        return NOT_TRIGGERED, f"{cid}: antecedent '{ant}' not performed by the requirement"
    ctx = a.req.context
    a.read(ctx)
    if ctx in c["exceptions"]:
        return PASS, f"{cid}: {ctx} is a declared exception"
    if "consent_obtained=true" in a.env.contexts.get(ctx, {}).get("properties", []):
        return PASS, f"{cid}: consent is asserted in {ctx}"
    return FAIL, f"{cid}: consent required in {ctx}, which is not an exception and asserts no consent"


VALIDATORS: Dict[str, Callable[[Assessment, str, dict], Tuple[str, str]]] = {
    "authority-equals": v_authority_equals,
    "consent-or-exception": v_consent_or_exception,
}


# ---------------------------------------------------------------------------
# Decision procedure
# ---------------------------------------------------------------------------
@dataclass
class Result:
    rid: str
    state: str
    justifications: List[str]
    trace: Set[str]
    obligations: List[Tuple[str, str, str]]
    snapshot: str = ""

    def key(self):
        return (self.state, tuple(sorted(self.justifications)), tuple(sorted(self.trace)))


def seed_lineage(a: Assessment) -> List[str]:
    out, frontier = [], [a.req.seed_goal]
    while frontier:
        g = frontier.pop(0)
        if g in out:
            continue
        a.read(g)
        if g not in a.env.goals:
            continue
        out.append(g)
        frontier.extend(sorted(a.env.goals[g]["refines"]))
    return out


def applicable_constraints(a: Assessment, lineage: List[str]) -> Dict[str, str]:
    """Return {constraint id: route}. Only the requirement's own references are
    used (not the whole slice), so that every element whose links determine
    applicability is in the read set."""
    env, q = a.env, a.req
    routes: Dict[str, str] = {}
    for cid in q.hard:
        routes.setdefault(cid, "declared-hard")
    for cid in q.soft:
        routes.setdefault(cid, "declared-soft")
    ctx = env.contexts.get(q.context, {})
    for cid in ctx.get("activeConstraints", []):
        routes.setdefault(cid, "context-active")
    for who in {q.actor, q.authority_of} - {None}:
        a.read(who)
        for cid in env.actors.get(who, {}).get("subjectTo", []):
            routes.setdefault(cid, f"isSubjectTo({who})")
    if q.interaction:
        a.read(q.interaction)
        for cid in env.interactions.get(q.interaction, {}).get("governedBy", []):
            routes.setdefault(cid, f"governedBy({q.interaction})")
    scope = q.references() | set(lineage)
    # Incoming appliesTo links of every scope element are consulted.
    a.read(*sorted(scope))
    for cid, c in sorted(env.constraints.items()):
        hit = sorted(set(c["appliesTo"]) & scope)
        if hit:
            routes.setdefault(cid, f"appliesTo({hit[0]})")
    return routes


def validate(env: Environment, q: Requirement) -> Result:
    a = Assessment(env, q)
    hard_fail, hard_unchecked, soft_res, open_u = [], [], [], []

    def ob(level, outcome, msg):
        a.record(level, outcome, msg)
        if outcome == FAIL and level == "hard":
            hard_fail.append(msg)
        elif outcome == UNCHECKED and level == "hard":
            hard_unchecked.append(msg)
        elif outcome in (FAIL, UNCHECKED) and level == "soft":
            soft_res.append(msg)

    a.read(q.seed_goal, q.context)
    if q.seed_goal not in env.goals or q.context not in env.contexts:
        return Result(q.rid, NOT_DERIVED, [f"NOT DERIVED: seed {q.seed_goal} or context {q.context} undefined"],
                      set(a.reads), [], env.snapshot)
    if not (q.actor or q.actions or q.concepts or q.properties or q.interaction):
        return Result(q.rid, PENDING_REVIEW, ["PENDING REVIEW: the requirement references no environment element"],
                      set(a.reads), [], env.snapshot)
    lineage = seed_lineage(a)
    ctx = env.contexts[q.context]
    # Well-formedness guard: a refinement cycle through the seed makes the
    # lineage (and therefore blocking) ill-defined.
    if any(q.seed_goal in env.goals.get(g, {}).get("refines", []) for g in lineage):
        ob("hard", UNCHECKED, f"goal refinement cycle through {q.seed_goal} (WF(E) violated)")

    # O1 Actor: existence and participation in the assessment situation.
    actor = None
    if q.actor:
        a.read(q.actor)
        actor = env.actors.get(q.actor)
        if actor is None:
            ob("hard", FAIL, f"actor {q.actor} undefined")
        else:
            active = q.actor in ctx["activeActors"]
            responsible = bool(set(actor["responsibleFor"]) & set(lineage))
            if active or responsible:
                ob("hard", PASS, f"actor {q.actor} participates "
                   f"({'active in ' + q.context if active else 'responsible for the seed lineage'})")
            else:
                ob("hard", FAIL, f"actor {q.actor} is neither active in {q.context} nor responsible for the seed lineage")
    # O2 Capabilities.
    for act in q.actions:
        a.read(act)
        if act not in env.actions:
            ob("hard", FAIL, f"action {act} undefined")
        elif actor is not None:
            if act in actor["capabilities"]:
                ob("hard", PASS, f"actor {q.actor} has capability {act}")
            else:
                ob("hard", FAIL, f"actor {q.actor} lacks capability {act}")
    # O3 Authority presence.
    if q.authority_of:
        a.read(q.authority_of)
        holder = env.actors.get(q.authority_of)
        if holder is None:
            ob("hard", FAIL, f"authority holder {q.authority_of} undefined")
        elif one(holder["authority"]):
            ob("hard", PASS, f"{q.authority_of} has an authority level")
        else:
            ob("hard", FAIL, f"{q.authority_of} has no authority level")
    # O4 Domain concepts and O5 properties.
    for cid in q.concepts:
        a.read(cid)
        ok = cid in env.domain
        ob("hard", PASS if ok else FAIL, f"domain concept {cid} {'defined' if ok else 'undefined'}")
    for pid in q.properties:
        a.read(pid)
        owners = [c for c in q.concepts if pid in env.domain.get(c, {}).get("properties", [])]
        if pid not in env.properties:
            ob("hard", FAIL, f"domain property {pid} undefined")
        elif not owners:
            ob("hard", FAIL, f"domain property {pid} is not a property of any referenced concept")
        else:
            ob("hard", PASS, f"domain property {pid} belongs to {owners[0]}")
    # O6 Interaction: existence, endpoint, direction, exchanged data, protocol.
    if q.interaction:
        a.read(q.interaction)
        it = env.interactions.get(q.interaction)
        if it is None:
            ob("hard", FAIL, f"interaction {q.interaction} undefined")
        else:
            src, tgt = one(it["source"]), one(it["target"])
            problems = []
            ambiguous_ends = len(it["source"]) > 1 or len(it["target"]) > 1
            if ambiguous_ends:
                # Endpoint and direction checks would rest on an arbitrary choice
                # among conflicting values: they are not decided (see O9).
                ob("hard", UNCHECKED, f"{q.interaction} has conflicting source/target values; "
                   "endpoint and direction checks not decided")
            if not ambiguous_ends and q.actor and q.actor not in it["source"] + it["target"]:
                problems.append(f"actor {q.actor} is not an endpoint of {q.interaction}")
            if not ambiguous_ends and q.interaction_source and src != q.interaction_source:
                problems.append(f"{q.interaction} originates from {src}, expected {q.interaction_source}")
            if q.concepts and not (set(it["data"]) & set(q.concepts)):
                problems.append(f"{q.interaction} exchanges none of the referenced concepts")
            if q.requires_protocol and not one(it["protocol"]):
                problems.append(f"{q.interaction} declares no protocol")
            for msg in problems:
                ob("hard", FAIL, msg)
            if not problems and not ambiguous_ends:
                ob("hard", PASS, f"interaction {q.interaction} ({src} -> {tgt}) satisfies endpoint, "
                   "direction, data and protocol checks")

    # O7 Applicable constraints, discharged by registered validators.
    routes = applicable_constraints(a, lineage)
    for cid in sorted(routes):
        a.read(cid)
        c = env.constraints.get(cid)
        declared_soft = cid in q.soft
        if c is None:
            ob("soft" if declared_soft else "hard", UNCHECKED, f"constraint {cid} (via {routes[cid]}) undefined")
            continue
        if cid in env.conflicts:
            ob("hard", UNCHECKED, f"constraint {cid} has conflicting values {env.conflicts[cid]}; not evaluated")
            continue
        level = (one(c["enforcement"]) or ("soft" if declared_soft else "hard")).strip().lower()
        level = "soft" if level == "soft" else "hard"
        for x in c["exceptions"]:
            a.read(x)
        validator = VALIDATORS.get(one(c["validatorKey"]) or "")
        if validator is None:
            ob(level, UNCHECKED, f"{level} constraint {cid} (via {routes[cid]}) has no registered validator")
            continue
        outcome, msg = validator(a, cid, c)
        if outcome == NOT_TRIGGERED:
            a.record(level, NOT_TRIGGERED, msg)
        else:
            ob(level, outcome, msg)

    # O8 Uncertainties blocking the seed lineage or affecting consulted evidence.
    evidence = q.references() | set(lineage) | set(routes) | {q.context}
    for uid, u in sorted(env.uncertainties.items()):
        blocking = sorted(set(u["blocks"]) & set(lineage))
        affecting = sorted(set(u["affects"]) & evidence)
        if not blocking and not affecting:
            continue
        a.read(uid)
        if uid in env.conflicts:
            ob("hard", UNCHECKED, f"{uid} has conflicting values {env.conflicts[uid]}; not interpreted")
            continue
        status, impact = one(u["status"]), (one(u["impact"]) or "high")
        if blocking:
            if status == "unvalidated":
                open_u.append(uid)
                a.record("hard", "open", f"{uid} (unvalidated) blocks {blocking[0]}")
            elif status == "validated":
                a.record("hard", PASS, f"{uid} blocking {blocking[0]} is validated")
            elif status == "rejected":
                ob("hard", FAIL, f"{uid} blocking {blocking[0]} was refuted (status rejected)")
            else:
                ob("hard", UNCHECKED, f"{uid} blocking {blocking[0]} has uninterpretable status {status!r}")
        else:
            if status == "unvalidated":
                if impact in ("high", "critical"):
                    open_u.append(uid)
                    a.record("hard", "open", f"{uid} (unvalidated, {impact}) affects consulted evidence {affecting}")
                else:
                    ob("soft", FAIL, f"{uid} (unvalidated, {impact}) affects consulted evidence {affecting}")
            elif status == "validated":
                a.record("soft", PASS, f"{uid} affecting {affecting} is validated")
            elif status == "rejected":
                ob("hard", UNCHECKED, f"{uid} invalidates consulted evidence {affecting}; review required")
            else:
                ob("hard", UNCHECKED, f"{uid} affecting {affecting} has uninterpretable status {status!r}")

    # O9 Conflicting evidence on any consulted element routes to review.
    for eid in sorted(a.reads):
        if eid in env.conflicts:
            ob("hard", UNCHECKED, f"conflicting values for {eid}: {env.conflicts[eid]}")
        if eid in env.multi_typed:
            ob("hard", UNCHECKED, f"{eid} is typed in several views: {env.multi_typed[eid]}")

    if hard_fail:
        state = REJECTED
    elif hard_unchecked:
        state = PENDING_REVIEW
    elif open_u:
        state = CONDITIONAL
    elif soft_res:
        state = ACCEPTED_WITH_RESERVATIONS
    else:
        state = ACCEPTED
    prefix = {PASS: "OK", FAIL: "FAIL", UNCHECKED: "UNCHECKED", NOT_TRIGGERED: "NOT TRIGGERED", "open": "OPEN"}
    just = [f"{prefix.get(o, o.upper())} [{lvl}]: {m}" for lvl, o, m in a.log]
    return Result(q.rid, state, just, set(a.reads), list(a.log), env.snapshot)


# ---------------------------------------------------------------------------
# Change impact
# ---------------------------------------------------------------------------
def touched_identifiers(g_old: rdflib.Graph, g_new: rdflib.Graph) -> Set[str]:
    """Identifiers occurring as subject or IRI object (other than an rdf:type class) of a
    triple added to or removed from the environment snapshot."""
    a, b = environment_triples(g_old), environment_triples(g_new)
    out: Set[str] = set()
    for s, p, o in a ^ b:
        out.add(local(s))
        if isinstance(o, URIRef) and p != RDF.type:
            out.add(local(o))
    return out


def subject_identifiers(g_old: rdflib.Graph, g_new: rdflib.Graph) -> Set[str]:
    """Element-level diff that records only modified subjects (coarser)."""
    return {local(s) for s, _, _ in environment_triples(g_old) ^ environment_triples(g_new)}


def direct_reevaluation(delta: Set[str], records: Dict[str, Set[str]]) -> Set[str]:
    """DirectReEval(Δ) = { r | T_r ∩ Δ ≠ ∅ }."""
    return {rid for rid, trace in records.items() if trace & delta}


def requirements_of(element: str, records: Dict[str, Set[str]]) -> Set[str]:
    return {rid for rid, trace in records.items() if element in trace}


def dependency_closure(env: Environment, delta: Set[str]) -> Set[str]:
    """Transitive dependency closure used with coarse (view-level) traces:
    auxiliary elements are lifted to their owners (property/invariant -> concept,
    action -> actors holding it), and goal changes propagate to sub-goals."""
    owners: Dict[str, Set[str]] = {}
    for cid, c in env.domain.items():
        for x in c["properties"] + c["invariants"]:
            owners.setdefault(x, set()).add(cid)
    for aid, act in env.actors.items():
        for x in act["capabilities"]:
            owners.setdefault(x, set()).add(aid)
    children: Dict[str, Set[str]] = {}
    for gid, gd in env.goals.items():
        for p in gd["refines"]:
            children.setdefault(p, set()).add(gid)
    out, frontier = set(delta), list(delta)
    while frontier:
        x = frontier.pop()
        for y in owners.get(x, set()) | children.get(x, set()):
            if y not in out:
                out.add(y)
                frontier.append(y)
    return out


# ---------------------------------------------------------------------------
# Identity migration (rename / split / merge) through reo:supersededBy
# ---------------------------------------------------------------------------
def supersession_map(g: rdflib.Graph) -> Dict[str, List[str]]:
    m: Dict[str, List[str]] = {}
    for s, o in g.subject_objects(REO.supersededBy):
        m.setdefault(local(s), []).append(local(o))
    return {k: sorted(v) for k, v in m.items()}


def migrate_requirement(q: Requirement, env: Environment, mapping: Dict[str, List[str]]) -> Tuple[Requirement, List[str]]:
    """Rewrite references through the supersession map. A split reference is
    resolved automatically only if the referenced properties/actions identify a
    unique successor; otherwise it is reported as ambiguous."""
    from copy import deepcopy
    q2, notes = deepcopy(q), []

    def succ_single(x):
        s = mapping.get(x)
        if not s:
            return x
        if len(s) == 1:
            notes.append(f"renamed/merged {x} -> {s[0]}")
            return s[0]
        return None  # split: decided by caller

    for attr in ("seed_goal", "context", "actor", "authority_of", "interaction", "interaction_source"):
        v = getattr(q2, attr)
        if v:
            r = succ_single(v)
            if r is None:
                notes.append(f"AMBIGUOUS split of {v} -> {mapping[v]}")
                setattr(q2, attr, v)  # left unresolved
            else:
                setattr(q2, attr, r)
    for attr in ("actions", "properties", "hard", "soft"):
        new = []
        for v in getattr(q2, attr):
            r = succ_single(v)
            if r is None:
                notes.append(f"AMBIGUOUS split of {v} -> {mapping[v]}")
                new.append(v)
            else:
                new.append(r)
        setattr(q2, attr, sorted(set(new)))
    concepts = []
    for c in q2.concepts:
        s = mapping.get(c)
        if not s:
            concepts.append(c)
        elif len(s) == 1:
            notes.append(f"renamed/merged {c} -> {s[0]}")
            concepts.append(s[0])
        else:
            owners = sorted({o for o in s for p in q2.properties if p in env.domain.get(o, {}).get("properties", [])})
            if len(owners) >= 1 and q2.properties:
                notes.append(f"split {c} resolved by referenced properties -> {owners}")
                concepts.extend(owners)
            else:
                notes.append(f"AMBIGUOUS split of {c} -> {s}")
                concepts.append(c)
    q2.concepts = sorted(set(concepts))
    return q2, notes


def rederive(env: Environment, q: Requirement, mapping: Dict[str, List[str]]) -> Result:
    """Identity-aware re-derivation (Section III-F): rewrite the references of q
    through reo:supersededBy, then validate. A requirement whose reference is
    split ambiguously is sent to review. Without supersession links this is
    exactly validate(env, q)."""
    if not mapping:
        return validate(env, q)
    q2, notes = migrate_requirement(q, env, mapping)
    if any(n.startswith("AMBIGUOUS") for n in notes):
        r = validate(env, q)
        return Result(q.rid, PENDING_REVIEW, notes + r.justifications, r.trace, r.obligations, r.snapshot)
    r = validate(env, q2)
    r.justifications = notes + r.justifications
    return r


# ---------------------------------------------------------------------------
# PROV-O decision records
# ---------------------------------------------------------------------------
def record_graph(results: List[Result], requirements_ns=REQ, timestamp: str = "2026-10-07T00:00:00Z") -> rdflib.Graph:
    g = rdflib.Graph()
    g.bind("reo", REO); g.bind("prov", PROV); g.bind("req", requirements_ns); g.bind("ex", EX)
    rec_ns = Namespace(str(requirements_ns).rstrip("#") + "/records#")
    g.bind("rec", rec_ns)
    for r in results:
        rec, act = rec_ns[f"{r.rid}-{r.snapshot[:12]}"], rec_ns[f"{r.rid}-{r.snapshot[:12]}-validation"]
        g.add((rec, RDF.type, REO.DerivationRecord))
        g.add((rec, REO.assesses, requirements_ns[r.rid]))
        g.add((rec, REO.hasDecision, STATE_IRI[r.state]))
        g.add((rec, REO.environmentSnapshot, Literal(r.snapshot)))
        g.add((rec, REO.policyVersion, Literal(POLICY_VERSION)))
        g.add((rec, PROV.wasGeneratedBy, act))
        g.add((act, RDF.type, REO.ValidationActivity))
        g.add((act, PROV.startedAtTime, Literal(timestamp, datatype=rdflib.XSD.dateTime)))
        for j in r.justifications:
            g.add((rec, REO.hasJustification, Literal(j)))
        for e in sorted(r.trace):
            g.add((act, REO.consulted, EX[e]))
    return g
