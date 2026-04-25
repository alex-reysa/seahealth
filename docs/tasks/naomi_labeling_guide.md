# Naomi Labeling Guide — Facility Claim Verification

This guide explains exactly how to label facility records for the healthcare capacity audit system. No prior data-labeling experience is assumed.

## Goal

We need 30-50 expert-reviewed examples that tell us whether facility capability claims are supported, contradicted, or uncertain.

The product will use these labels to test whether the AI can correctly verify claims such as:

- "This facility can perform surgery."
- "This facility has ICU capability."
- "This facility provides dialysis."
- "This facility offers emergency/trauma care."

Your job is not to prove the full truth about each facility. Your job is to judge whether the available evidence in the dataset supports the claim well enough for an NGO planner to trust it.

## Recommended Tool

Use **Google Sheets**.

Why:

- easiest for collaboration
- supports filters and dropdowns
- easy to export as CSV
- no engineering setup needed

Excel also works if Google Sheets is inconvenient.

## Files To Use

You should receive:

- the full source CSV: `VF_Hackathon_Dataset_India_Large...csv`
- the starter source sample: `naomi_source_sample_50.csv`
- the labels template: `naomi_labeling_template.csv`
- this guide

Create one Google Sheet with two tabs:

- `source_data`: import `naomi_source_sample_50.csv` first; use the full source CSV later if more rows are needed
- `labels`: import/copy the labels template

Freeze the first row in both tabs and turn on filters.

In the `labels` tab, use Google Sheets dropdowns if you have time:

- `claimed_capability`: `surgery`, `icu`, `dialysis`, `emergency_trauma`, `neonatal`, `oncology`, `cardiology`, `obstetrics`, `dental`, `diagnostics`, `other`
- `evidence_status`: `supports`, `contradicts`, `silent`, `unclear`
- `contradiction_type`: `capability_equipment_mismatch`, `capability_staff_mismatch`, `capability_capacity_mismatch`, `temporal_coverage_mismatch`, `vague_claim`, `stale_or_weak_source`, `facility_type_mismatch`, `none`, `other`
- `clinical_plausibility`: `1`, `2`, `3`, `4`, `5`
- `confidence`: `1`, `2`, `3`, `4`, `5`
- `source_checked`: `yes`, `no`
- `source_type`: `official_site`, `directory`, `social`, `other`, `not_checked`
- `demo_candidate`: `yes`, `no`

## What Counts As One Label?

One label is one **facility + one claimed capability**.

Example:

If a facility claims both `surgery` and `ICU`, create two label rows:

- one row for the surgery claim
- one row for the ICU claim

Do not put multiple major claims into one label row. This makes the evaluation cleaner.

## Target Output

Label **30-50 facility-capability claims**.

Suggested mix:

- 10 surgery claims
- 8 ICU or critical care claims
- 6 emergency or trauma claims
- 5 dialysis, oncology, cardiology, or neonatal claims
- 5 ordinary clinic/dental claims as negative controls
- 5 strange or suspicious records where something feels inconsistent

If time is short, label 20 claims well rather than 50 claims quickly.

## Source Fields To Read

For each facility, read these columns first:

- `source_row_number`
- `name`
- `facilityTypeId`
- `description`
- `specialties`
- `procedure`
- `equipment`
- `capability`
- `numberDoctors`
- `capacity`
- `officialWebsite`
- `websites`
- `recency_of_page_update`
- `address_city`
- `address_stateOrRegion`

You do not need to inspect every column.

Use `source_row_number` to trace your label back to the original CSV row. Use `label_id` as a simple counter: `1`, `2`, `3`, and so on.

## Step-By-Step Workflow

### Step 1: Pick A Facility

In `source_data`, filter for useful records.

Good filters/search terms:

- `facilityTypeId = hospital`
- `capability` contains `ICU`, `critical care`, `surgery`, `emergency`, `trauma`, `dialysis`, `oncology`, `neonatal`
- `specialties` contains `generalSurgery`, `criticalCareMedicine`, `emergencyMedicine`, `cardiology`, `oncology`, `neonatology`

Avoid spending too much time on dental clinics unless you are using them as negative controls.

### Step 2: Identify The Claim

Ask: what capability is this facility claiming?

Use one of these normalized capability names:

- `surgery`
- `icu`
- `dialysis`
- `emergency_trauma`
- `neonatal`
- `oncology`
- `cardiology`
- `obstetrics`
- `dental`
- `diagnostics`
- `other`

Write the normalized name in `claimed_capability`.

### Step 3: Copy The Best Evidence Quote

Find the strongest sentence or phrase in the CSV that supports or describes the claim.

Good evidence examples:

- `"24/7 emergency surgical services"`
- `"Hospital with critical care services"`
- `"CT scanner"`
- `"Has 1 ophthalmologist/eye surgeon on staff"`
- `"Performs cataract surgery"`

Copy the exact phrase into `evidence_quote`.

If there is no clear supporting phrase, write `no explicit evidence found`.

### Step 4: Decide Evidence Status

Choose exactly one value:

- `supports`
- `contradicts`
- `silent`
- `unclear`

Definitions:

| Status | Meaning | Example |
| --- | --- | --- |
| `supports` | The data gives specific evidence for the claim. | Surgery claim plus procedure list and operating/theater/anesthesia evidence. |
| `contradicts` | The data makes the claim clinically doubtful. | ICU claimed, but only outpatient clinic evidence and no staff/equipment. |
| `silent` | The claim exists, but the dataset gives no useful evidence either way. | "Hospital" listed but no procedures, equipment, staff, or capability details. |
| `unclear` | Evidence is mixed, vague, or hard to interpret. | "Advanced care" and "many specialties" but no concrete prerequisites. |

Use `silent` when evidence is simply missing.
Use `unclear` when evidence exists but is ambiguous.

### Step 5: Mark Missing Prerequisites

Use one or more of these values, separated by semicolons:

- `staff`
- `equipment`
- `capacity`
- `service_availability`
- `source_recency`
- `specificity`
- `none_obvious`

Examples:

- Surgery claimed but no anesthetist or operating theater: `staff; equipment`
- 24/7 emergency claimed but only one doctor listed: `staff; service_availability`
- Oncology claimed but source is vague and old: `specificity; source_recency`

### Step 6: Choose Contradiction Type

Use one of these values:

- `capability_equipment_mismatch`
- `capability_staff_mismatch`
- `capability_capacity_mismatch`
- `temporal_coverage_mismatch`
- `vague_claim`
- `stale_or_weak_source`
- `facility_type_mismatch`
- `none`
- `other`

Definitions:

| Type | Meaning |
| --- | --- |
| `capability_equipment_mismatch` | Claim needs equipment that is missing from the record. |
| `capability_staff_mismatch` | Claim needs staff that is missing from the record. |
| `capability_capacity_mismatch` | Claimed service seems too high-acuity for the listed beds/scale. |
| `temporal_coverage_mismatch` | 24/7 or emergency claim is not supported by staffing/operations evidence. |
| `vague_claim` | Claim is broad but not operationally specific. |
| `stale_or_weak_source` | Source looks old, copied, directory-only, or non-specific. |
| `facility_type_mismatch` | Facility type conflicts with claimed capability, such as a clinic claiming ICU-like services. |
| `none` | No contradiction spotted. |
| `other` | Something else; explain in `review_notes`. |

### Step 7: Score Clinical Plausibility

Use a 1-5 score:

| Score | Meaning |
| --- | --- |
| `1` | Very implausible based on available data. |
| `2` | Doubtful; important prerequisites missing. |
| `3` | Possible but not well proven. |
| `4` | Plausible; most required evidence is present. |
| `5` | Strongly plausible; claim is specific and well supported. |

This is a clinical judgment, not a mathematical score.

### Step 8: Score Your Confidence

Use a 1-5 score:

| Score | Meaning |
| --- | --- |
| `1` | I am guessing. |
| `2` | Low confidence; record is very incomplete. |
| `3` | Moderate confidence; enough evidence to make a tentative call. |
| `4` | High confidence; evidence is reasonably clear. |
| `5` | Very high confidence; evidence is explicit and specific. |

Important: plausibility and confidence are different.

Example:

- A claim can be plausible but low-confidence if the evidence is thin.
- A claim can be implausible but high-confidence if the contradiction is obvious.

### Step 9: Add A Short Review Note

Write one sentence explaining your reasoning.

Good examples:

- `Surgery is claimed, but no anesthetist, operating theater, sterilization, or oxygen evidence appears in the row.`
- `ICU claim is plausible because critical care specialty, ventilator-related equipment, and emergency availability are all present.`
- `Emergency care is claimed, but 24/7 staffing is not supported.`

Avoid long paragraphs.

## When To Use Web Enrichment

Start with **CSV-only labeling**.

Use web enrichment only for:

- the best demo examples
- confusing high-impact records
- rows where the CSV has an official website and the claim is important

Time box web checking to **3 minutes per facility**.

If you check a website, add:

- `source_checked = yes`
- `source_url = exact URL`
- `source_type = official_site`, `directory`, `social`, or `other`
- `accessed_date = today's date`

Do not get stuck researching one facility.

## Rules To Keep Labels Consistent

- Do not infer too much from a generic specialty.
  - `generalSurgery` is evidence of surgical relevance, but not enough by itself to verify surgical capacity.
- Do not treat "hospital" as proof of ICU, emergency, or surgery.
- Do not treat "24/7 open" as proof of 24/7 clinical capability.
- Do not treat social media presence as clinical evidence.
- Do not mark missing data as a contradiction unless the missing prerequisite is clinically important for the claim.
- Copy exact evidence phrases when possible.
- When unsure, use `unclear` and explain why.

## Examples

### Example 1: Weak Surgery Claim

Facility row says:

- `facilityTypeId = clinic`
- `procedure = ["minor surgery"]`
- `equipment = []`
- `numberDoctors = blank`

Label:

- `claimed_capability = surgery`
- `evidence_status = unclear`
- `missing_prerequisite = staff; equipment`
- `contradiction_type = vague_claim`
- `clinical_plausibility = 2`
- `confidence = 3`
- `review_notes = Surgery is mentioned, but the row lacks evidence for anesthesia, operating theater, or surgical staffing.`

### Example 2: Stronger ICU Claim

Facility row says:

- `facilityTypeId = hospital`
- `specialties = criticalCareMedicine`
- `equipment = ventilator, oxygen support, monitoring equipment`
- `capability = 24/7 emergency and ICU care`

Label:

- `claimed_capability = icu`
- `evidence_status = supports`
- `missing_prerequisite = none_obvious`
- `contradiction_type = none`
- `clinical_plausibility = 4`
- `confidence = 4`
- `review_notes = ICU claim is supported by critical care specialty plus relevant equipment and emergency availability.`

### Example 3: 24/7 Emergency Claim With Weak Staffing

Facility row says:

- `capability = ["Open 24/7", "Provides emergency care"]`
- `numberDoctors = 1`
- no emergency department, duty roster, or trauma equipment listed

Label:

- `claimed_capability = emergency_trauma`
- `evidence_status = contradicts`
- `missing_prerequisite = staff; equipment; service_availability`
- `contradiction_type = temporal_coverage_mismatch`
- `clinical_plausibility = 2`
- `confidence = 4`
- `review_notes = 24/7 emergency care is claimed, but one listed doctor and no emergency infrastructure make the claim doubtful.`

## First 45 Minutes

Do this first:

1. Label 10 claims only.
2. Include at least one surgery, one ICU/critical care, one emergency/trauma, one dialysis/oncology/neonatal/cardiology, and one ordinary clinic/dental example.
3. Send the first 10 labels back to the team for calibration.
4. After calibration, continue to 30-50 labels.

This prevents inconsistent labels early.

## Final Deliverables

Send back:

- the completed `labels` sheet as CSV
- 3-5 examples you think are best for the live demo
- 3 contradiction patterns you saw repeatedly
- any clinical prerequisite rules that should be added to the validator

The most valuable output is not the number of labels. It is the reasoning behind the labels.
