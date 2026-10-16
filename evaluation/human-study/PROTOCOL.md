# Comparative pilot protocol: document-based analysis vs. EC-RE (prospective)

Status: **prospective protocol — not yet executed.** No participant data exist in this
repository. Results must not be reported until the study has been run as specified.

## 1. Question
Within controlled scenarios, does assessing candidate requirements against an explicit
REO environment model (EC-RE) change decision errors, trace and impact accuracy, and
analyst effort compared with conventional document-based analysis of the same facts?

## 2. Design
* Within-subjects, two conditions: **DOC** (facts given as prose documents) and **ECRE**
  (same facts as a REO model, the requirement annotations and checker reports).
* Two matched scenarios (S1, S2), each with 10 candidate requirements and 5 change requests.
  Both scenarios are built from the same underlying fact base structure; S1 and S2 differ in
  domain content so that answers cannot be carried over.
* Counterbalancing: 4 sequences (DOC-S1/ECRE-S2, DOC-S2/ECRE-S1, ECRE-S1/DOC-S2, ECRE-S2/DOC-S1),
  assigned in rotation.
* Participants: 6-8 analysts with RE training (e.g., doctoral students, practitioners) who did
  not build REO or the checker. A pilot of this size characterises effects; it is not powered
  for hypothesis tests.

## 3. Reference answers (oracle) — prepared before any session
Two adjudicators who did not build the artefact independently produce, per scenario:
the decision state of each requirement, its supporting evidence links (at concept level), and
the set of requirements affected by each change request. Disagreements are resolved in an
adjudication meeting and logged (`templates/adjudication_log.csv`). Agreement before
adjudication (Cohen's kappa for decisions; Jaccard for link sets) is reported.

## 4. Tasks (per condition)
1. Decide the state of each candidate (accepted / accepted with reservations / conditional /
   pending review / rejected) and justify it.
2. Record the evidence links consulted for each decision.
3. For each change request, list the affected requirements and re-decide them.
4. ECRE condition only, separate timed task: encode one additional requirement annotation and
   one environment change in REO (modelling overhead).

## 5. Measures (Table 12 of the paper)
| Measure | Definition |
|---|---|
| Decision errors | Full confusion matrix vs. oracle; false acceptance = unconditional acceptance of a case the oracle rejects, sends to review or makes conditional; false rejection = rejection of an oracle-acceptable case |
| Trace precision/recall | Proposed links vs. oracle links at concept granularity |
| Impact precision/recall | Selected vs. oracle-affected requirements, per change request |
| Analyst effort | Task time from start/stop logs, per task |
| Modelling overhead | Time and number of corrections for the encoding task |
| Total cost | Upfront modelling plus recurring task time, reported separately |

## 6. Analysis
`analyze_pilot.py` computes all measures from the filled templates. Report per participant and
aggregated (median, IQR), paired differences ECRE-DOC with 95% bootstrap intervals
(10,000 resamples). Zero-denominator cases are reported as undefined. Conditional outcomes are
never counted as acceptances. Any inferential test must be pre-registered before data collection.

## 7. Ethics and data
Informed consent (`templates/consent_form.md`); anonymised participant codes; no personal data
in the repository; raw time logs and answers published where consent permits.
