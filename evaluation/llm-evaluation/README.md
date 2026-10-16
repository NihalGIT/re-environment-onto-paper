# Blinded evaluation by language models (studies E1–E3)

No evaluator outside the author team was available for the v1.1.0 revision. The three tasks that need
independence from the developers were therefore delegated to language-model agents under the
protocol below. These results are a **proxy**: they are not a human study and do not measure analyst
effort (see paper, Sections VIII-E and XI). The human protocols remain in
`../independent-evaluation/` and `../human-study/`.

| Study | Question | Agents |
|---|---|---|
| E1 | Do test suites written by others, from the specification only, agree with the checker? | 3 authors (Opus, Sonnet, Haiku) |
| E2 | Can an analyst apply the policy by hand, from documentation (DOC) or from the REO model (MODEL)? | 2 models × 2 conditions × 2 runs |
| E3 | Does an independent coding of the 12 × 17 framework–concern matrix confirm the seven views? | 2 coders (Opus, Sonnet) |
| — | Classification of each disagreement | 2 adjudicators of a different model |

Models are recorded from the API responses in the agent transcripts: `claude-opus-5-5`,
`claude-sonnet-5-5`, `claude-haiku-5-5`.

## Protocol

1. **Specification pack** (`spec/`, built by `scripts/build_spec.py` from the paper's LaTeX before any
   agent ran): Section III without the view selection, Sections IV-B/C, V and VII, the two OWL
   modules and the example files. No code, test suite, result or view coding. E2 materials are in
   `e2/materials-DOC/` and `e2/materials-MODEL/` (`scripts/build_e2.py`; the DOC environment is
   verbalised mechanically from the Turtle, so both conditions hold the same information). E3 uses
   only the codebook `tasks/TASK_E3_coder.md`.
2. **Isolation.** Each agent ran in its own folder, with the prompt in `prompts.json` and the task in
   `tasks/`. It was told to read only inside its folder, write one file and run no code.
3. **Audit.** `scripts/audit_transcripts.py` extracts every tool call and the serving model from the
   runtime's transcripts. The extracted log is in `raw/audit.json`: 15 agents, 114 tool calls,
   0 violations.
4. **Freeze.** Every output was copied to `raw/` and hashed (`freeze_record.json`) before any
   execution. Outputs are never edited. Input files are hashed in `inputs_manifest.json`.
5. **Execution and scoring.** `scripts/rescore_all.py` (called by `scripts/run_all.py`) checks the
   hashes, re-executes the E1 suites (`run_llm_suite.py`) and re-scores E2 and E3 (`score_e2.py`,
   `score_e3.py`, `summarize.py`). Agents are not re-run, because their outputs vary between runs.
6. **Adjudication.** Each disagreement went to an agent of a different model, which chose one of:
   evaluator error, implementation deviation, specification ambiguity, or harness problem. Packets
   are in `adjudication/`, verdicts in `raw/ADJ_*`.

## Results (`results/llm_evaluation_summary.json`)

* **E1.** 36 scenarios, 25 new requirements, 385 expected decisions (112 non-trivial), 24 competency
  questions. The first execution met 384 of the 385 expectations. The one miss was a rename via
  `reo:supersededBy`, where the suite runner had not applied identity migration before
  re-derivation. The adjudicator classified it as an implementation deviation. The fix is
  `reo_checker.rederive`, now used by every runner. After the fix, all 385 expectations are met and
  24/24 competency questions return their frozen answers. `results/e1_run_initial_no_migration.json`
  keeps the first execution.
* **E2.** Eight runs of 20 sampled mutants (200 decisions each). Accuracy is 0.995–1.000 and recall
  of changed decisions is 1.00. Repeated runs give the same decision on 799 of 800 pairs. Every error
  is on a single item, a hard rule that applies to a constraint R001 declares: 7 of the 8 runs
  treated it as applicable. The adjudicator found the specification ambiguous, and the paper now
  defines refs(q) explicitly. Hand application took 0.54–0.95 s per decision; the checker takes
  0.45 ms.
* **E3.** Cohen's κ against the author coding is 0.46 (B1) and 0.53 (B2), and 0.72 between B1 and
  B2. Fleiss' κ over the three codings is 0.57. Under every coding the selection rule retains actor,
  goal, domain, constraint, context and interaction. B1 retains the same seven views as the author
  coding. B2 retains six, because uncertainty fails C1 there. Provenance passes C1 under B1 but fails C3
  in every coding, since it induces no obligation. The models coded from their knowledge of the
  frameworks, not from a new reading of the sources, so E3 is a sensitivity check.

## Running the protocol again (other models or human evaluators)

1. Rebuild the packs: `python scripts/build_spec.py ../../../paper/access.tex <dir>/spec`. A pack
   built from the revised paper includes the refs(q) clarification.
2. Give each evaluator a folder containing a pack and `tasks/TASK_*.md`. Collect `out/*.json`.
3. Freeze before running anything: `python scripts/freeze.py freeze_record.json raw/<file>.json`.
4. Execute: `python scripts/run_llm_suite.py results/<run>.json raw/<suite>.json` for E1, or score
   with `score_e2.py` / `score_e3.py`.

The frozen `spec/` folder is exactly what the agents saw (the pre-clarification wording). Do not
regenerate it in place.
