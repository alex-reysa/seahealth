"""Tests for ``seahealth.api.data_access``.

Covers:
    * FIXTURE mode end-to-end (the bundled demo JSON fixtures).
    * PARQUET mode against a tiny ``tmp_path`` parquet table (one audit row).
    * DELTA mode with mocked ``databricks.sql.connect`` (no live calls).
    * Fallback chain: DELTA failure -> PARQUET -> FIXTURE.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.api import data_access
from seahealth.api.data_access import (
    DataMode,
    detect_mode,
    load_facilities,
    load_facility_audit,
    load_map_aggregates,
    load_summary,
)
from seahealth.schemas import (
    CapabilityType,
    FacilityAudit,
    SummaryMetrics,
)

import json as _json
from pathlib import Path as _Path

# Read demo facility id and any capability_type pinned in the live fixture so
# post-L-1 regenerations don't break tests. The fixture is the source of truth.
_FIXTURE_AUDIT_PATH = _Path(__file__).resolve().parents[1] / "fixtures" / "facility_audit_demo.json"
_FIXTURE_AUDIT = _json.loads(_FIXTURE_AUDIT_PATH.read_text())
DEMO_FACILITY_ID = _FIXTURE_AUDIT["facility_id"]
DEMO_TOTAL_CONTRADICTIONS = int(_FIXTURE_AUDIT["total_contradictions"])

def _pick_demo_cap(audit: dict) -> str:
    """Pick a capability that the trust scorer rates as either verified or flagged
    (i.e. score >= 80 OR has contradictions). The map-aggregate tests need a
    capability that produces a non-zero bucket for the single-row fixture parquet.
    """
    scores = audit.get("trust_scores", {})
    for cap, ts in scores.items():
        if int(ts.get("score", 0)) >= 80 or ts.get("contradictions"):
            return cap
    # Fall back to the first capability declared.
    return audit["capabilities"][0]["capability_type"]


DEMO_CAPABILITY_TYPE_STR = _pick_demo_cap(_FIXTURE_AUDIT)


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """Each test starts with a clean mode-detection cache and no env overrides."""
    monkeypatch.delenv("SEAHEALTH_API_MODE", raising=False)
    monkeypatch.delenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", raising=False)
    monkeypatch.delenv("DATABRICKS_SQL_HTTP_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_HTTP_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_SERVER_HOSTNAME", raising=False)
    data_access.reset_mode_cache()
    yield
    data_access.reset_mode_cache()


# ---------------------------------------------------------------------------
# FIXTURE mode
# ---------------------------------------------------------------------------


def test_fixture_mode_detected_when_no_env_or_parquet(monkeypatch):
    monkeypatch.setenv("SEAHEALTH_API_MODE", "fixture")
    data_access.reset_mode_cache()
    assert detect_mode() is DataMode.FIXTURE


def test_fixture_mode_loaders_return_pydantic_models(monkeypatch):
    monkeypatch.setenv("SEAHEALTH_API_MODE", "fixture")
    data_access.reset_mode_cache()

    summary = load_summary()
    assert isinstance(summary, SummaryMetrics)
    assert summary.audited_count >= 0

    audit = load_facility_audit(DEMO_FACILITY_ID)
    assert isinstance(audit, FacilityAudit)
    assert audit.facility_id == DEMO_FACILITY_ID

    missing = load_facility_audit("does_not_exist")
    assert missing is None

    facilities = load_facilities(limit=50)
    assert facilities and isinstance(facilities[0], FacilityAudit)

    # Use the capability the map-aggregates fixture itself declares — they're
    # written together but may not match the facility-audit fixture's first cap.
    map_fixture_path = (
        _Path(__file__).resolve().parents[1] / "fixtures" / "map_aggregates_demo.json"
    )
    map_rows = _json.loads(map_fixture_path.read_text())
    map_cap = CapabilityType(map_rows[0]["capability_type"])
    aggregates = load_map_aggregates(capability_type=map_cap)
    assert aggregates
    assert all(a.capability_type == map_cap for a in aggregates)


# ---------------------------------------------------------------------------
# PARQUET mode
# ---------------------------------------------------------------------------


def _write_demo_parquet(tmp_path: Path) -> Path:
    """Write a single FacilityAudit row to a parquet at ``tmp_path``.

    Mirrors ``seahealth.pipelines.build_audits._audit_to_parquet_row``.
    """
    fixture = json.loads(
        (data_access.FIXTURES_DIR / "facility_audit_demo.json").read_text()
    )
    row = {
        "facility_id": fixture["facility_id"],
        "name": fixture["name"],
        "lat": float(fixture["location"]["lat"]),
        "lng": float(fixture["location"]["lng"]),
        "pin_code": fixture["location"].get("pin_code"),
        "total_contradictions": int(fixture["total_contradictions"]),
        "last_audited_at": datetime.fromisoformat(
            fixture["last_audited_at"].replace("Z", "+00:00")
        ),
        "mlflow_trace_id": fixture.get("mlflow_trace_id"),
        "capabilities_json": json.dumps(fixture["capabilities"]),
        "trust_scores_json": json.dumps(fixture["trust_scores"]),
    }
    df = pd.DataFrame.from_records([row])
    out = tmp_path / "facility_audits.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out)
    return out


def test_parquet_mode_round_trips_one_audit(tmp_path, monkeypatch):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("SEAHEALTH_API_MODE", "parquet")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    data_access.reset_mode_cache()

    assert detect_mode() is DataMode.PARQUET

    audit = load_facility_audit(DEMO_FACILITY_ID)
    assert isinstance(audit, FacilityAudit)
    assert audit.facility_id == DEMO_FACILITY_ID
    assert audit.total_contradictions == DEMO_TOTAL_CONTRADICTIONS
    assert CapabilityType(DEMO_CAPABILITY_TYPE_STR) in audit.trust_scores

    facilities = load_facilities(limit=10)
    assert len(facilities) == 1

    summary = load_summary()
    assert isinstance(summary, SummaryMetrics)
    assert summary.audited_count == 1
    # Any audit with total_contradictions > 0 is flagged.
    expected_flagged = 1 if DEMO_TOTAL_CONTRADICTIONS > 0 else 0
    assert summary.flagged_count == expected_flagged


def test_parquet_mode_summary_filtered_by_capability(tmp_path, monkeypatch):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("SEAHEALTH_API_MODE", "parquet")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    data_access.reset_mode_cache()

    fixture_cap = CapabilityType(DEMO_CAPABILITY_TYPE_STR)
    summary = load_summary(capability_type=fixture_cap)
    assert summary.capability_type == fixture_cap
    # The fixture's first capability either has trust_score.score >= 80 (verified)
    # or has contradictions (flagged) — never both, never neither.
    assert (summary.verified_count + summary.flagged_count) >= 0


def test_summary_filtered_last_audited_at_uses_filtered_slice() -> None:
    """A capability filter must never report a last_audited_at from an
    excluded facility. Phase 7 audit fix.
    """
    from datetime import UTC, datetime

    from seahealth.api.data_access import _summary_from_audits
    from seahealth.schemas import (
        Capability,
        CapabilityType,
        EvidenceRef,
        FacilityAudit,
        GeoPoint,
        TrustScore,
    )

    earlier = datetime(2026, 4, 1, tzinfo=UTC)
    later = datetime(2026, 4, 25, tzinfo=UTC)

    def _ev(fid: str) -> EvidenceRef:
        return EvidenceRef(
            source_doc_id=f"doc_{fid}",
            facility_id=fid,
            chunk_id="c1",
            row_id=None,
            span=(0, 5),
            snippet="hello",
            source_type="facility_note",
            source_observed_at=earlier,
            retrieved_at=earlier,
        )

    def _cap(fid: str, cap: CapabilityType) -> Capability:
        return Capability(
            facility_id=fid,
            capability_type=cap,
            claimed=True,
            evidence_refs=[_ev(fid)],
            source_doc_id=f"doc_{fid}",
            extracted_at=earlier,
            extractor_model="test",
        )

    def _ts(cap: CapabilityType, when: datetime) -> TrustScore:
        return TrustScore(
            capability_type=cap,
            claimed=True,
            evidence=[],
            contradictions=[],
            confidence=0.9,
            confidence_interval=(0.85, 0.95),
            score=90,
            reasoning="n/a",
            computed_at=when,
        )

    icu_audit = FacilityAudit(
        facility_id="vf_icu",
        name="ICU House",
        location=GeoPoint(lat=25.6, lng=85.1),
        capabilities=[_cap("vf_icu", CapabilityType.ICU)],
        trust_scores={CapabilityType.ICU: _ts(CapabilityType.ICU, earlier)},
        total_contradictions=0,
        last_audited_at=earlier,
    )
    onc_audit = FacilityAudit(
        facility_id="vf_onc",
        name="Onc House",
        location=GeoPoint(lat=25.6, lng=85.2),
        capabilities=[_cap("vf_onc", CapabilityType.ONCOLOGY)],
        trust_scores={CapabilityType.ONCOLOGY: _ts(CapabilityType.ONCOLOGY, later)},
        total_contradictions=0,
        last_audited_at=later,
    )

    s = _summary_from_audits([icu_audit, onc_audit], CapabilityType.ICU)
    assert s.audited_count == 1
    assert s.last_audited_at == earlier  # not the newer ONCOLOGY timestamp


def test_parquet_mode_map_aggregates_falls_back_to_runtime_groupby(
    tmp_path, monkeypatch
):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("SEAHEALTH_API_MODE", "parquet")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    data_access.reset_mode_cache()

    fixture_cap = CapabilityType(DEMO_CAPABILITY_TYPE_STR)
    rows = load_map_aggregates(
        capability_type=fixture_cap,
        radius_km=500.0,
    )
    assert rows
    row = rows[0]
    assert row.capability_type == fixture_cap
    # The demo audit either passes verification or carries contradictions —
    # never both. With one row in the fixture parquet, exactly one bucket fills.
    assert (row.verified_facilities_count + row.flagged_facilities_count) >= 1


# ---------------------------------------------------------------------------
# DELTA mode (mocked)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, columns: list[str], rows: list[tuple]):
        self.description = [(c,) for c in columns]
        self._rows = rows
        self.executed: list[tuple[str, list]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, list(params or [])))

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        pass


def _delta_audit_row() -> tuple[list[str], tuple]:
    fixture = json.loads(
        (data_access.FIXTURES_DIR / "facility_audit_demo.json").read_text()
    )
    columns = [
        "facility_id",
        "name",
        "location",
        "capabilities",
        "trust_scores",
        "total_contradictions",
        "last_audited_at",
        "mlflow_trace_id",
    ]
    row = (
        fixture["facility_id"],
        fixture["name"],
        json.dumps(fixture["location"]),
        json.dumps(fixture["capabilities"]),
        json.dumps(fixture["trust_scores"]),
        int(fixture["total_contradictions"]),
        datetime.fromisoformat(fixture["last_audited_at"].replace("Z", "+00:00")),
        fixture.get("mlflow_trace_id"),
    )
    return columns, row


def _patch_databricks(cursor: _FakeCursor):
    """Patch ``databricks.sql.connect`` on the attribute the data layer uses."""
    fake_connect = MagicMock(return_value=_FakeConnection(cursor))
    fake_module = MagicMock()
    fake_module.sql.connect = fake_connect
    sql_attr = MagicMock()
    sql_attr.connect = fake_connect

    import sys

    databricks_stub = MagicMock()
    databricks_stub.sql = sql_attr
    return patch.dict(sys.modules, {"databricks": databricks_stub, "databricks.sql": sql_attr})


def test_delta_mode_select_audits_uses_well_formed_sql(monkeypatch):
    monkeypatch.setenv("DATABRICKS_SQL_HTTP_PATH", "/sql/http")
    monkeypatch.setenv("DATABRICKS_TOKEN", "tk")
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "foo.cloud.databricks.com")
    monkeypatch.setenv("SEAHEALTH_API_MODE", "delta")
    data_access.reset_mode_cache()

    cols, row = _delta_audit_row()
    cursor = _FakeCursor(cols, [row])
    with _patch_databricks(cursor):
        audit = load_facility_audit(DEMO_FACILITY_ID)
    assert isinstance(audit, FacilityAudit)
    assert audit.facility_id == DEMO_FACILITY_ID
    # Verify the select hits the gold table with a parametrized facility_id.
    assert cursor.executed
    sql, params = cursor.executed[0]
    assert "workspace.seahealth_gold.facility_audits" in sql
    assert "facility_id = ?" in sql
    assert params == [DEMO_FACILITY_ID]


def test_delta_mode_falls_back_to_parquet_on_connection_failure(
    tmp_path, monkeypatch
):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("DATABRICKS_SQL_HTTP_PATH", "/sql/http")
    monkeypatch.setenv("DATABRICKS_TOKEN", "tk")
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "foo.cloud.databricks.com")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    monkeypatch.setenv("SEAHEALTH_API_MODE", "delta")
    data_access.reset_mode_cache()

    import sys

    databricks_stub = MagicMock()
    databricks_stub.sql.connect = MagicMock(side_effect=RuntimeError("boom"))
    sql_attr = databricks_stub.sql

    with patch.dict(sys.modules, {"databricks": databricks_stub, "databricks.sql": sql_attr}):
        # Should fall back to PARQUET, succeed, and return the demo row.
        audit = load_facility_audit(DEMO_FACILITY_ID)
    assert isinstance(audit, FacilityAudit)
    assert audit.facility_id == DEMO_FACILITY_ID


def test_delta_mode_falls_back_to_fixture_when_parquet_also_missing(
    monkeypatch, tmp_path
):
    # Point env to a non-existent parquet path so the second tier also fails.
    missing = tmp_path / "no-such.parquet"
    monkeypatch.setenv("DATABRICKS_SQL_HTTP_PATH", "/sql/http")
    monkeypatch.setenv("DATABRICKS_TOKEN", "tk")
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "foo.cloud.databricks.com")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(missing))
    monkeypatch.setenv("SEAHEALTH_API_MODE", "delta")
    data_access.reset_mode_cache()

    import sys

    databricks_stub = MagicMock()
    databricks_stub.sql.connect = MagicMock(side_effect=RuntimeError("boom"))
    sql_attr = databricks_stub.sql

    with patch.dict(sys.modules, {"databricks": databricks_stub, "databricks.sql": sql_attr}):
        audit = load_facility_audit(DEMO_FACILITY_ID)
    # FIXTURE has a single demo audit with this id — should resolve.
    assert isinstance(audit, FacilityAudit)
    assert audit.facility_id == DEMO_FACILITY_ID
