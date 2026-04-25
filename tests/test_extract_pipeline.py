"""Tests for ``seahealth.pipelines.extract``.

Mocks the extractor so the pipeline can run without an Anthropic client.
Verifies it reads the demo subset + chunks parquet correctly, writes
``capabilities.parquet``, and skips MLflow / Delta when not configured.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.agents.extractor import ExtractedCapabilities
from seahealth.pipelines import extract as extract_pipeline
from seahealth.schemas import Capability, CapabilityType, EvidenceRef


def _build_chunks_parquet(tmp_path: Path) -> Path:
    rows = [
        {
            "chunk_id": "vf_a::facility_note",
            "facility_id": "vf_a",
            "row_index": 0,
            "source_type": "facility_note",
            "source_doc_id": "vf_a",
            "text": "Hospital A offers general surgery.",
            "span_start": 0,
            "span_end": 35,
            "indexed_at": "2026-04-25T00:00:00+00:00",
        },
        {
            "chunk_id": "vf_a::staff_roster",
            "facility_id": "vf_a",
            "row_index": 0,
            "source_type": "staff_roster",
            "source_doc_id": "vf_a",
            "text": "5 surgeons on staff.",
            "span_start": 0,
            "span_end": 20,
            "indexed_at": "2026-04-25T00:00:00+00:00",
        },
        {
            "chunk_id": "vf_b::facility_note",
            "facility_id": "vf_b",
            "row_index": 1,
            "source_type": "facility_note",
            "source_doc_id": "vf_b",
            "text": "Clinic B offers dialysis.",
            "span_start": 0,
            "span_end": 25,
            "indexed_at": "2026-04-25T00:00:00+00:00",
        },
    ]
    df = pd.DataFrame(rows)
    out = tmp_path / "chunks.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out)
    return out


def _build_subset_json(tmp_path: Path, ids: list[str]) -> Path:
    out = tmp_path / "demo_subset.json"
    out.write_text(json.dumps({"facility_ids": ids, "_meta": {"cap": 250}}), encoding="utf-8")
    return out


def _make_capability(facility_id: str, ctype: CapabilityType) -> Capability:
    return Capability(
        facility_id=facility_id,
        capability_type=ctype,
        claimed=True,
        source_doc_id=facility_id,
        evidence_refs=[
            EvidenceRef(
                source_doc_id=facility_id,
                facility_id=facility_id,
                chunk_id=f"{facility_id}::facility_note",
                span=(0, 8),
                snippet="Hospital",
                source_type="facility_note",
                retrieved_at=datetime(2026, 4, 25, 0, 0, 0),
            )
        ],
        extracted_at=datetime(2026, 4, 25, 0, 0, 0),
        extractor_model="claude-sonnet-4-6",
    )


def test_pipeline_writes_capabilities_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks_path = _build_chunks_parquet(tmp_path)
    subset_path = _build_subset_json(tmp_path, ["vf_a", "vf_b"])
    out_path = tmp_path / "capabilities.parquet"

    # Make absolutely sure MLflow + Databricks paths are silent.
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)

    seen: list[str] = []

    def fake_extract(facility_id: str, chunks: list[dict], *, model: str) -> ExtractedCapabilities:
        seen.append(facility_id)
        ctype = CapabilityType.SURGERY_GENERAL if facility_id == "vf_a" else CapabilityType.DIALYSIS
        return ExtractedCapabilities(
            facility_id=facility_id,
            capabilities=[_make_capability(facility_id, ctype)],
        )

    summary = extract_pipeline.main(
        subset="demo",
        subset_path=subset_path,
        chunks_path=chunks_path,
        out_path=out_path,
        extract_fn=fake_extract,
    )

    assert seen == ["vf_a", "vf_b"]
    assert summary["facility_count"] == 2
    assert summary["capability_count"] == 2
    assert summary["delta_written"] is False

    df = pq.read_table(out_path).to_pandas()
    assert set(df["facility_id"]) == {"vf_a", "vf_b"}
    assert set(df["capability_type"]) == {"SURGERY_GENERAL", "DIALYSIS"}
    # Evidence refs round-trip through JSON.
    sample = json.loads(df.iloc[0]["evidence_refs_json"])
    assert sample[0]["chunk_id"].endswith("::facility_note")


def test_pipeline_respects_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chunks_path = _build_chunks_parquet(tmp_path)
    subset_path = _build_subset_json(tmp_path, ["vf_a", "vf_b"])
    out_path = tmp_path / "capabilities.parquet"

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)

    seen: list[str] = []

    def fake_extract(facility_id: str, chunks: list[dict], *, model: str) -> ExtractedCapabilities:
        seen.append(facility_id)
        return ExtractedCapabilities(
            facility_id=facility_id,
            capabilities=[_make_capability(facility_id, CapabilityType.LAB)],
        )

    summary = extract_pipeline.main(
        subset="demo",
        limit=1,
        subset_path=subset_path,
        chunks_path=chunks_path,
        out_path=out_path,
        extract_fn=fake_extract,
    )

    assert seen == ["vf_a"]
    assert summary["facility_count"] == 1
    assert summary["capability_count"] == 1


def test_pipeline_skips_mlflow_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pipeline should not import / call mlflow.start_span when env unset."""
    chunks_path = _build_chunks_parquet(tmp_path)
    subset_path = _build_subset_json(tmp_path, ["vf_a"])
    out_path = tmp_path / "capabilities.parquet"

    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)

    # If something tried to call mlflow.start_span we'd notice — patch it to
    # a function that raises and confirm it's never invoked.
    import mlflow  # type: ignore

    def _boom(*_args, **_kwargs):  # pragma: no cover — must not run
        raise AssertionError("mlflow.start_span should not be called when unconfigured")

    monkeypatch.setattr(mlflow, "start_span", _boom)

    def fake_extract(facility_id: str, chunks: list[dict], *, model: str) -> ExtractedCapabilities:
        return ExtractedCapabilities(facility_id=facility_id, capabilities=[])

    summary = extract_pipeline.main(
        subset="demo",
        subset_path=subset_path,
        chunks_path=chunks_path,
        out_path=out_path,
        extract_fn=fake_extract,
    )
    assert summary["facility_count"] == 1
    assert summary["capability_count"] == 0
    # Even with zero rows we still wrote a parquet file (with the canonical schema).
    assert out_path.exists()
    df = pq.read_table(out_path).to_pandas()
    assert list(df.columns) == [
        "facility_id",
        "capability_type",
        "claimed",
        "source_doc_id",
        "extractor_model",
        "extracted_at",
        "evidence_refs_json",
    ]
