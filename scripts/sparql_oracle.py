#!/usr/bin/env python3
"""Second, declarative implementation of the derivation contract (N-version).

The decision policy of the paper (obligation table + decision order) is
re-encoded as SPARQL queries evaluated directly on the RDF graph
(ontology + environment + requirement annotations). It shares no code with
``reo_checker.py``: no projection into Python dictionaries, no read-set
bookkeeping. Used for differential testing over the mutation corpus.

``decide(graph)`` returns {requirement id: decision state} for every
reo:Requirement in the graph.
"""
from __future__ import annotations

from collections import defaultdict

from rdflib import Graph

PFX = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX reo:  <http://re-environment-onto.org/ontology#>
"""

# Reusable graph patterns -------------------------------------------------
LINEAGE = "?r reo:hasSeedGoal ?s0 . ?s0 reo:refines* ?lg . ?lg rdf:type/rdfs:subClassOf* reo:Goal ."
REFPATH = ("(reo:hasResponsibleActor|reo:requiresAuthorityOf|reo:performsAction|reo:refersToConcept|"
           "reo:refersToProperty|reo:usesInteraction|reo:expectsInteractionSource)")
APPLICABLE = f"""
  {{ ?r reo:declaresHardConstraint ?c }} UNION {{ ?r reo:declaresSoftConstraint ?c }}
  UNION {{ ?r reo:assessedInContext ?ax . ?ax reo:hasActiveConstraint ?c }}
  UNION {{ ?r (reo:hasResponsibleActor|reo:requiresAuthorityOf) ?aa .
           ?aa rdf:type/rdfs:subClassOf* reo:Actor . ?aa reo:isSubjectTo ?c }}
  UNION {{ ?r reo:usesInteraction ?ai . ?ai rdf:type/rdfs:subClassOf* reo:Interaction . ?ai reo:governedBy ?c }}
  UNION {{ ?r {REFPATH} ?ae . ?c reo:appliesTo ?ae . ?c rdf:type/rdfs:subClassOf* reo:Constraint }}
  UNION {{ ?r reo:hasSeedGoal ?as0 . ?as0 reo:refines* ?ag . ?ag rdf:type/rdfs:subClassOf* reo:Goal .
           ?c reo:appliesTo ?ag . ?c rdf:type/rdfs:subClassOf* reo:Constraint }}
"""
# Level of an applicable constraint: its enforcementLevel if "soft"/"hard",
# otherwise soft when declared soft, else hard.
LEVEL = """
  OPTIONAL { ?c reo:enforcementLevel ?enf . ?c rdf:type/rdfs:subClassOf* reo:Constraint
             FILTER NOT EXISTS { ?c reo:enforcementLevel ?enf2 FILTER(?enf2 != ?enf) } }
  BIND(EXISTS { ?c ?cfp ?cv1, ?cv2 . FILTER(?cv1 != ?cv2)
                FILTER(?cfp IN (reo:enforcementLevel, reo:validatorKey, reo:formalExpression)) } AS ?cconflict)
  BIND(IF(?cconflict, "hard",
       IF(BOUND(?enf), IF(LCASE(STR(?enf)) = "soft", "soft", "hard"),
          IF(EXISTS { ?r reo:declaresSoftConstraint ?c }, "soft", "hard"))) AS ?level)
"""
EVIDENCE = f"""
  {{ ?r {REFPATH} ?ev }} UNION {{ ?r reo:hasSeedGoal ?es . ?es reo:refines* ?ev . ?ev rdf:type/rdfs:subClassOf* reo:Goal }}
  UNION {{ ?r reo:assessedInContext ?ev }} UNION {{ SELECT ?r ?ev WHERE {{ {APPLICABLE.replace('?c', '?ev')} }} }}
"""

Q_REQS = PFX + "SELECT ?r ?id WHERE { ?r a reo:Requirement ; reo:requirementId ?id }"
Q_ANCHORED = PFX + """SELECT ?r WHERE { ?r a reo:Requirement ; reo:hasSeedGoal ?s ; reo:assessedInContext ?x .
  ?s rdf:type/rdfs:subClassOf* reo:Goal . ?x rdf:type/rdfs:subClassOf* reo:Context . }"""
Q_HASREFS = PFX + """SELECT DISTINCT ?r WHERE { ?r a reo:Requirement .
  ?r (reo:hasResponsibleActor|reo:performsAction|reo:refersToConcept|reo:refersToProperty|reo:usesInteraction) ?e }"""

# Structural hard failures --------------------------------------------------
Q_STRUCT_FAIL = PFX + f"""SELECT DISTINCT ?r ?why WHERE {{ ?r a reo:Requirement .
 {{ ?r reo:hasResponsibleActor ?a . FILTER NOT EXISTS {{ ?a rdf:type/rdfs:subClassOf* reo:Actor }} BIND("actor-undefined" AS ?why) }}
 UNION {{ ?r reo:hasResponsibleActor ?a . ?a rdf:type/rdfs:subClassOf* reo:Actor .
          FILTER NOT EXISTS {{ ?r reo:assessedInContext ?x . ?x reo:hasActiveActor ?a }}
          FILTER NOT EXISTS {{ {LINEAGE} ?a reo:isResponsibleFor ?lg }} BIND("actor-not-participating" AS ?why) }}
 UNION {{ ?r reo:performsAction ?act . FILTER NOT EXISTS {{ ?act rdf:type/rdfs:subClassOf* reo:Action }} BIND("action-undefined" AS ?why) }}
 UNION {{ ?r reo:hasResponsibleActor ?a ; reo:performsAction ?act . ?a rdf:type/rdfs:subClassOf* reo:Actor .
          ?act rdf:type/rdfs:subClassOf* reo:Action . FILTER NOT EXISTS {{ ?a reo:hasCapability ?act }} BIND("lacks-capability" AS ?why) }}
 UNION {{ ?r reo:requiresAuthorityOf ?h . FILTER NOT EXISTS {{ ?h rdf:type/rdfs:subClassOf* reo:Actor }} BIND("holder-undefined" AS ?why) }}
 UNION {{ ?r reo:requiresAuthorityOf ?h . ?h rdf:type/rdfs:subClassOf* reo:Actor .
          FILTER NOT EXISTS {{ ?h reo:authorityLevel ?av FILTER(STRLEN(STR(?av)) > 0) }} BIND("holder-no-authority" AS ?why) }}
 UNION {{ ?r reo:refersToConcept ?k . FILTER NOT EXISTS {{ ?k rdf:type/rdfs:subClassOf* reo:DomainConcept }} BIND("concept-undefined" AS ?why) }}
 UNION {{ ?r reo:refersToProperty ?p . FILTER NOT EXISTS {{ ?p rdf:type/rdfs:subClassOf* reo:DomainProperty }} BIND("property-undefined" AS ?why) }}
 UNION {{ ?r reo:refersToProperty ?p . ?p rdf:type/rdfs:subClassOf* reo:DomainProperty .
          FILTER NOT EXISTS {{ ?r reo:refersToConcept ?k . ?k rdf:type/rdfs:subClassOf* reo:DomainConcept . ?k reo:hasProperty ?p }}
          BIND("property-not-owned" AS ?why) }}
 UNION {{ ?r reo:usesInteraction ?i . FILTER NOT EXISTS {{ ?i rdf:type/rdfs:subClassOf* reo:Interaction }} BIND("interaction-undefined" AS ?why) }}
 UNION {{ ?r reo:usesInteraction ?i ; reo:hasResponsibleActor ?a . ?i rdf:type/rdfs:subClassOf* reo:Interaction .
          FILTER NOT EXISTS {{ ?i reo:hasSource ?a }} FILTER NOT EXISTS {{ ?i reo:hasTarget ?a }} FILTER NOT EXISTS {{ ?i reo:hasSource ?xs1, ?xs2 FILTER(?xs1 != ?xs2) }} FILTER NOT EXISTS {{ ?i reo:hasTarget ?xt1, ?xt2 FILTER(?xt1 != ?xt2) }} BIND("actor-not-endpoint" AS ?why) }}
 UNION {{ ?r reo:usesInteraction ?i ; reo:expectsInteractionSource ?es . ?i rdf:type/rdfs:subClassOf* reo:Interaction .
          FILTER NOT EXISTS {{ ?i reo:hasSource ?es }} FILTER NOT EXISTS {{ ?i reo:hasSource ?xs1, ?xs2 FILTER(?xs1 != ?xs2) }} FILTER NOT EXISTS {{ ?i reo:hasTarget ?xt1, ?xt2 FILTER(?xt1 != ?xt2) }} BIND("wrong-direction" AS ?why) }}
 UNION {{ ?r reo:usesInteraction ?i ; reo:refersToConcept ?k0 . ?i rdf:type/rdfs:subClassOf* reo:Interaction .
          FILTER NOT EXISTS {{ ?r reo:refersToConcept ?k1 . ?i reo:exchangesData ?k1 }} BIND("no-data-overlap" AS ?why) }}
 UNION {{ ?r reo:usesInteraction ?i ; reo:requiresProtocol true . ?i rdf:type/rdfs:subClassOf* reo:Interaction .
          FILTER NOT EXISTS {{ ?i reo:protocol ?pv FILTER(STRLEN(STR(?pv)) > 0) }} BIND("no-protocol" AS ?why) }}
}}"""

# Constraint outcomes --------------------------------------------------------
# For every applicable constraint: level and outcome in {pass, fail, unchecked, not_triggered}.
Q_CONSTRAINTS = PFX + f"""SELECT DISTINCT ?r ?c ?level ?outcome WHERE {{ ?r a reo:Requirement .
 {{ SELECT DISTINCT ?r ?c WHERE {{ ?r a reo:Requirement . {APPLICABLE} }} }}
 {LEVEL}
 OPTIONAL {{ ?c reo:validatorKey ?key }}
 OPTIONAL {{ ?c reo:formalExpression ?fx }}
 BIND(STRBEFORE(COALESCE(STR(?fx), ""), " →") AS ?ant0)
 BIND(IF(CONTAINS(?ant0, "("), STRBEFORE(?ant0, "("), ?ant0) AS ?ant)
 BIND(STRAFTER(COALESCE(STR(?fx), ""), "actor.authority = ") AS ?required)
 BIND(EXISTS {{ ?r reo:performsAction ?ta . ?ta rdfs:label ?tl . FILTER(STR(?tl) = ?ant) }} AS ?triggered)
 OPTIONAL {{ ?r reo:requiresAuthorityOf ?h0 }}
 OPTIONAL {{ ?r reo:hasResponsibleActor ?h1 }}
 BIND(COALESCE(?h0, ?h1) AS ?holder)
 OPTIONAL {{ ?r reo:assessedInContext ?cx }}
 BIND(
  IF(NOT EXISTS {{ ?c rdf:type/rdfs:subClassOf* reo:Constraint }}, "unchecked",
  IF(?cconflict, "unchecked",
  IF(EXISTS {{ ?r reo:performsAction ?ca . ?ca rdfs:label ?cl1, ?cl2 . FILTER(?cl1 != ?cl2) }}, "unchecked",
  IF(!BOUND(?key) || !(STR(?key) IN ("authority-equals", "consent-or-exception")), "unchecked",
  IF(STR(?key) = "authority-equals",
     IF(STRLEN(?ant) = 0 || STRLEN(?required) = 0, "unchecked",
     IF(!?triggered, "not_triggered",
     IF(NOT EXISTS {{ ?holder rdf:type/rdfs:subClassOf* reo:Actor }}, "fail",
     IF(EXISTS {{ ?holder reo:authorityLevel ?x1, ?x2 FILTER(?x1 != ?x2) }}, "unchecked",
     IF(EXISTS {{ ?holder reo:authorityLevel ?av FILTER(STR(?av) = ?required) }}, "pass", "fail"))))),
     IF(STRLEN(?ant) = 0, "unchecked",
     IF(!?triggered, "not_triggered",
     IF(EXISTS {{ ?c reo:hasException ?cx }} || EXISTS {{ ?cx reo:contextProperty "consent_obtained=true" }}, "pass", "fail"))))))))
  AS ?outcome)
}}"""

# Uncertainties -----------------------------------------------------------
Q_UNCERTAINTY = PFX + f"""SELECT DISTINCT ?r ?u ?kind ?status ?impact WHERE {{ ?r a reo:Requirement .
 ?u rdf:type/rdfs:subClassOf* reo:Uncertainty .
 {{ ?u reo:blocks ?lg . {LINEAGE} BIND("blocking" AS ?kind) }}
 UNION {{ ?u reo:affects ?ev . {EVIDENCE} BIND("affecting" AS ?kind)
          FILTER NOT EXISTS {{ ?u reo:blocks ?lg2 . ?r reo:hasSeedGoal ?s2 . ?s2 reo:refines* ?lg2 .
                               ?lg2 rdf:type/rdfs:subClassOf* reo:Goal }} }}
 OPTIONAL {{ ?u reo:status ?status }}
 OPTIONAL {{ ?u reo:impactLevel ?impact }}
}}"""

Q_CYCLE = PFX + """SELECT DISTINCT ?r WHERE { ?r a reo:Requirement ; reo:hasSeedGoal ?s . ?s reo:refines* ?g .
  ?g rdf:type/rdfs:subClassOf* reo:Goal . ?g reo:refines ?s . }"""

# Conflicting evidence on consulted elements ------------------------------------
CONSULTED = f"""
  {{ ?r {REFPATH} ?e }} UNION {{ ?r (reo:hasSeedGoal|reo:assessedInContext) ?e }}
  UNION {{ ?r reo:hasSeedGoal ?cs . ?cs reo:refines* ?e . ?e rdf:type/rdfs:subClassOf* reo:Goal }}
  UNION {{ SELECT ?r ?e WHERE {{ {APPLICABLE.replace('?c', '?e')} }} }}
  UNION {{ SELECT ?r ?e WHERE {{ {APPLICABLE} ?c reo:hasException ?e . ?c rdf:type/rdfs:subClassOf* reo:Constraint }} }}
"""
Q_CONFLICT = PFX + f"""SELECT DISTINCT ?r ?e WHERE {{ ?r a reo:Requirement .
 {{ {CONSULTED} }}
 {{ ?e ?fp ?v1, ?v2 . FILTER(?v1 != ?v2)
    FILTER(?fp IN (reo:authorityLevel, reo:enforcementLevel, reo:validatorKey, reo:formalExpression,
                   reo:status, reo:impactLevel, reo:hasSource, reo:hasTarget, reo:protocol, rdfs:label))
    FILTER(?fp != rdfs:label || EXISTS {{ ?e rdf:type/rdfs:subClassOf* reo:Action }}) }}
 UNION {{ ?e rdf:type/rdfs:subClassOf* ?root1 . ?e rdf:type/rdfs:subClassOf* ?root2 .
          VALUES ?root1 {{ reo:Actor reo:Goal reo:DomainConcept reo:Constraint reo:Context reo:Uncertainty
                          reo:Interaction reo:Action reo:DomainProperty reo:DomainInvariant }}
          VALUES ?root2 {{ reo:Actor reo:Goal reo:DomainConcept reo:Constraint reo:Context reo:Uncertainty
                          reo:Interaction reo:Action reo:DomainProperty reo:DomainInvariant }}
          FILTER(?root1 != ?root2) }}
}}"""

# Uncertainties considered are consulted too.
Q_CONFLICT_U = PFX + f"""SELECT DISTINCT ?r ?u WHERE {{ ?r a reo:Requirement .
 ?u rdf:type/rdfs:subClassOf* reo:Uncertainty .
 {{ ?u reo:blocks ?lg . {LINEAGE} }} UNION {{ ?u reo:affects ?ev . {EVIDENCE} }}
 {{ ?u ?fp ?v1, ?v2 . FILTER(?v1 != ?v2) FILTER(?fp IN (reo:status, reo:impactLevel)) }}
 UNION {{ ?u rdf:type/rdfs:subClassOf* ?root2 .
          VALUES ?root2 {{ reo:Actor reo:Goal reo:DomainConcept reo:Constraint reo:Context
                          reo:Interaction reo:Action reo:DomainProperty reo:DomainInvariant }} }}
}}"""


def _local(v) -> str:
    s = str(v)
    return s.split("#")[-1] if "#" in s else s.rsplit("/", 1)[-1]


def decide(g: Graph) -> dict:
    ids = {r: str(i) for r, i in g.query(Q_REQS)}
    anchored = {r for (r,) in g.query(Q_ANCHORED)}
    hasrefs = {r for (r,) in g.query(Q_HASREFS)}
    fail, unchecked, opened, soft = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    for r, why in g.query(Q_STRUCT_FAIL):
        fail[r].add(str(why))
    for r, c, level, outcome in g.query(Q_CONSTRAINTS):
        o, lv = str(outcome), str(level)
        if o in ("fail", "unchecked"):
            (soft if lv == "soft" else (fail if o == "fail" else unchecked))[r].add(f"{_local(c)}:{o}")
    # Uncertainties: blocking takes precedence over affecting for the same (r, u).
    conflict_u = {(r, u) for r, u in g.query(Q_CONFLICT_U)}
    per = defaultdict(dict)
    for r, u, kind, status, impact in g.query(Q_UNCERTAINTY):
        k = str(kind)
        cur = per[(r, u)]
        if k == "blocking" or "kind" not in cur:
            cur.update(kind=k, status=None if status is None else str(status),
                       impact=None if impact is None else str(impact))
    for (r, u), d in per.items():
        if (r, u) in conflict_u:
            unchecked[r].add(f"{_local(u)}:conflict")
            continue
        st, imp = d["status"], (d["impact"] or "high")
        if d["kind"] == "blocking":
            if st == "unvalidated":
                opened[r].add(_local(u))
            elif st == "rejected":
                fail[r].add(f"{_local(u)}:refuted")
            elif st != "validated":
                unchecked[r].add(f"{_local(u)}:status")
        else:
            if st == "unvalidated":
                (opened if imp in ("high", "critical") else soft)[r].add(_local(u))
            elif st != "validated":
                unchecked[r].add(f"{_local(u)}:affecting")
    for (r,) in g.query(Q_CYCLE):
        unchecked[r].add("cycle")
    for r, e in g.query(Q_CONFLICT):
        unchecked[r].add(f"conflict:{_local(e)}")
    for r, u in g.query(Q_CONFLICT_U):
        unchecked[r].add(f"conflict:{_local(u)}")
    out = {}
    for r, rid in ids.items():
        if r not in anchored:
            out[rid] = "not_derived"
        elif r not in hasrefs:
            out[rid] = "pending_review"
        elif fail[r]:
            out[rid] = "rejected"
        elif unchecked[r]:
            out[rid] = "pending_review"
        elif opened[r]:
            out[rid] = "conditional"
        elif soft[r]:
            out[rid] = "accepted_with_reservations"
        else:
            out[rid] = "accepted"
    return out
