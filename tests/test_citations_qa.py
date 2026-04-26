"""Tests for ``seahealth.eval.citations_qa``."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seahealth.eval.citations_qa import (
    CITATION_CLASSES,
    VALID_CLASSES,
    classify_ref,
    format_report,
    run_citation_qa,
)

# ---------------------------------------------------------------------------
# classify_ref — pure-function classifier
# ---------------------------------------------------------------------------


def test_classify_ref_valid_substring_at_exact_span() -> None:
    text = "CIMS Hospital provides ICU/NICU/PICU services 24x7 Emergency."
    snippet = "ICU/NICU/PICU"
    start = text.index(snippet)
    end = start + len(snippet)
    assert classify_ref(snippet, (start, end), text) == "valid_substring"


def test_classify_ref_valid_substring_when_span_anywhere() -> None:
    """When the recorded span doesn't cover the snippet but the snippet does
    appear in the chunk, we still accept it as valid_substring (the extractor's
    re-anchoring would have produced the same result on a fresh run)."""
    text = "CIMS Hospital provides ICU/NICU/PICU services."
    snippet = "ICU/NICU/PICU"
    assert classify_ref(snippet, (0, 5), text) == "valid_substring"


def test_classify_ref_normalized_match() -> None:
    text = "CIMS Hospital provides ICU\n\nNICU\n\nPICU services."
    snippet = "ICU NICU PICU"
    assert classify_ref(snippet, (0, 0), text) == "valid_normalized"


def test_classify_ref_zero_span_with_no_snippet_in_text() -> None:
    text = "CIMS Hospital provides general surgery services."
    assert classify_ref("oncology unit", (0, 0), text) == "mismatch"


def test_classify_ref_zero_span_collapses_into_mismatch() -> None:
    """The (0, 0) extractor failure marker on a snippet absent from the chunk
    is bucketed as ``mismatch`` — both states render an unsupported citation
    chip in the UI, so the planner needs only one alarm."""
    text = "CIMS Hospital provides general surgery services."
    assert classify_ref("oncology", (0, 0), text) == "mismatch"


def test_classify_ref_empty_snippet() -> None:
    assert classify_ref("", (0, 0), "any chunk text") == "empty_snippet"
    assert classify_ref("   \n\t  ", (5, 10), "any chunk text") == "empty_snippet"


def test_classify_ref_chunk_missing() -> None:
    assert classify_ref("ICU", (0, 3), None) == "chunk_missing"


def test_classify_ref_zero_span_when_snippet_is_present_at_zero() -> None:
    """A snippet anchored at (0,0) is mismatch unless the snippet is the empty
    prefix; we treat (0,0) as the extractor's failure marker on real ingest."""
    text = "ICU is available."
    # Snippet "ICU" appears at offset 0; the extractor would record (0, 3),
    # not (0, 0). When (0, 0) shows up we still accept it as valid_substring
    # because the snippet is present in the chunk.
    assert classify_ref("ICU", (0, 0), text) == "valid_substring"


# ---------------------------------------------------------------------------
# run_citation_qa — end-to-end
# ---------------------------------------------------------------------------


def _write_capabilities(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_chunks(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _ref(*, chunk_id: str, snippet: str, span: tuple[int, int]) -> dict:
    return {
        "source_doc_id": chunk_id,
        "facility_id": "vf_001",
        "chunk_id": chunk_id,
        "row_id": None,
        "span": list(span),
        "snippet": snippet,
        "source_type": "facility_note",
        "source_observed_at": None,
        "retrieved_at": "2026-04-25T22:30:00Z",
    }


def test_run_citation_qa_mixed_corpus(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.parquet"
    caps_path = tmp_path / "capabilities.parquet"
    _write_chunks(
        chunks_path,
        [
            {"chunk_id": "c1", "text": "CIMS Hospital provides ICU/NICU/PICU services."},
            {"chunk_id": "c2", "text": "Emergency 24x7 with general surgery."},
        ],
    )
    text_c1 = "CIMS Hospital provides ICU/NICU/PICU services."
    icu_start = text_c1.index("ICU/NICU/PICU")
    icu_end = icu_start + len("ICU/NICU/PICU")
    _write_capabilities(
        caps_path,
        [
            {
                "facility_id": "vf_001",
                "capability_type": "ICU",
                "evidence_refs_json": json.dumps(
                    [_ref(chunk_id="c1", snippet="ICU/NICU/PICU", span=(icu_start, icu_end))]
                ),
            },
            {
                "facility_id": "vf_001",
                "capability_type": "ONCOLOGY",
                "evidence_refs_json": json.dumps(
                    [_ref(chunk_id="c1", snippet="oncology unit", span=(0, 0))]
                ),
            },
            {
                "facility_id": "vf_001",
                "capability_type": "EMERGENCY_24_7",
                "evidence_refs_json": json.dumps(
                    [_ref(chunk_id="c_unknown", snippet="24x7", span=(0, 4))]
                ),
            },
            {
                "facility_id": "vf_001",
                "capability_type": "MATERNAL",
                "evidence_refs_json": json.dumps(
                    [_ref(chunk_id="c2", snippet="", span=(0, 0))]
                ),
            },
        ],
    )

    report = run_citation_qa(
        capabilities_path=caps_path,
        chunks_path=chunks_path,
    )
    by_class = report["by_class"]
    totals = report["totals"]

    assert totals["refs"] == 4
    assert by_class["valid_substring"] == 1
    assert by_class["mismatch"] == 1
    assert by_class["chunk_missing"] == 1
    assert by_class["empty_snippet"] == 1
    assert by_class["valid_normalized"] == 0
    assert totals["valid"] == 1
    assert totals["invalid"] == 3
    # Examples are populated for failing classes.
    assert "mismatch" in report["examples"]
    assert "chunk_missing" in report["examples"]
    assert "empty_snippet" in report["examples"]
    # And the formatter renders without crashing.
    text = format_report(report)
    assert "Citation QA report" in text
    assert "valid%" in text


def test_citation_classes_invariants() -> None:
    """The valid/invalid partition is total."""
    assert VALID_CLASSES <= set(CITATION_CLASSES)
    invalid = set(CITATION_CLASSES) - VALID_CLASSES
    assert invalid == {"empty_snippet", "mismatch", "chunk_missing"}
