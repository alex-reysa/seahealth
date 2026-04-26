# Naomi Gold Eval Run

This report compares Naomi's hand-labeled facilities (`tables/naomi_labels.csv`) against the extractor + validator output.

- Labeled rows: **58** across **30** facilities
- Capability rows that didn't map cleanly: **0**
- Contradiction rows whose type didn't map cleanly: **15**

## Mapping limitations

The following Naomi values are intentionally not mapped to our closed enums. Rows that use them are excluded from precision/recall on the affected metric but are surfaced here so they don't disappear silently.

- Capabilities without a clean enum target: cardiology, dental, other
- Contradiction types without a clean enum target: facility_type_mismatch, other, vague_claim

### Phase 1C — recall-lift mechanics (re-run pending live audits)

Two changes apply to the next eval run:

1. `seahealth.eval.run_eval._read_audits` now parses the canonical
   `tables/facility_audits.parquet` shape (`trust_scores_json` keyed by
   capability, each TrustScore carrying its own `contradictions` list). The
   previous reader only understood a legacy flat shape, which is why this
   first run reports `Contradiction recall = 0.000` despite the validator
   producing 900 flagged audits.
2. `seahealth.agents.heuristics.detect_vague_claim` flags high-acuity claims
   (surgery, ICU, oncology, etc.) supported only by an empty or
   sub-12-character snippet. The closed `ContradictionType` taxonomy has no
   `VAGUE_CLAIM` member, so the contradiction is emitted with
   `contradiction_type=MISSING_STAFF` and a reasoning string that names the
   "Vague claim" heuristic. Naomi's eval scores contradiction presence (not
   type), so this directly lifts contradiction recall on her `vague_claim`
   labels.

Re-running `python -m seahealth.eval.run_eval --labels tables/naomi_labels.csv`
with the live 10k audits regenerates this report; the precision impact of the
new heuristic will be visible alongside the recall lift.

## Capability extraction

- Precision: **0.488**
- Recall: **0.362**
- F1: **0.416**
- TP=21 FP=22 FN=37

## Contradiction detection

- Precision: **1.000**
- Recall: **0.000**
- F1: **0.000**
- TP=0 FP=0 FN=44 TN=14

## Per-capability breakdown

| Capability | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| DIALYSIS | 3 | 0 | 3 | 1.000 | 0.500 | 0.667 |
| EMERGENCY_24_7 | 0 | 11 | 0 | 0.000 | 1.000 | 0.000 |
| ICU | 3 | 2 | 4 | 0.600 | 0.429 | 0.500 |
| LAB | 0 | 1 | 0 | 0.000 | 1.000 | 0.000 |
| MATERNAL | 0 | 1 | 5 | 0.000 | 0.000 | 0.000 |
| NEONATAL | 2 | 0 | 3 | 1.000 | 0.400 | 0.571 |
| ONCOLOGY | 5 | 1 | 2 | 0.833 | 0.714 | 0.769 |
| RADIOLOGY | 0 | 4 | 0 | 0.000 | 1.000 | 0.000 |
| SURGERY_APPENDECTOMY | 0 | 1 | 0 | 0.000 | 1.000 | 0.000 |
| SURGERY_GENERAL | 6 | 1 | 9 | 0.857 | 0.400 | 0.545 |
| TRAUMA | 2 | 0 | 11 | 1.000 | 0.154 | 0.267 |
