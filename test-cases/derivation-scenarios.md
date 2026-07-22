# Derivation-Contract Scenario Catalogue

These scenarios are exercised by `prototype.py`, the deterministic reference
checker for the environment-bounded derivation contract. Every scenario is a
controlled mutation of the released
`examples/medical-emergency/hospital.ttl` environment, evaluated against the
baseline candidate requirement:

> **R001** — "The Physician shall verify `Medication.contraindications` against
> `Patient.current_medications` before prescribing."
>
> Seed goal: **G002** (`Verify Drug Interactions`)  
> Active context: **X001_EmergencyDept**

The checker reads the same Turtle instance validated by SHACL, creates an
initial seed slice, completes it with candidate-specific validation evidence,
and applies this priority order:

```text
rejected
> pending_review
> conditional
> accepted_with_reservations
> accepted
```

`not_derived` is returned before candidate validation when no active anchoring
slice exists. An applicable hard constraint that is missing or has no
registered checker is never treated as satisfied; it produces
`pending_review`.

## Requirement-state scenarios (18)

| # | Scenario | Controlled mutation | Expected state |
|---:|---|---|---|
| 1 | `accepted_freshness_resolved` | U001 status becomes `validated` | **accepted** |
| 2 | `accepted_outpatient_consent_and_freshness` | Outpatient is declared a HIPAA exception and U001 is resolved | **accepted** |
| 3 | `accepted_with_reservations_soft_constraint` | C001 is changed to `soft`, its emergency exception is removed, and U001 is resolved | **accepted_with_reservations** |
| 4 | `conditional_baseline_unresolved_freshness` | No mutation; U001 remains unvalidated and blocks G002 | **conditional** |
| 5 | `conditional_outpatient_consent_unresolved_freshness` | Outpatient is a HIPAA exception, but U001 remains unvalidated | **conditional** |
| 6 | `pending_review_missing_hard_constraint` | C002 is removed while the candidate/context still require it | **pending_review** |
| 7 | `pending_review_no_induced_obligations` | A valid seed/context pair induces no validation obligation | **pending_review** |
| 8 | `pending_review_hard_constraint_without_checker` | A new applicable hard constraint is added without a registered checker | **pending_review** |
| 9 | `rejected_missing_actor` | Physician is removed | **rejected** |
| 10 | `rejected_missing_capability` | `Action_Prescribe` is removed from Physician | **rejected** |
| 11 | `rejected_missing_authority` | Physician authority is cleared | **rejected** |
| 12 | `rejected_missing_domain_concept` | `D001_Medication` is removed | **rejected** |
| 13 | `rejected_missing_domain_property` | `Patient.current_medications` is removed | **rejected** |
| 14 | `rejected_missing_interaction` | `I001_PhysicianToEHR` is removed | **rejected** |
| 15 | `rejected_missing_protocol` | The interaction protocol is cleared | **rejected** |
| 16 | `rejected_consent_without_exception` | The emergency exception is removed from C001 | **rejected** |
| 17 | `rejected_unlicensed_prescriber` | Physician authority becomes empty | **rejected** |
| 18 | `not_derived_inactive_seed_goal` | Seed goal G002 is removed | **not_derived** |

### Expected distribution

| State | Count |
|---|---:|
| `accepted` | 2 |
| `accepted_with_reservations` | 1 |
| `conditional` | 2 |
| `pending_review` | 3 |
| `rejected` | 9 |
| `not_derived` | 1 |
| **Total** | **18** |

## Explicit constraint checkers

The reference artifact registers the domain-specific rules used by the medical
example:

| Constraint | Registered deterministic check |
|---|---|
| `C001_HIPAA` | Consent is required unless the active context is an explicit exception |
| `C002_FDA` | The candidate's prescribing actor must have a non-empty authority level |

An applicable hard constraint not listed in the checker registry produces
`pending_review`. For soft constraints, a failed or unavailable check is kept
as a reservation and cannot produce `rejected` by itself.

## Direct change-impact queries (4)

The baseline conditional record `R001` has a nine-element trace spanning all
seven views: `Physician` (A), `G002` (G), `D001_Medication` and `D002_Patient`
(D), `C001_HIPAA` and `C002_FDA` (C), `X001_EmergencyDept` (X),
`U001_DrugDBFrequency` (U), and `I001_PhysicianToEHR` (I).

| Changed element | Expected result |
|---|---|
| `C002_FDA` | **hit** — returns R001 |
| `D001_Medication` | **hit** — returns R001 |
| `U001_DrugDBFrequency` | **hit** — returns R001 |
| `G005` | **miss** — does not return R001 |

## Reproduction

```bash
python prototype.py
python scripts/assert_derivation_results.py
```

Expected terminal output:

```text
Scenario checks: 18/18 passed
Impact queries : 4/4 passed
Baseline status: CONDITIONAL; trace size: 9
Results written: evaluation_results.csv
Scenario result assertion: 18/18 passed
Impact result assertion: 4/4 passed
```
