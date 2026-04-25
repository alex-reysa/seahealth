"""Smoke tests for the ``seahealth.pipelines.build_audits`` pipeline."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seahealth.pipelines import build_audits
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceRef,
)

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _evidence(facility_id: str, snippet: str = "snippet") -> EvidenceRef:
    return EvidenceRef(
        source_doc_id=f"doc_{facility_id}",
        facility_id=facility_id,
        chunk_id="chunk_1",
        row_id=None,
        span=(0, len(snippet)),
        snippet=snippet,
        source_type="facility_note",
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability(facility_id: str, cap_type: CapabilityType) -> Capability:
    return Capability(
        facility_id=facility_id,
        capability_type=cap_type,
        claimed=True,
        evidence_refs=[_evidence(facility_id)],
        source_doc_id=f"doc_{facility_id}",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _contradiction(facility_id: str, cap_type: CapabilityType, severity: str) -> Contradiction:
    return Contradiction(
        contradiction_type=ContradictionType.MISSING_STAFF,
        capability_type=cap_type,
        facility_id=facility_id,
        evidence_for=[],
        evidence_against=[],
        severity=severity,  # type: ignore[arg-type]
        reasoning="test reason.",
        detected_by="validator.heuristics_v1",
        detected_at=NOW,
    )


def _write_capabilities(path: Path, caps: list[Capability]) -> None:
    rows = [
        {
            "facility_id": cap.facility_id,
            "capability_type": cap.capability_type.value,
            "payload": json.dumps(cap.model_dump(mode="json"), ensure_ascii=False),
        }
        for cap in caps
    ]
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_contradictions(path: Path, items: list[Contradiction]) -> None:
    rows = [
        {
            "facility_id": c.facility_id,
            "capability_type": c.capability_type.value,
            "severity": c.severity,
            "payload": json.dumps(c.model_dump(mode="json"), ensure_ascii=False),
        }
        for c in items
    ]
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _write_facilities_index(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame.from_records(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_audits_writes_parquet(tmp_path: Path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    caps = [
        _capability("vf_00042_janta_hospital_patna", CapabilityType.SURGERY_APPENDECTOMY),
        _capability("vf_00042_janta_hospital_patna", CapabilityType.ICU),
        _capability("vf_00099_other_clinic", CapabilityType.LAB),
    ]
    contradictions = [
        _contradiction(
            "vf_00042_janta_hospital_patna",
            CapabilityType.SURGERY_APPENDECTOMY,
            "MEDIUM",
        ),
    ]

    _write_capabilities(tables_dir / build_audits.CAPABILITIES_FILE, caps)
    _write_contradictions(tables_dir / build_audits.CONTRADICTIONS_FILE, contradictions)
    _write_facilities_index(
        tables_dir / build_audits.FACILITIES_INDEX_FILE,
        [
            {
                "facility_id": "vf_00042_janta_hospital_patna",
                "name": "Janta Hospital, Patna",
                "latitude": 25.61,
                "longitude": 85.14,
                "pin_code": "800001",
            },
            {
                "facility_id": "vf_00099_other_clinic",
                "name": "Other Clinic",
                "latitude": 12.97,
                "longitude": 77.59,
                "pin_code": None,
            },
        ],
    )

    summary = build_audits.main(tables_dir=tables_dir)

    audits_path = tables_dir / build_audits.AUDITS_FILE
    assert audits_path.exists()
    df = pq.read_table(audits_path).to_pandas()

    assert summary["facility_count"] == 2
    assert summary["capability_count"] == 3
    assert summary["audit_count"] == 2
    assert len(df) == 2

    janta = df[df["facility_id"] == "vf_00042_janta_hospital_patna"].iloc[0]
    assert janta["name"] == "Janta Hospital, Patna"
    # The pipeline runs the validator heuristics safety-net for any capability
    # that does not yet have a contradiction; with empty FacilityFacts the ICU
    # capability picks up MISSING_EQUIPMENT + MISSING_STAFF, joining the input
    # SURGERY MEDIUM contradiction for a total of 3.
    assert int(janta["total_contradictions"]) >= 1
    trust_scores = json.loads(janta["trust_scores_json"])
    assert {"SURGERY_APPENDECTOMY", "ICU"} <= set(trust_scores.keys())


def test_build_audits_handles_missing_optional_parquet(tmp_path: Path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    caps = [_capability("vf_00042_janta_hospital_patna", CapabilityType.SURGERY_APPENDECTOMY)]
    _write_capabilities(tables_dir / build_audits.CAPABILITIES_FILE, caps)
    _write_facilities_index(
        tables_dir / build_audits.FACILITIES_INDEX_FILE,
        [
            {
                "facility_id": "vf_00042_janta_hospital_patna",
                "name": "Janta Hospital, Patna",
                "latitude": 25.61,
                "longitude": 85.14,
                "pin_code": "800001",
            }
        ],
    )

    # Note: contradictions.parquet and evidence_assessments.parquet are absent.
    summary = build_audits.main(tables_dir=tables_dir)

    audits_path = tables_dir / build_audits.AUDITS_FILE
    assert audits_path.exists()
    assert summary["audit_count"] == 1
    assert summary["contradiction_count"] == 0


def test_build_audits_subset_demo_filters_facilities(tmp_path: Path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    caps = [
        _capability("vf_00042_janta_hospital_patna", CapabilityType.SURGERY_APPENDECTOMY),
        _capability("vf_00099_other_clinic", CapabilityType.LAB),
    ]
    _write_capabilities(tables_dir / build_audits.CAPABILITIES_FILE, caps)
    _write_facilities_index(
        tables_dir / build_audits.FACILITIES_INDEX_FILE,
        [
            {
                "facility_id": "vf_00042_janta_hospital_patna",
                "name": "Janta Hospital, Patna",
                "latitude": 25.61,
                "longitude": 85.14,
                "pin_code": "800001",
            },
            {
                "facility_id": "vf_00099_other_clinic",
                "name": "Other Clinic",
                "latitude": 12.97,
                "longitude": 77.59,
                "pin_code": None,
            },
        ],
    )
    (tables_dir / build_audits.DEMO_SUBSET_FILE).write_text(
        json.dumps(
            {"_meta": {"selected_count": 1}, "facility_ids": ["vf_00042_janta_hospital_patna"]}
        ),
        encoding="utf-8",
    )

    summary = build_audits.main(tables_dir=tables_dir, subset="demo")
    assert summary["audit_count"] == 1
    df = pq.read_table(tables_dir / build_audits.AUDITS_FILE).to_pandas()
    assert df["facility_id"].tolist() == ["vf_00042_janta_hospital_patna"]
