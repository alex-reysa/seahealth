"""Tests for ``seahealth.pipelines.validate``.

Mocks the retriever and the validator LLM client so the pipeline can run
without a real Vector Search endpoint or network. Asserts:

* `contradictions.parquet` and `evidence_assessments.parquet` are written in
  the schema that ``build_audits._row_json_field(row, "payload")`` consumes
  unchanged.
* Heuristics-only mode (``use_llm=False``) writes contradictions for high-
  acuity claims missing equipment/staff.
* LLM mode wires the client factory through and produces non-empty
  ``EvidenceAssessment`` rows derived from retrieved evidence.
* Resulting parquets round-trip through :func:`seahealth.pipelines.build_audits.main`,
  bumping ``total_contradictions`` on the produced audit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.pipelines import build_audits, validate
from seahealth.schemas import IndexedDoc

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_capabilities_parquet(path: Path) -> None:
    rows = [
        {
            "facility_id": "vf_a",
            "capability_type": "SURGERY_APPENDECTOMY",
            "claimed": True,
            "source_doc_id": "vf_a",
            "extractor_model": "test-model",
            "extracted_at": NOW.isoformat(),
            "evidence_refs_json": json.dumps(
                [
                    {
                        "source_doc_id": "vf_a",
                        "facility_id": "vf_a",
                        "chunk_id": "vf_a::facility_note",
                        "row_id": None,
                        "span": [0, 30],
                        "snippet": "general surgery including appendectomy",
                        "source_type": "facility_note",
                        "source_observed_at": None,
                        "retrieved_at": NOW.isoformat(),
                    }
                ],
                ensure_ascii=False,
            ),
            "mlflow_trace_id": "local::vf_a::deadbeef",
        },
        {
            "facility_id": "vf_b",
            "capability_type": "DIALYSIS",
            "claimed": True,
            "source_doc_id": "vf_b",
            "extractor_model": "test-model",
            "extracted_at": NOW.isoformat(),
            "evidence_refs_json": json.dumps(
                [
                    {
                        "source_doc_id": "vf_b",
                        "facility_id": "vf_b",
                        "chunk_id": "vf_b::facility_note",
                        "row_id": None,
                        "span": [0, 12],
                        "snippet": "dialysis unit",
                        "source_type": "facility_note",
                        "source_observed_at": None,
                        "retrieved_at": NOW.isoformat(),
                    }
                ],
                ensure_ascii=False,
            ),
            "mlflow_trace_id": "local::vf_b::deadbeef",
        },
    ]
    df = pd.DataFrame(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_facilities_index_parquet(path: Path) -> None:
    rows = [
        {
            "facility_id": "vf_a",
            "row_index": 0,
            "name": "Hospital A",
            "address_city": "Patna",
            "address_stateOrRegion": "Bihar",
            "pin_code": "800001",
            "latitude": 25.61,
            "longitude": 85.14,
            "recency_of_page_update": "3 months",
            "facilityTypeId": "hospital",
            "numberDoctors": 0,  # forces MISSING_STAFF on SURGERY_APPENDECTOMY
            "capacity": 50,
        },
        {
            "facility_id": "vf_b",
            "row_index": 1,
            "name": "Clinic B",
            "address_city": "Patna",
            "address_stateOrRegion": "Bihar",
            "pin_code": "800002",
            "latitude": 25.62,
            "longitude": 85.15,
            "recency_of_page_update": None,
            "facilityTypeId": "clinic",
            "numberDoctors": 6,
            "capacity": 10,
        },
    ]
    df = pd.DataFrame(rows)
    df["numberDoctors"] = df["numberDoctors"].astype("Int64")
    df["capacity"] = df["capacity"].astype("Int64")
    df["row_index"] = df["row_index"].astype("Int64")
    df["latitude"] = df["latitude"].astype("float64")
    df["longitude"] = df["longitude"].astype("float64")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_subset_json(path: Path, ids: list[str]) -> None:
    path.write_text(json.dumps({"facility_ids": ids, "_meta": {"cap": 250}}), encoding="utf-8")


class _StubRetriever:
    """In-memory retriever that always returns one IndexedDoc per facility."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, query: str, k: int, facility_id: str | None = None) -> list[IndexedDoc]:
        self.calls.append({"query": query, "k": k, "facility_id": facility_id})
        if not facility_id:
            return []
        return [
            IndexedDoc(
                doc_id=f"{facility_id}::staff_roster",
                facility_id=facility_id,
                text=f"Staff roster for {facility_id}: 0 anesthesiologists.",
                embedding=[0.0] * 1024,
                chunk_index=0,
                source_type="staff_roster",
                source_observed_at=None,
                metadata={
                    "source_doc_id": facility_id,
                    "span_start": "0",
                    "span_end": "20",
                },
            )
        ]


class _StubValidatorClient:
    """Records calls; returns a canned validator-shape payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def structured_call(self, prompt: str, *, model: str) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "model": model})
        return self.payload


def _scaffold(tmp_path: Path) -> dict[str, Path]:
    cap_path = tmp_path / "capabilities.parquet"
    idx_path = tmp_path / "facilities_index.parquet"
    sub_path = tmp_path / "demo_subset.json"
    contradictions_path = tmp_path / "contradictions.parquet"
    assessments_path = tmp_path / "evidence_assessments.parquet"
    _write_capabilities_parquet(cap_path)
    _write_facilities_index_parquet(idx_path)
    _write_subset_json(sub_path, ["vf_a", "vf_b"])
    return {
        "tables_dir": tmp_path,
        "capabilities": cap_path,
        "facilities_index": idx_path,
        "subset": sub_path,
        "contradictions": contradictions_path,
        "assessments": assessments_path,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validate_heuristics_only_writes_payload_parquets(tmp_path: Path) -> None:
    paths = _scaffold(tmp_path)
    retriever = _StubRetriever()

    summary = validate.main(
        subset="demo",
        use_llm=False,
        tables_dir=paths["tables_dir"],
        capabilities_path=paths["capabilities"],
        facilities_index_path=paths["facilities_index"],
        subset_path=paths["subset"],
        contradictions_out=paths["contradictions"],
        assessments_out=paths["assessments"],
        retriever=retriever,
    )

    assert summary["facility_count"] == 2
    assert summary["capability_count"] == 2
    # vf_a (SURGERY_APPENDECTOMY) has staff_count=0 → MISSING_STAFF + MISSING_EQUIPMENT.
    assert summary["contradiction_count"] >= 1
    # Heuristics-only path emits no LLM EvidenceAssessment rows.
    assert summary["assessment_count"] == 0
    # Retriever was consulted once per capability.
    assert len(retriever.calls) == 2

    contradictions_df = pq.read_table(paths["contradictions"]).to_pandas()
    assert set(contradictions_df.columns) >= {
        "facility_id",
        "capability_type",
        "contradiction_type",
        "severity",
        "detected_by",
        "payload",
    }
    # Every payload must reload as a Contradiction.
    for raw in contradictions_df["payload"]:
        decoded = json.loads(raw)
        assert {"contradiction_type", "facility_id", "severity"} <= decoded.keys()


def test_validate_llm_mode_writes_evidence_assessments(tmp_path: Path) -> None:
    paths = _scaffold(tmp_path)
    retriever = _StubRetriever()
    payload = {
        "evidence_assessments": [
            {
                "evidence_ref_id": "vf_a:vf_a::staff_roster",
                "stance": "contradicts",
                "reasoning": "Staff roster lists 0 anesthesiologists.",
            }
        ],
        "additional_contradictions": [
            {
                "contradiction_type": "CONFLICTING_SOURCES",
                "severity": "HIGH",
                "reasoning": "Claim conflicts with the staff roster.",
            }
        ],
        "heuristic_reasoning_overrides": {},
    }
    stub_client = _StubValidatorClient(payload)

    summary = validate.main(
        subset="demo",
        use_llm=True,
        tables_dir=paths["tables_dir"],
        capabilities_path=paths["capabilities"],
        facilities_index_path=paths["facilities_index"],
        subset_path=paths["subset"],
        contradictions_out=paths["contradictions"],
        assessments_out=paths["assessments"],
        retriever=retriever,
        client_factory=lambda: stub_client,
    )

    assert summary["assessment_count"] >= 1
    assert summary["contradiction_count"] >= 1
    assert stub_client.calls, "validator LLM client should have been called"

    assessments_df = pq.read_table(paths["assessments"]).to_pandas()
    assert "payload" in assessments_df.columns
    decoded = json.loads(assessments_df["payload"].iloc[0])
    assert decoded["stance"] in {"verifies", "contradicts", "silent"}
    assert decoded["evidence_ref_id"] == "vf_a:vf_a::staff_roster"


def test_validate_outputs_are_consumed_by_build_audits(tmp_path: Path) -> None:
    """The new parquets must round-trip through build_audits unchanged."""
    paths = _scaffold(tmp_path)
    retriever = _StubRetriever()

    validate.main(
        subset="demo",
        use_llm=False,
        tables_dir=paths["tables_dir"],
        capabilities_path=paths["capabilities"],
        facilities_index_path=paths["facilities_index"],
        subset_path=paths["subset"],
        contradictions_out=paths["contradictions"],
        assessments_out=paths["assessments"],
        retriever=retriever,
    )

    summary = build_audits.main(tables_dir=paths["tables_dir"], subset="demo")

    assert summary["audit_count"] == 2
    # contradictions parquet was read and at least one feeds into the audit.
    assert summary["contradiction_count"] >= 1


def test_validate_respects_limit_and_subset(tmp_path: Path) -> None:
    paths = _scaffold(tmp_path)
    retriever = _StubRetriever()

    summary = validate.main(
        subset="demo",
        limit=1,
        use_llm=False,
        tables_dir=paths["tables_dir"],
        capabilities_path=paths["capabilities"],
        facilities_index_path=paths["facilities_index"],
        subset_path=paths["subset"],
        contradictions_out=paths["contradictions"],
        assessments_out=paths["assessments"],
        retriever=retriever,
    )

    # Only the first facility's capability is processed.
    assert summary["capability_count"] == 1
    assert summary["facility_count"] == 1
    assert len(retriever.calls) == 1


def test_validate_skips_mlflow_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _scaffold(tmp_path)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    import mlflow  # type: ignore

    def _boom(*_a, **_kw):  # pragma: no cover - must not run
        raise AssertionError("mlflow.start_span must not be called when unconfigured")

    monkeypatch.setattr(mlflow, "start_span", _boom)

    summary = validate.main(
        subset="demo",
        use_llm=False,
        tables_dir=paths["tables_dir"],
        capabilities_path=paths["capabilities"],
        facilities_index_path=paths["facilities_index"],
        subset_path=paths["subset"],
        contradictions_out=paths["contradictions"],
        assessments_out=paths["assessments"],
        retriever=_StubRetriever(),
    )
    assert summary["facility_count"] == 2
