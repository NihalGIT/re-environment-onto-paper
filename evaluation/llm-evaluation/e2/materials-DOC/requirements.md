# Requirements

Each requirement is assessed for the stated goal and context.

* **R001** (goal G002, context X001_EmergencyDept): The Physician shall verify Medication.contraindications against Patient.current_medications before prescribing.
* **R002** (goal G003, context X001_EmergencyDept): The Physician shall check Patient.allergies before prescribing.
* **R003** (goal G004, context X001_EmergencyDept): The Physician shall validate that Medication.dosage is positive before prescribing.
* **R004** (goal G005, context X001_EmergencyDept): The EHR_System shall forward each confirmed prescription to the Pharmacist using HL7-FHIR.
* **R005** (goal G005, context X001_EmergencyDept): The Pharmacist shall verify each received prescription before dispensing the Medication.
* **R006** (goal G004, context X001_EmergencyDept): The Pharmacist shall prescribe the Medication dosage.
* **R007** (goal G002, context X001_EmergencyDept): The EHR_System shall query the drug database to refresh Medication.contraindications.
* **R008** (goal G003, context X002_Outpatient): In the outpatient clinic, the Physician shall review Patient.medical_history before prescribing.
* **R009** (goal G004, context X002_Outpatient): In the outpatient clinic, the Physician shall validate Medication.route before prescribing.
* **R010** (goal G005, context X001_EmergencyDept): The EHR_System shall send Patient.medical_history to the Pharmacist.
