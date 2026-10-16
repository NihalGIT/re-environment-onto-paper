# Independent authoring and freezing of competency questions and mutations

Status: **prospective for human evaluators.** It was executed once with language-model agents in
place of people (`../llm-evaluation/`, paper Section VIII-E). That run is a proxy and does not
replace this protocol. The other suites shipped with REO v1.1.0 were written by the artefact authors. This kit lets evaluators who did not build REO or the checker author new
suites whose expectations are fixed before any execution.

## Roles
* **Evaluators** (at least two, not co-authors of the artefact): author questions, mutations and
  expected outcomes from the specification only (paper Sections III-V, `hospital.ttl`,
  `hospital-extension.ttl`, the requirement texts and annotations). They do not read
  `reo_checker.py` or `scripts/sparql_oracle.py`.
* **Encoders** (may be developers): translate questions to SPARQL and mutations to triple
  additions/removals. They may not change an expected outcome; translation questions go back
  to the evaluators in writing.

## Procedure
1. Evaluators fill `templates/cq_template.csv` (question, expected answer in domain terms) and
   `templates/mutations_template.json` (natural-language change, expected decision per
   requirement, rationale) independently, then reconcile disagreements in
   `templates/adjudication_log.csv` (keep both original answers).
2. **Freeze**: commit the filled templates; record the commit hash, date and evaluator codes in
   `templates/freeze_record.md`. From this point expected values are immutable.
3. Encoders add the SPARQL/triple encodings in a separate commit; evaluators approve that each
   encoding matches the natural-language item (not the expected result).
4. Run `python scripts/run_external_suite.py evaluation/independent-evaluation/<file>.json`.
   Store the output unchanged.
5. Report every disagreement. A disagreement is resolved only by (a) fixing an encoding error
   confirmed by the evaluators, or (b) recording a specification ambiguity or an implementation
   defect. Expected outcomes are never edited to match observed outputs. Unsupported items stay
   in the denominator.
6. Keep a held-out half of the mutations unseen by the developers until the final run.
