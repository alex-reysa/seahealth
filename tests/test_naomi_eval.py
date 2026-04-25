"""End-to-end tests for `seahealth.eval.run_eval.main`.

The synthetic fixtures live in `tests/fixtures/naomi/`. Their expected
metrics are pinned in the JSON's `_README` field and asserted here so a
mapping or metric drift trips a clear failure.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from seahealth.eval.run_eval import main as run_eval_main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "naomi"
SAMPLE_LABELS = FIXTURE_DIR / "sample_labels.csv"
SAMPLE_EXTRACTION = FIXTURE_DIR / "sample_extraction.json"


def test_run_eval_end_to_end(tmp_path):
    out_md = tmp_path / "report.md"
    result = run_eval_main(
        labels_csv=str(SAMPLE_LABELS),
        extractions_path=str(SAMPLE_EXTRACTION),
        audits_path=str(SAMPLE_EXTRACTION),
        output_md=str(out_md),
    )

    assert result["status"] == "ok"
    assert result["n_labels"] == 5
    assert result["n_facilities"] == 5

    # Capability metrics: TP=3, FP=3, FN=1 -> P=0.5, R=0.75, F1=0.6.
    assert result["capability_tp"] == 3
    assert result["capability_fp"] == 3
    assert result["capability_fn"] == 1
    assert result["capability_precision"] == pytest.approx(0.5, abs=1e-4)
    assert result["capability_recall"] == pytest.approx(0.75, abs=1e-4)
    assert result["capability_f1"] == pytest.approx(0.6, abs=1e-4)

    # Contradiction metrics: TP=2, FP=1, FN=1 -> P=R=F1=2/3.
    assert result["contradiction_tp"] == 2
    assert result["contradiction_fp"] == 1
    assert result["contradiction_fn"] == 1
    assert result["contradiction_precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["contradiction_recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["contradiction_f1"] == pytest.approx(2 / 3, abs=1e-4)

    # Row 5 (cardiology) doesn't map cleanly, so it must be reported as unmapped.
    assert result["unmapped_capability_rows"] == 1

    # Markdown report written and mentions the right sections.
    assert out_md.exists()
    text = out_md.read_text()
    assert "Capability extraction" in text
    assert "Contradiction detection" in text
    assert "Mapping limitations" in text
    assert "Per-capability breakdown" in text


def test_run_eval_empty_labels_returns_no_labels_status(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text(
        "label_id,facility_id,facility_name,raw_text_excerpt,claimed_capability,"
        "evidence_quote,evidence_status,missing_prerequisite,contradiction_type,"
        "clinical_plausibility,confidence,source_checked,source_url,source_type,"
        "accessed_date,demo_candidate,review_notes\n"
    )
    out_md = tmp_path / "report.md"
    result = run_eval_main(
        labels_csv=str(empty),
        extractions_path=str(SAMPLE_EXTRACTION),
        output_md=str(out_md),
    )
    assert result["status"] == "no_labels"
    assert "labels_csv" in result
    # Placeholder report is still written so downstream tooling can find it.
    assert out_md.exists()


def test_run_eval_missing_extractions_raises(tmp_path):
    bogus = tmp_path / "no_such_extractions.parquet"
    out_md = tmp_path / "report.md"
    with pytest.raises(FileNotFoundError) as excinfo:
        run_eval_main(
            labels_csv=str(SAMPLE_LABELS),
            extractions_path=str(bogus),
            output_md=str(out_md),
        )
    # Helpful message names the file path.
    assert str(bogus) in str(excinfo.value)


def test_run_eval_missing_labels_raises(tmp_path):
    bogus = tmp_path / "no_such_labels.csv"
    with pytest.raises(FileNotFoundError):
        run_eval_main(
            labels_csv=str(bogus),
            extractions_path=str(SAMPLE_EXTRACTION),
            output_md=None,
        )
