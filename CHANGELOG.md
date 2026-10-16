# Changelog

## 1.1.0 (2026-10) — revision for IEEE Access resubmission

### Second internal review (2026-10-15)
- `reo_checker.environment_triples`: the snapshot hash and the touched-identifier and subject diffs ignore
  requirement annotations and decision records. These are triples whose subject is typed `Requirement`,
  `DerivationRecord` or `ValidationActivity`, or whose predicate belongs to the derivation module. Results
  are unchanged, because the evaluated graphs never contained such triples.
- `scripts/check_record_isolation.py`: adds the annotations and PROV-O records of all requirements (388
  triples) to the environment graph and checks that the touched identifiers stay empty and the hash
  unchanged. A raw diff would touch 31 environment identifiers. Also tests a single untyped `reo:consulted`
  triple.
- `ontology/reo-core.ttl`: the definitions of `reo:blocks` (a necessary premise of a goal), `reo:affects`
  and `reo:status` now state the semantics the contract uses. Only documentation changed; triple counts
  are unchanged.

### Corrections after an internal review (2026-10-15)
- `evaluation/view-derivation/criteria.json`: criterion C3 is now an explicit boolean (`C3_holds`). The
  scripts used to derive it from the free-text note, which marked provenance as satisfying C3. Provenance
  induces no obligation, as the paper states, so it now fails C3. This changes no view: the author coding
  still retains the same seven views. It also changes how E3 reads: provenance is excluded under every
  coding.
- `scripts/ir_sensitivity.py`: change-impact precision and recall of the TF-IDF document baseline at
  every threshold of the trace grid (tau = 0.05 ... 0.30). The value at tau = 0.10 is cross-checked
  against `evaluation_summary.json`. Table 15 now also shows tau = 0.05.
- `scripts/export_paper_macros.py`: SHACL agreement with exact state matching, a breakdown of false
  acceptances by contract state, a C4 column in Table 3, and macros for the threshold sensitivity.
- `scripts/draw_ontology.py`: one subclass per line, larger fonts and tighter spacing, so Figures 1–2
  stay legible at page width.

### Language-model evaluation (added after the first v1.1.0 evaluation run)
- `evaluation/llm-evaluation/`: blinded evaluation by language-model agents. E1: independent test
  authoring (36 scenarios, 385 expected decisions, 24 competency questions). E2: hand application of
  the policy from documentation or from the model (8 runs). E3: independent recoding of the view
  selection (Cohen's kappa, threshold sensitivity). Specification packs, prompts, frozen outputs
  (SHA-256), tool-log audit, adjudications and scoring scripts; `scripts/run_all.py` re-scores them.
- `reo_checker.rederive`: identity-aware re-derivation entry point, which migrates references through
  `reo:supersededBy` before validation. Found by E1: the suite runner had validated without
  migration. Used by `scripts/run_external_suite.py` and the E1 runner.
- Specification: `refs(q)` is defined explicitly, and declared constraints, seed and context are not
  referenced elements. Found by E2 as an ambiguity. The implementation is unchanged.

### Ontology
- English-only annotations; ontology metadata (creators, MIT licence, version IRI 1.1.0, prior version).
- `owl:AllDisjointClasses` over the seven view classes and the three auxiliary classes (role separation).
- `reo:validatorKey` binds a constraint to a registered validator independently of its IRI.
- `reo:supersededBy` records identity migration (rename/split/merge).
- New module `reo-derivation.ttl`: `Requirement`, `DerivationRecord` (⊑ `prov:Entity`),
  `ValidationActivity` (⊑ `prov:Activity`), `DecisionState` (six individuals), requirement
  annotation properties, `reo:consulted` (⊑ `prov:used`).
- New shapes module `reo-derivation-shapes.ttl`.
- Definitions added for all terms reported by the pitfall scan (P08); explicit ranges (P11).

### Example
- `hospital.ttl`: English text; `validatorKey` and machine-interpretable formal expressions for C001/C002;
  unique-name assertion (`owl:AllDifferent`). Environment semantics unchanged for the 18 scenarios.
- New `hospital-extension.ttl` (outpatient context, soft quality rule, hard business rule without validator).
- New `hospital-requirements.ttl`: ten requirements with explicit RDF annotations.

### Checker (`reo_checker.py`, replaces the decision logic of `prototype.py` v1.0.0)
- Requirements are read from RDF; the trace is the read set (every consulted identifier).
- Applicability restricted to the requirement's own references (fixes over-inclusive applicability
  introduced by an intermediate patch); every element whose links determine applicability is traced.
- Uncertainty semantics: blocking through the seed lineage (ancestors), `affects` on consulted evidence,
  `rejected` status (refuted premise → rejected; invalidated evidence → review).
- Actor participation, interaction endpoint/direction/data checks, refinement-cycle guard.
- Conflicting values and multi-view typing on consulted elements route to review.
- Validators bound by `reo:validatorKey`; formal expressions of the two example rules are interpreted.
- Touched-identifier diff, direct and transitive re-evaluation, identity migration, PROV-O records.

### Evaluation
- 18 original scenarios now run end-to-end on RDF graph mutations (one scenario refined: wrong authority value).
- 20 targeted regressions; 34 competency questions (15 from v1.0.0 + 19 new) with vocabulary coverage.
- HermiT positive cases and 8 injected errors (compared with v1.0.0); pitfall scan before/after.
- Mutation corpus derived from the schema; independent SPARQL encoding of the contract (differential testing);
  SHACL-verdict and TF-IDF document baselines; impact and trace precision/recall; identity-migration cases.
- Prospective human-study and independent-evaluation kits (not executed).
