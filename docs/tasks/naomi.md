# Naomi Workstream — Clinical Credibility + Planner Narrative

Naomi owns the parts of the project that make the system defensible: clinical plausibility, verification logic, user narrative, and judge-facing evidence. The core product is not "search over hospitals"; it is an audit layer that tells NGO planners which facility capability claims are supported, contradicted, or uncertain.

For the concrete labeling workflow, use:

- `docs/tasks/naomi_labeling_guide.md`
- `docs/tasks/naomi_labeling_template.csv`
- `docs/tasks/naomi_source_sample_50.csv`

## Track 1 — Hand-Labeled Evaluation Set

**Deadline:** first 6-8 hours.

**Deliverable:** a spreadsheet of 30-50 manually reviewed facility records.

This is the highest-leverage task. The brief emphasizes that there is no answer key, so we need a small expert-labeled set to evaluate whether the extraction and verification agents are actually right.

Spreadsheet columns:

- `facility_id`
- `facility_name`
- `raw_text_excerpt`
- `claimed_capability` such as ICU, surgery, dialysis, oncology, neonatal, trauma
- `evidence_quote`
- `evidence_status` with one of: `supports`, `contradicts`, `silent`, `unclear`
- `missing_prerequisite` such as staff, equipment, beds, oxygen, blood access, 24/7 coverage
- `contradiction_type`
- `clinical_plausibility` from 1-5
- `confidence` from 1-5
- `review_notes`

What we will use this for:

- extraction precision and recall on claimed capabilities
- contradiction-detection accuracy
- examples for the demo and pitch
- calibration of the Trust Score

Important: this is a hand-labeled eval set, not perfect ground truth. That is fine. The point is to have an expert-reviewed benchmark instead of only eyeballing model outputs.

## Track 2 — Contradiction Taxonomy

**Deadline:** hour 10-12.

**Deliverable:** a short taxonomy that engineering can implement directly.

For each contradiction type, define:

- `name`
- `definition`
- `example`
- `detection_rule`
- `severity` from low, medium, high

Initial taxonomy:

- **Capability/equipment mismatch:** facility claims a capability but lacks the equipment normally required.
  - Example: surgery claimed, but no operating theater or anesthesia machine mentioned.
- **Capability/staff mismatch:** facility claims a capability but lacks required clinical staff.
  - Example: ICU claimed, but no critical care nurse, anesthetist, or physician coverage listed.
- **Capability/volume mismatch:** facility claims high-acuity service but listed capacity is implausibly small.
  - Example: trauma center claimed, but only two beds listed.
- **Temporal coverage mismatch:** facility claims 24/7 service but staffing pattern does not support it.
  - Example: emergency care claimed, but only one named physician is listed.
- **Vague capability claim:** facility uses broad terms without enough operational evidence.
  - Example: "advanced surgery available" with no staff, equipment, or procedure evidence.
- **Stale or weak source:** claim is based on an old, low-specificity, or copied source.
  - Example: a 2021 directory listing with no recent corroboration.

This taxonomy becomes the Trust Scorer logic. Naomi is not just generating ideas; she is defining the rules the product applies at scale.

## Track 3 — Clinical Verification Rubric

**Deadline:** hour 12-16.

**Deliverable:** one-page rubric for major capabilities.

For each capability, define:

- `minimum_staff`
- `minimum_equipment`
- `minimum_service_availability`
- `strong_evidence`
- `weak_evidence`
- `disqualifying_or_high-risk_contradiction`

Capabilities to cover first:

- ICU
- surgery
- dialysis
- neonatal care
- trauma/emergency care
- oncology

Example format:

| Capability | Minimum staff | Minimum equipment | Strong evidence | High-risk contradiction |
| --- | --- | --- | --- | --- |
| Surgery | surgeon, anesthetist, nursing support | operating theater, anesthesia machine, sterilization, oxygen | specific procedure list, OT count, staff roster | surgery claimed but no anesthesia/OT evidence |

This rubric becomes the Validator Agent prompt and the explanation layer shown in the Facility Audit View.

## Track 4 — NGO Planner Persona + Decision Story

**Deadline:** hour 18-24.

**Deliverable:** one sharp planner persona tied to a concrete decision.

Do not write a generic UX persona. Write a decision scenario:

> Sarah works at an NGO allocating $2M for rural healthcare equipment in Bihar. She has three weeks to recommend five facilities to fund. Today she triangulates facility claims through calls, spreadsheets, old registries, and local partner notes. Her problem is not finding hospitals; it is deciding which claims are trustworthy enough to fund.

Include:

- decision she must make
- budget or constraint
- geography
- clinical capability of interest
- current workflow
- what evidence would make her trust a recommendation

This persona keeps the UI focused on planner-grade decisions: verified gaps, uncertainty, contradictions, and exportable evidence.

## Track 5 — Lightweight Stakeholder Validation

**Deadline:** send by hour 18; collect responses by hour 30 if possible.

**Deliverable:** 1-2 quotes or summarized reactions from clinical/healthcare contacts.

Send a short message to 2-3 relevant contacts from Hirslanden, ETH, MedTech, or clinical operations.

Suggested questions:

1. If a tool flagged hospitals whose claimed capabilities were not supported by listed staff/equipment, would that be useful for planning or due diligence?
2. What evidence would make you trust or distrust such a flag?
3. Which contradiction would worry you most: missing staff, missing equipment, stale source, or inconsistent service volume?

Even one credible quote can strengthen the pitch more than broad unsupported claims.

## Track 6 — Demo Narrative + Pitch Artifacts

**Deadline:** hours 24-36.

**Deliverables:**

- 4-minute demo script
- slide narrative
- impact page with credible numbers
- one-page judge handout

Demo script structure:

1. Hook: "Healthcare facility data often claims more than it can prove."
2. Planner problem: NGO must allocate funding under uncertainty.
3. Live query: use the appendectomy/surgery example from the brief.
4. Facility audit: show claim, evidence quote, missing prerequisite, contradiction.
5. Map: show underserved region and verified capability gap.
6. Recommendation: show why one facility should be funded, inspected, or excluded.
7. Close: "We built the verification layer NGOs need before allocating money."

Naomi should drive the story and deck structure while engineering feeds screenshots, metrics, and product outputs.

## Why Not Use Synthetic Data As The Core Verification Layer?

Synthetic data and LLM-supervised labels are useful for bootstrapping, but they cannot replace Naomi's expert-reviewed eval set.

Reasons:

- **Circular evaluation risk:** if an LLM generates the labels and another LLM is evaluated against them, we may only prove that models agree with each other, not that they are clinically right.
- **False confidence:** synthetic examples are usually cleaner and more internally consistent than real facility records. The project wins by handling messy, contradictory records.
- **Weak clinical grounding:** an LLM may know that ICU implies ventilators, but it can miss practical prerequisites such as staffing coverage, oxygen reliability, sterilization, or blood access.
- **Poor calibration:** synthetic labels can make the Trust Score look more precise than the evidence supports.
- **Judge defensibility:** "our domain expert reviewed 50 real records and built the rubric" is more credible than "we asked an LLM to supervise another LLM."
- **No discovery of real failure modes:** the contradiction taxonomy should emerge from actual facility records. Synthetic data tends to reflect what we already imagined.

Best use of synthetic/LLM supervision:

- pre-label facility records to speed up Naomi's review
- generate candidate contradiction types for Naomi to accept, edit, or reject
- create extra test cases after the real taxonomy is defined
- stress-test prompts against edge cases
- fill demo fixtures only when real examples are unavailable

The rule: LLMs can accelerate labeling, but Naomi should adjudicate the benchmark and rubric. That gives us both speed and credibility.
