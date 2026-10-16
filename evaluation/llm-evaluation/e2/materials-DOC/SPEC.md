# EC-RE specification (excerpt of the paper)

This is the published specification of the REO vocabulary and of the derivation contract (paper Sections III, IV-B/C, V and VII). Machine-readable files in this folder: `reo-core.ttl`, `reo-derivation.ttl` (ontology modules), `hospital.ttl`, `hospital-extension.ttl` (example environment), `hospital-requirements.ttl` (ten annotated requirements). Decision state names used in answers: accepted, accepted_with_reservations, conditional, pending_review, rejected, not_derived.

# Foundations of Environment-Centric RE

## Environment model



An environment model at version $t$ is a tuple $\mathcal{E}_t=\langle A_t,G_t,D_t,C_t,X_t,U_t,I_t\rangle$ of finite sets of typed elements: actors, goals, domain concepts, constraints, contexts, uncertainties, and interactions, together with auxiliary elements (actions, domain properties, invariants) and typed links among them.



The views are roles that elements play in assessing a requirement, not seven independent databases. An actor answers *who* acts and with which capability and authority; a goal *why* the requirement exists; a domain concept *what* it refers to; a constraint *which rules* bound it; a context *in which situation* it is assessed; an uncertainty *which premise* is still open; an interaction *through which exchange* it is realized.

## Overlaps and role separation

Overlaps are resolved by role separation: one real-world entity that plays several roles is represented by distinct role individuals linked explicitly. A pharmacy information system that exchanges patient records is an actor; the record is a domain concept; the exchange is an interaction. “Fast response is desired” motivates a goal, whereas “responses within 2 s” is a quality constraint. REO v1.1.0 enforces this discipline with a disjointness axiom over the seven view classes and the three auxiliary classes, so that a reasoner rejects, for example, a goal used as the source of an interaction (Section [sec:eval-onto]).

## Extension contract

An extension declares its classes and predicates, their meaning, and the obligations they introduce, and states which links affect applicability, uncertainty propagation, and trace recording. Because the checker computes view membership through the `rdfs:subClassOf` closure, a project-specific subclass (for example a temporal constraint) is recognized without code changes; a new obligation, in contrast, requires a registered validator, and an applicable hard constraint without one sends the requirement to review rather than to acceptance. An extension is *conservative* for the contract if all regression scenarios and competency questions keep their results when the extension vocabulary is loaded but not instantiated. We check this for a vocabulary extension that introduces a temporal-constraint subclass with a validity bound (Section [sec:eval-contract]).

## Well-formedness

A well-formedness predicate $WF(\mathcal{E})$ requires referential integrity and acyclic refinement, for instance $$\begin{aligned}
&\mathit{stakeholders}(g)\subseteq A, && g\in G, \\
&\mathit{source}(i)\in A,\ \ \mathit{data}(i)\subseteq D, && i\in I, \\
&\mathit{blocks}(u)\subseteq G, && u\in U,
\end{aligned}$$ and $g\notin\mathit{ancestors}(g)$. These conditions are enforced by SHACL shapes and, for typing errors, by OWL disjointness; the contract additionally refuses to decide when a refinement cycle passes through the seed goal.

## Slices, traces, and evolution

A requirement $q$ is assessed for a seed goal $s$ and a context $x$. Its *lineage* $L(s)$ is $s$ with its ancestors under `refines`. The contract (Section [sec:derivation]) consults a finite set of elements: $s$, $x$, $L(s)$, the elements referenced by $q$, the constraints applicable to $q$ and their exception contexts, and the uncertainties that block $L(s)$ or affect those elements. We call this set the *read set* and record it as the trace $\mathsf{T}_q$.

For two snapshots $\mathcal{E}_t$ and $\mathcal{E}_{t+1}$ with RDF graphs $\mathcal{G}_t$ and $\mathcal{G}_{t+1}$, the *touched identifiers* are $$\begin{split}
\Delta={}&\{\,s \mid (s,p,o)\in \mathcal{G}_t \triangle \mathcal{G}_{t+1}\,\}\\
&\cup\{\,o \mid (s,p,o)\in \mathcal{G}_t \triangle \mathcal{G}_{t+1},\ o\ \text{an IRI},\ p\neq\mathit{rdf{:}type}\,\}.
\end{split}$$ The direct selection rule is $$\label{eq:direct}
\mathsf{DirectReEval}(\Delta)=\{\,q \mid \mathsf{T}_q\cap\Delta\neq\emptyset\,\}.$$ Proposition [prop:sufficiency] shows that requirements outside this set keep their assessment. Two weaker variants are evaluated for comparison: a diff that records only modified subjects, and view-level traces that keep only identifiers of the seven views, optionally completed by a transitive dependency closure (properties and invariants lifted to their concept, actions to the actors holding them, goals to their sub-goals).

Identity is handled with `reo:supersededBy`. One successor denotes a rename, several successors a split, and several predecessors with one successor a merge. Before re-derivation, references of $q$ are rewritten through this map. A split reference is resolved automatically only when the properties or actions referenced by $q$ belong to exactly one successor; otherwise the requirement is sent to review as ambiguous, because choosing a successor is an analyst decision.

## Classes and predicates

The core has 27 classes: the seven view classes, their 17 subclasses (three actor kinds, two goal kinds, four constraint kinds, four uncertainty kinds, four interaction kinds), and three auxiliary classes (`Action`, `DomainProperty`, `DomainInvariant`). The derivation module adds `Requirement`, `DerivationRecord`, `ValidationActivity`, and `DecisionState`, whose six instances (*Accepted*, *AcceptedWithReservations*, *Conditional*, *PendingReview*, *Rejected*, *NotDerived*) are declared pairwise different and form an enumerated class.

In RDF a triple has a subject, a predicate, and an object; the *subject classes* and *object classes* of a predicate are its declared domain and range. Table [tab:objprops] lists all 34 object properties with their domain and range, and Table [tab:dataprops] all 46 datatype properties. Five predicates have the range `owl:Thing` on purpose: a constraint can apply to, and an uncertainty can affect, an element of any view; an interaction can target an actor or a domain concept (refined by SHACL); traces and identity links range over all elements. The derivation predicates are the explicit mapping from a requirement sentence to environment elements: seed goal, context, responsible actor, actions, concepts, properties, interaction and its expected source, required protocol, and declared constraints.

**[tab:objprops]**

| **Domain**         | **Predicate**              | **Range**        | **Module** |
|:-------------------|:---------------------------|:-----------------|:-----------|
| owl:Thing          | `supersededBy`             | owl:Thing        | core       |
| Actor              | `hasCapability`            | Action           | core       |
| Actor              | `isResponsibleFor`         | Goal             | core       |
| Actor              | `isSubjectTo`              | Constraint       | core       |
| Constraint         | `appliesTo`                | owl:Thing        | core       |
| Constraint         | `hasException`             | Context          | core       |
| Context            | `hasActiveActor`           | Actor            | core       |
| Context            | `hasActiveConstraint`      | Constraint       | core       |
| DomainConcept      | `hasInvariant`             | DomainInvariant  | core       |
| DomainConcept      | `hasProperty`              | DomainProperty   | core       |
| DomainConcept      | `relatedTo`                | DomainConcept    | core       |
| Goal               | `hasStakeholder`           | Actor            | core       |
| Goal               | `refines`                  | Goal             | core       |
| Interaction        | `exchangesData`            | DomainConcept    | core       |
| Interaction        | `governedBy`               | Constraint       | core       |
| Interaction        | `hasSource`                | Actor            | core       |
| Interaction        | `hasTarget`                | owl:Thing        | core       |
| Uncertainty        | `affects`                  | owl:Thing        | core       |
| Uncertainty        | `blocks`                   | Goal             | core       |
| DerivationRecord   | `assesses`                 | Requirement      | derivation |
| DerivationRecord   | `hasDecision`              | DecisionState    | derivation |
| DerivationRecord   | `supersedes`               | DerivationRecord | derivation |
| Requirement        | `assessedInContext`        | Context          | derivation |
| Requirement        | `declaresHardConstraint`   | Constraint       | derivation |
| Requirement        | `declaresSoftConstraint`   | Constraint       | derivation |
| Requirement        | `expectsInteractionSource` | Actor            | derivation |
| Requirement        | `hasResponsibleActor`      | Actor            | derivation |
| Requirement        | `hasSeedGoal`              | Goal             | derivation |
| Requirement        | `performsAction`           | Action           | derivation |
| Requirement        | `refersToConcept`          | DomainConcept    | derivation |
| Requirement        | `refersToProperty`         | DomainProperty   | derivation |
| Requirement        | `requiresAuthorityOf`      | Actor            | derivation |
| Requirement        | `usesInteraction`          | Interaction      | derivation |
| ValidationActivity | `consulted`                | owl:Thing        | derivation |

The 34 object properties of REO v1.1.0: subject class (domain), predicate, object class (range), and module. `prov:wasGeneratedBy` links a record to its validation activity.



**[tab:dataprops]**

| **Domain (count)**       | **Properties**                                                                                          |
|:-------------------------|:--------------------------------------------------------------------------------------------------------|
| Actor (4)                | actorId, actorName, authorityLevel, organizationalUnit                                                  |
| Constraint (6)           | constraintId, constraintName, enforcementLevel, formalExpression, naturalLanguage, validatorKey         |
| Context (6)              | contextId, contextName, contextProperty, spatialScope, temporalEnd (dateTime), temporalStart (dateTime) |
| DomainConcept (2)        | conceptId, conceptName                                                                                  |
| DomainInvariant (3)      | formalLogic, invariantExpression, severity                                                              |
| DomainProperty (4)       | isMandatory (boolean), propertyName, propertyType, referenceTarget                                      |
| Goal (4)                 | goalId, goalName, priority (integer), refinementType                                                    |
| Interaction (4)          | interactionId, interactionName, protocol, triggeringEvent                                               |
| RegulatoryConstraint (1) | hasAuthoritativeText                                                                                    |
| Uncertainty (6)          | impactLevel, status, subject, uncertaintyId, uncertaintyName, validationPlan                            |
| DerivationRecord (3)     | environmentSnapshot, hasJustification, policyVersion                                                    |
| Requirement (3)          | requirementId, requirementText, requiresProtocol (boolean)                                              |

The 46 datatype properties by domain (range `xsd:string` unless stated).



## Four kinds of checking and their criteria

REO is used by four distinct checks, which must not be conflated. *(a) OWL reasoning* (open world): an ontology plus instance data is consistent and has no unsatisfiable named class; injected typing and cardinality errors must make it inconsistent. Absence of a value is not an error under OWL semantics. *(b) SHACL validation* (closed world): required values, datatypes, enumerations, typed references, and two SPARQL rules (goal-refinement cycle; unvalidated uncertainty blocking a goal, reported as a warning). We run pySHACL with RDFS inference and warnings allowed; a warning does not make a graph non-conforming. *(c) SPARQL competency questions* : each question has an expected answer specified separately from its execution; answers are compared as sorted rows or booleans. *(d) Requirement decisions*: the contract of Section [sec:derivation] reads the graph and the requirement annotation and returns a decision, justifications, and a trace. Its states are not OWL entailments, and the checker does not consume SHACL reports; Section [sec:eval-contract] measures how often the two disagree.

# The Environment-Bounded Derivation Contract

## Requirements as annotated candidates

A *candidate requirement* $q$ is a natural-language statement together with an explicit mapping to environment elements, stored as a `reo:Requirement`. For R001, “The Physician shall verify Medication.contraindications against Patient.current_medications before prescribing,” the mapping is

```
req:R001 a reo:Requirement ;
  reo:hasSeedGoal ex:G002 ;
  reo:assessedInContext ex:X001_EmergencyDept ;
  reo:hasResponsibleActor ex:Physician ;
  reo:requiresAuthorityOf ex:Physician ;
  reo:performsAction ex:Action_Prescribe ,
                     ex:Action_AccessRecords ;
  reo:refersToConcept ex:D001_Medication , ex:D002_Patient ;
  reo:refersToProperty ex:Prop_Contraindications ,
                       ex:Prop_CurrentMedications ;
  reo:usesInteraction ex:I001_PhysicianToEHR ;
  reo:expectsInteractionSource ex:Physician ;
  reo:requiresProtocol true ;
  reo:declaresHardConstraint ex:C002_FDA .
```

The contract evaluates the mapping, not the sentence. Producing the mapping is the interface to any candidate producer: an analyst writes it, and a future LLM-based producer would have to emit it. The mapping discipline is: identify the actor and its actions; resolve each noun phrase to one concept or property; select the seed goal and the context; name any interaction the behavior relies on; and declare rules the statement explicitly invokes. Two situations are handled by policy rather than by guessing. If a phrase can denote several elements, the analyst records an `AmbiguityUncertainty` that affects the candidate elements; the requirement then becomes *conditional* until the ambiguity is validated. If the model contains conflicting values for an attribute the contract reads—for instance two authority levels for one actor contributed by two sources—the contract does not choose: the requirement goes to *pending review*. Agreement between sentence and mapping is an input assumption; the evaluation records that changing only the sentence leaves the decision unchanged (Section [sec:eval-contract]).

## Obligations and applicability

Table [tab:obligations] lists the obligations the contract induces. Constraint applicability is computed from the requirement’s own references only: a constraint applies if the requirement declares it, if it is active in the requirement’s context, if the responsible actor or authority holder is subject to it, if the used interaction is governed by it, or if it applies to a referenced element or a goal of the seed lineage. A constraint is discharged by the validator named by its `validatorKey`. Two validators are registered for the example: `authority-equals`, which reads the antecedent action and the required authority from the formal expression “*prescribe $\rightarrow$ actor.authority = licensed_medical_professional*”; and `consent-or-exception`, which passes if the context is a declared exception or asserts consent. A rule whose antecedent action is not performed is *not triggered*. A hard constraint that is undefined, has no registered validator, or has an uninterpretable expression is *unchecked*.



| **Id** | **View** | **Obligation**                                                                                                                                                | **Outcomes**                                                                                                                                                   |
|:-------|:---------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| O1     | A, X, G  | The responsible actor exists and participates: it is active in $x$ or responsible for a goal of $L(s)$.                                                       | fail if undefined or not participating                                                                                                                         |
| O2     | A        | The actor holds every performed action as a capability.                                                                                                       | fail per missing capability                                                                                                                                    |
| O3     | A        | The authority holder exists and has an authority level.                                                                                                       | fail if absent                                                                                                                                                 |
| O4     | D        | Every referenced concept exists.                                                                                                                              | fail if undefined                                                                                                                                              |
| O5     | D        | Every referenced property exists and belongs to a referenced concept.                                                                                         | fail if undefined or not owned                                                                                                                                 |
| O6     | I        | The used interaction exists; the actor is an endpoint; the source is the expected one; it exchanges a referenced concept; it declares a protocol if required. | fail per violated condition; unchecked if sources/targets conflict                                                                                             |
| O7     | C, X     | Every applicable constraint is discharged by its registered validator.                                                                                        | pass, fail, not triggered; unchecked if undefined, unregistered, or conflicting; soft rules yield reservations                                                 |
| O8     | U, G     | No uncertainty blocking $L(s)$ is open or refuted; no uncertainty affecting consulted evidence is open.                                                       | blocking: unvalidated $\to$ open, rejected $\to$ fail; affecting: unvalidated high/critical $\to$ open, low/medium $\to$ reservation, rejected $\to$ unchecked |
| O9     | all      | No consulted element has conflicting values or several view types; no refinement cycle passes through $s$.                                                    | unchecked                                                                                                                                                      |



## Decision policy

The outcomes are aggregated by the ordered guards of Table [tab:states]; each guard applies only if the earlier ones did not. Algorithm [alg:derive] gives the procedure; the reference checker (`reo_checker.py`) implements it line by line, and `sparql_oracle.py` encodes the same policy declaratively in SPARQL.

**[tab:states]**

| **State**                  | **Guard**                  | **Meaning**                                                                        |
|:---------------------------|:---------------------------|:-----------------------------------------------------------------------------------|
| not derived                | $s\notin G$ or $x\notin X$ | No anchoring seed or context.                                                      |
| pending review             | $q$ references no element  | Prevents vacuous acceptance.                                                       |
| rejected                   | $H_f\neq\emptyset$         | A checked hard obligation failed or a blocking premise was refuted.                |
| pending review             | $H_u\neq\emptyset$         | A mandatory obligation cannot be decided with the available model and validators.  |
| conditional                | $U_o\neq\emptyset$         | Hard obligations hold, but an open premise blocks the lineage or affects evidence. |
| accepted with reservations | $S_r\neq\emptyset$         | Hard obligations hold; soft obligations failed or are unchecked.                   |
| accepted                   | otherwise                  | All induced obligations hold in the model.                                         |

Decision states in precedence order ($H_f$, $H_u$: failed and unchecked hard obligations; $U_o$: open uncertainties; $S_r$: soft reservations).





    input: environment graph $\mathcal{G}$, requirement $q$ with seed $s$ and context $x$, validator registry $V$
    output: decision $z$, justifications $J$, trace $T$
    $T\gets\{s,x\}$
    if{$s\notin G$ or $x\notin X$}
      return $\langle\mathit{notDerived},J,T\rangle$
    if{$\mathit{refs}(q)=\emptyset$}
      return $\langle\mathit{pendingReview},J,T\rangle$
    $L\gets\mathsf{lineage}(s)$;\ $T\gets T\cup L$;\ $H_f,H_u,U_o,S_r\gets\emptyset$
    evaluate O1--O6 on $\mathit{refs}(q)$; add every read element to $T$ and failures to $H_f$ or $H_u$
    $R\gets\mathsf{applicable}(q,x,L)$;\ $T\gets T\cup R\cup\mathit{refs}(q)$
    for all{$c\in R$}
      $o\gets V[\mathit{key}(c)](c,q,x)$
      // {unchecked if no validator}
      add $c$'s exception contexts to $T$; route $o$ to $H_f$, $H_u$, or $S_r$ by $\mathit{level}(c)$
    for all{$u\in U$ with $\mathit{blocks}(u)\cap L\neq\emptyset$ or $\mathit{affects}(u)\cap(\mathit{refs}(q)\cup L\cup R\cup\{x\})\neq\emptyset$}
      $T\gets T\cup\{u\}$; route $\mathit{status}(u),\mathit{impact}(u)$ to $U_o$, $H_f$, $H_u$, or $S_r$ (O8)
    add O9 conflicts on elements of $T$ to $H_u$
    $z\gets$ first guard of Table \ref{tab:states} that holds
    return $\langle z,J,T\rangle$



## Properties of the contract

The following properties are stated relative to the model and the registered validators; they say nothing about whether the model is true of the world.



A registered validator returns *pass* for an obligation only if the obligation holds under the stated semantics of the model.





Under Assumption [ass:sound], if the contract returns *accepted*, *accepted with reservations*, or *conditional*, every hard obligation induced by $q$ holds in the model.





*Proof.* These states are reached only when $H_f=H_u=\emptyset$. Every induced hard obligation is therefore *pass* or *not triggered*; the latter holds vacuously, and the former holds by Assumption [ass:sound] or, for O1–O6 and O9, by direct graph membership. ◻





Let $\mathcal{G}_t$ and $\mathcal{G}_{t+1}$ be two snapshots over the same vocabulary (no change to class or property axioms), $q$ a requirement with unchanged annotation, policy, and validator registry, and $\Delta$ the touched identifiers. If $\mathsf{T}_q\cap\Delta=\emptyset$, then the decision, justifications, and trace of $q$ are identical in both snapshots.





*Proof sketch.* Every value read by Algorithm [alg:derive] is either an attribute or outgoing link of an element in $\mathsf{T}_q$, or an incoming link whose object is in $\mathsf{T}_q$: applicability through `appliesTo` of referenced elements and lineage goals, and uncertainties through `blocks` and `affects` pointing into $\mathsf{T}_q$. A triple added to or removed from $\mathcal{G}$ that changes such a value has its subject or its IRI object in $\mathsf{T}_q$, hence in $\Delta$. If no such triple exists, all values read are identical, and by induction over the algorithm’s steps so are the set of read elements and every outcome. ◻



Proposition [prop:sufficiency] makes $\mathsf{DirectReEval}$ complete for the contract’s assessments: no requirement outside the selected set can change. A change of vocabulary, policy, or validators is a version change of the contract itself and calls for re-validating all requirements. It is a property of read-set recording; Section [sec:eval-impact] checks it empirically on 7,790 assessments and shows that the weaker traces of v1.0.0 lose it.



If an element $e\in\mathsf{T}_q$ is renamed, split, or merged and the successor snapshot links $e$ to its successors with `reo:supersededBy`, then $e\in\Delta$, so $q$ is selected; after reference migration, $q$ is re-assessed on its successors, or sent to review if a split leaves its reference ambiguous.





*Proof.* Removing the triples of $e$ (or adding the supersession triple whose subject is $e$) puts $e$ in $\Delta$; the rest follows from the migration rule of Section [sec:evolution]. ◻



## Decision records

Each assessment is serialized as a PROV-O-aligned record: a `DerivationRecord` assesses one requirement, has one decision, the SHA-256 hash of the environment snapshot, the policy version, and its justifications, and was generated by a `ValidationActivity` that `consulted` each element of the trace. Records live in the same graph as the environment, so impact analysis is a SPARQL query:

```
SELECT DISTINCT ?r WHERE {
  ?rec reo:assesses ?req ; prov:wasGeneratedBy ?act .
  ?act reo:consulted ex:Physician .
  ?req reo:requirementId ?r . }
```

The property `supersedes` links a re-derived record to the record it replaces, so that the decision history can be kept. Records are validated by SHACL; for example, an accepted record with an empty trace is a violation.

# Worked Example: Emergency Prescription

The example is a synthetic fixture that illustrates the semantics; it does not validate healthcare applicability, and the identifiers `C001_HIPAA` and `C002_FDA` are illustrative labels, not interpretations of the regulations. `hospital.ttl` (243 triples) contains three actors, five goals (G001 refined by G002–G005), two domain concepts with eight properties and three invariants, two constraints, one context, one uncertainty, and two interactions: I001 from the Physician to the EHR system exchanging patient data, and I002 from the EHR system to the Pharmacist exchanging medication data. The emergency context X001 activates C002 and is an exception of C001. U001, the unknown update frequency of the drug-interaction database, is *unvalidated* and blocks G002. The extension (38 triples) adds an outpatient context X002 without consent, a soft response-time rule C003 governing I001, and a hard dispensing-log rule C004 on the Pharmacist without a registered validator. the figure shows the part of the model read for R001.

For R001 the contract confirms that the Physician is active in X001 and holds both actions; that both properties belong to the referenced concepts; that I001 starts at the Physician, exchanges patient data, and declares HL7-FHIR; that C001 is waived because X001 is an exception; and that C002 passes because the Physician’s authority equals the required value. U001 blocks the seed, so R001 is *conditional*. On `hospital.ttl` alone its trace has 14 identifiers; with the extension, the soft rule C003 is applicable through I001 and adds a reservation, which the conditional state already dominates. SHACL reports the same model as conforming with one warning: graph conformance and requirement acceptance are different results.

Table [tab:requirements] gives the decisions for the ten requirements of `hospital-requirements.ttl` (117 triples) on the extended model. Every state except *not derived* occurs, and each decision is explained by the outcome that triggered it. The records support counterfactual questions, which we re-ran on modified snapshots: if X002 asserts consent, R008 becomes *accepted with reservations* (the C003 reservation remains); once U001 is validated, R007 becomes *accepted* and R001 *accepted with reservations*; R006 can only be repaired by assigning the prescribing action to an actor that holds it.



| **Req.** | **Seed** | **Context** | **Decision**         | **Trace** | **Determining outcome**                                                                             |
|:---------|:---------|:------------|:---------------------|:----------|:----------------------------------------------------------------------------------------------------|
| R001     | G002     | X001        | conditional          | 15        | U001_DrugDBFrequency (unvalidated) blocks G002                                                      |
| R002     | G003     | X001        | acc. w/ reservations | 12        | soft constraint C003_ResponseTime (via governedBy(I001_PhysicianToEHR)) has no registered validator |
| R003     | G004     | X001        | accepted             | 9         | all obligations hold                                                                                |
| R004     | G005     | X001        | accepted             | 9         | all obligations hold                                                                                |
| R005     | G005     | X001        | pending review       | 12        | hard constraint C004_DispensingLog (via isSubjectTo(Pharmacist)) has no registered validator        |
| R006     | G004     | X001        | rejected             | 9         | actor Pharmacist lacks capability Action_Prescribe                                                  |
| R007     | G002     | X001        | conditional          | 10        | U001_DrugDBFrequency (unvalidated) blocks G002                                                      |
| R008     | G003     | X002        | rejected             | 13        | C001_HIPAA: consent required in X002_Outpatient, which is not an exception and asserts no consent   |
| R009     | G004     | X002        | accepted             | 10        | all obligations hold                                                                                |
| R010     | G005     | X001        | rejected             | 10        | I002_EHRToPharmacy exchanges none of the referenced concepts                                        |


