# Derivation-Contract Scenario Catalogue

These are the scenarios exercised by `prototype.py` (the reference derivation
checker). Each scenario is a controlled mutation of the released
`examples/medical-emergency/hospital.ttl` environment, evaluated against the
baseline candidate requirement:

> **R001** — "The Physician shall verify `Medication.contraindications` against
> `Patient.current_medications` before prescribing."
> Seed goal: **G002** (Verify Drug Interactions); active context:
> **X001_EmergencyDept**.

The checker is deterministic; every run reproduces the outcomes below and writes
`evaluation_results.csv`.

## Requirement-state scenarios (15)

| # | Scenario | Mutation | Expected |
|---|----------|----------|----------|
| 1 | `accepted_freshness_resolved` | U001 status → `validated` | **accepted** |
| 2 | `accepted_outpatient_consent_and_freshness` | outpatient context declared a HIPAA exception + U001 resolved | **accepted** |
| 3 | `conditional_baseline_unresolved_freshness` | none (baseline: U001 unvalidated, blocks G002) | **conditional** |
| 4 | `conditional_outpatient_consent_unresolved_freshness` | outpatient exception but U001 still unvalidated | **conditional** |
| 5 | `rejected_missing_actor` | delete Physician | **rejected** |
| 6 | `rejected_missing_capability` | remove Physician's `Action_Prescribe` | **rejected** |
| 7 | `rejected_missing_authority` | clear Physician `authorityLevel` | **rejected** |
| 8 | `rejected_missing_domain_concept` | delete `D001_Medication` | **rejected** |
| 9 | `rejected_missing_domain_property` | remove `Patient.current_medications` | **rejected** |
| 10 | `rejected_missing_interaction` | delete `I001_PhysicianToEHR` | **rejected** |
| 11 | `rejected_missing_protocol` | clear the interaction protocol | **rejected** |
| 12 | `rejected_missing_hard_constraint` | delete `C002_FDA` | **rejected** |
| 13 | `rejected_consent_without_exception` | remove emergency exception from HIPAA | **rejected** |
| 14 | `rejected_unlicensed_prescriber` | empty Physician `authorityLevel` | **rejected** |
| 15 | `not_derived_inactive_seed_goal` | delete seed goal G002 | **not_derived** |

Summary: 2 accepted, 2 conditional, 10 rejected, 1 not-derived.

## Direct change-impact queries (4)

The baseline (conditional) record `R001` has a nine-element trace spanning all
seven views: `Physician` (A), `G002` (G), `D001_Medication` and `D002_Patient`
(D), `C001_HIPAA` and `C002_FDA` (C), `X001_EmergencyDept` (X),
`U001_DrugDBFrequency` (U), `I001_PhysicianToEHR` (I).

| Changed element | In trace? | `requirements(e)` returns R001? |
|-----------------|-----------|---------------------------------|
| `C002_FDA` (licensing constraint) | yes | **hit** |
| `D001_Medication` (concept) | yes | **hit** |
| `U001_DrugDBFrequency` (uncertainty) | yes | **hit** |
| `G005` (unrelated goal) | no | **miss** |

Summary: 3 hits, 1 miss — trace-relative recall as specified.
