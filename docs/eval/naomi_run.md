# Naomi Gold Eval Run

This report compares Naomi's hand-labeled facilities (`docs/tasks/naomi_labeling_template.csv`) against the extractor + validator output.

> Last run: NOT YET RUN. Run `python -m seahealth.eval.run_eval --labels <path>` once Naomi delivers labels.

## How to run

```bash
python -m seahealth.eval.run_eval \
    --labels docs/tasks/naomi_labeling_template.csv \
    --extractions tables/capabilities.parquet \
    --audits tables/facility_audits.parquet \
    --output docs/eval/naomi_run.md
```

If `tables/*.parquet` are absent, pass JSON snapshots instead. If labels CSV is the empty template, the runner exits 0 and writes a placeholder report.

## Mapping limitations

The harness uses an explicit mapping (`src/seahealth/eval/naomi_mapping.py`) from Naomi's label vocabulary to the closed enums in `seahealth.schemas`. A few of Naomi's values have no clean target:

- **Capabilities without a closed-enum match**: `cardiology`, `dental`, `other`. Rows using these values are excluded from capability precision/recall but counted under "unmapped rows" in the report.
- **Contradiction types without a closed-enum match**: `vague_claim`, `facility_type_mismatch`, `other`. These rows still count as contradictions for recall purposes (presence-based scoring) but cannot be matched on type. The report's per-type breakdown will show them as "unmapped".
- **Approximate map**: `diagnostics` -> `RADIOLOGY` is the closest analogue; the closed enum has no broader "diagnostics" type.

If, when Naomi delivers labels, a meaningful share of rows fall into these buckets, the right move is to extend `CapabilityType` / `ContradictionType` rather than add fuzzy mappings.

## Capability extraction

- Precision: TBD
- Recall: TBD
- F1: TBD

## Contradiction detection

- Precision: TBD
- Recall: TBD
- F1: TBD

## Per-capability breakdown

(table TBD — auto-generated when the harness runs against real labels)

## Synthetic-fixture sanity check

The harness ships with a 5-row synthetic fixture (`tests/fixtures/naomi/sample_labels.csv` + `sample_extraction.json`). Running against it (see `tests/test_naomi_eval.py`) yields:

- Capability metrics: TP=3, FP=3, FN=1 -> precision 0.50, recall 0.75, F1 0.60
- Contradiction metrics: TP=2, FP=1, FN=1 -> precision 0.667, recall 0.667, F1 0.667
- Unmapped capability rows: 1 (the cardiology row)

These numbers exist purely to verify the harness wiring; they say nothing about how the real extractor + validator will score against Naomi's gold set.
