# Emergency-prescription environment (documentation)

Each paragraph documents one element of the environment and its attributes and relations.

**Action_AccessRecords** — kind: Action.
  - label: "access_records"

**Action_Diagnose** — kind: Action.
  - label: "diagnose"

**Action_Dispense** — kind: Action.
  - label: "dispense"

**Action_ForwardPrescription** — kind: Action.
  - label: "forward_prescription"

**Action_Prescribe** — kind: Action.
  - label: "prescribe"

**Action_QueryDatabase** — kind: Action.
  - label: "query_database"

**Action_StoreRecords** — kind: Action.
  - label: "store_records"

**Action_VerifyPrescription** — kind: Action.
  - label: "verify_prescription"

**C001_HIPAA** — kind: RegulatoryConstraint.
  - applies to: EHR_System; Physician
  - constraint id: "C-001"
  - constraint name: "HIPAA Privacy Rule"
  - enforcement level: "hard"
  - formal expression: "access_records → has_consent(context) ∨ exception(context)"
  - has authoritative text: "45 CFR Parts 160 and 164 (HIPAA Privacy Rule, HHS 2013)"
  - has exception: X001_EmergencyDept
  - natural language: "Patient consent required before accessing medical records, unless emergency override applies."
  - validator key: "consent-or-exception"

**C002_FDA** — kind: RegulatoryConstraint.
  - applies to: Pharmacist; Physician
  - constraint id: "C-002"
  - constraint name: "FDA Prescription Rules"
  - enforcement level: "hard"
  - formal expression: "prescribe → actor.authority = licensed_medical_professional"
  - has authoritative text: "21 CFR Part 1306 (DEA Prescription Requirements)"
  - natural language: "Only licensed medical professionals may prescribe controlled medications."
  - validator key: "authority-equals"

**C003_ResponseTime** — kind: QualityConstraint.
  - constraint id: "C-003"
  - constraint name: "EHR response time"
  - enforcement level: "soft"
  - formal expression: "response_time(I001) <= 2s"
  - natural language: "Patient data should be returned to the physician within two seconds."

**C004_DispensingLog** — kind: BusinessConstraint.
  - applies to: Pharmacist
  - constraint id: "C-004"
  - constraint name: "Dispensing log"
  - enforcement level: "hard"
  - formal expression: "dispense → logged(dispensing_event)"
  - natural language: "Every dispensing event must be recorded in the pharmacy log."

**D001_Medication** — kind: DomainConcept.
  - concept id: "D-001"
  - concept name: "Medication"
  - has invariant: Inv_ContraindicationsKnown; Inv_DosagePositive
  - has property: Prop_Contraindications; Prop_Dosage; Prop_MedName; Prop_Route
  - related to: D002_Patient

**D002_Patient** — kind: DomainConcept.
  - concept id: "D-002"
  - concept name: "Patient"
  - has invariant: Inv_PatientIdUnique
  - has property: Prop_Allergies; Prop_CurrentMedications; Prop_MedicalHistory; Prop_PatientId
  - related to: D001_Medication

**EHR_System** — kind: SystemActor.
  - actor id: "SYS001"
  - actor name: "EHR_System"
  - authority level: "system_level"
  - has capability: Action_ForwardPrescription; Action_QueryDatabase; Action_StoreRecords
  - is responsible for: G005
  - is subject to: C001_HIPAA; C002_FDA
  - organizational unit: "IT_Department"

**G001** — kind: StrategicGoal.
  - goal id: "G-001"
  - goal name: "Ensure Safe Medication Prescribing"
  - has stakeholder: Physician
  - priority: "1"
  - refinement type: "AND"

**G002** — kind: OperationalGoal.
  - goal id: "G-002"
  - goal name: "Verify Drug Interactions"
  - has stakeholder: Physician
  - priority: "1"
  - refinement type: "leaf"
  - refines: G001

**G003** — kind: OperationalGoal.
  - goal id: "G-003"
  - goal name: "Check Patient Allergies"
  - has stakeholder: Physician
  - priority: "1"
  - refinement type: "leaf"
  - refines: G001

**G004** — kind: OperationalGoal.
  - goal id: "G-004"
  - goal name: "Validate Dosage"
  - has stakeholder: Physician
  - priority: "2"
  - refinement type: "leaf"
  - refines: G001

**G005** — kind: OperationalGoal.
  - goal id: "G-005"
  - goal name: "Notify Pharmacist"
  - has stakeholder: EHR_System; Pharmacist
  - priority: "2"
  - refinement type: "leaf"
  - refines: G001

**I001_PhysicianToEHR** — kind: DataFlowInteraction.
  - exchanges data: D002_Patient
  - governed by: C001_HIPAA; C003_ResponseTime
  - has source: Physician
  - has target: EHR_System
  - interaction id: "I-001"
  - interaction name: "Physician reads Patient data from EHR"
  - protocol: "HL7-FHIR"
  - triggering event: "physician_initiates_prescription"

**I002_EHRToPharmacy** — kind: DataFlowInteraction.
  - exchanges data: D001_Medication
  - governed by: C002_FDA
  - has source: EHR_System
  - has target: Pharmacist
  - interaction id: "I-002"
  - interaction name: "EHR forwards confirmed prescription to Pharmacy"
  - protocol: "HL7-FHIR"
  - triggering event: "physician_confirms_prescription"

**Inv_ContraindicationsKnown** — kind: DomainInvariant.
  - formal logic: "contraindications ⊆ KnownSubstances"
  - invariant expression: "contraindications ⊆ known_substances"
  - severity: "error"

**Inv_DosagePositive** — kind: DomainInvariant.
  - formal logic: "dosage > 0"
  - invariant expression: "dosage > 0"
  - severity: "error"

**Inv_PatientIdUnique** — kind: DomainInvariant.
  - formal logic: "∀p1,p2 ∈ Patient : p1.id = p2.id → p1 = p2"
  - invariant expression: "id is unique across all patients"
  - severity: "error"

**Pharmacist** — kind: HumanActor.
  - actor id: "PHA001"
  - actor name: "Pharmacist"
  - authority level: "licensed_pharmacist"
  - has capability: Action_Dispense; Action_VerifyPrescription
  - is responsible for: G005
  - is subject to: C002_FDA; C004_DispensingLog
  - organizational unit: "Pharmacy"

**Physician** — kind: HumanActor.
  - actor id: "PHY001"
  - actor name: "Physician"
  - authority level: "licensed_medical_professional"
  - has capability: Action_AccessRecords; Action_Diagnose; Action_Prescribe
  - is responsible for: G001; G002; G003; G004
  - is subject to: C001_HIPAA; C002_FDA
  - organizational unit: "EmergencyDept"

**Prop_Allergies** — kind: DomainProperty.
  - is mandatory: "false"
  - property name: "allergies"
  - property type: "reference"
  - reference target: "KnownSubstances"

**Prop_Contraindications** — kind: DomainProperty.
  - is mandatory: "false"
  - property name: "contraindications"
  - property type: "reference"
  - reference target: "KnownSubstances"

**Prop_CurrentMedications** — kind: DomainProperty.
  - is mandatory: "false"
  - property name: "current_medications"
  - property type: "reference"
  - reference target: "D001_Medication"

**Prop_Dosage** — kind: DomainProperty.
  - is mandatory: "true"
  - property name: "dosage"
  - property type: "decimal"

**Prop_MedName** — kind: DomainProperty.
  - is mandatory: "true"
  - property name: "name"
  - property type: "string"

**Prop_MedicalHistory** — kind: DomainProperty.
  - is mandatory: "false"
  - property name: "medical_history"
  - property type: "string"

**Prop_PatientId** — kind: DomainProperty.
  - is mandatory: "true"
  - property name: "id"
  - property type: "string"

**Prop_Route** — kind: DomainProperty.
  - is mandatory: "true"
  - property name: "route"
  - property type: "enum"

**U001_DrugDBFrequency** — kind: UnknownUncertainty.
  - affects: G002
  - blocks: G002
  - impact level: "high"
  - status: "unvalidated"
  - subject: "Update frequency of the drug-interaction database (not yet determined)."
  - uncertainty id: "U-001"
  - uncertainty name: "Drug DB Update Frequency"
  - validation plan: "Infrastructure analysis scheduled Week 12."

**X001_EmergencyDept** — kind: Context.
  - context id: "X-001"
  - context name: "Emergency Department"
  - context property: "resource_constrained=high"; "time_critical=true"
  - has active actor: EHR_System; Pharmacist; Physician
  - has active constraint: C002_FDA
  - spatial scope: "Emergency_Wing_Hospital"

**X002_Outpatient** — kind: Context.
  - context id: "X-002"
  - context name: "Outpatient Clinic"
  - context property: "consent_obtained=false"; "time_critical=false"
  - has active actor: Pharmacist; Physician
  - has active constraint: C002_FDA
  - spatial scope: "Outpatient_Wing_Hospital"
