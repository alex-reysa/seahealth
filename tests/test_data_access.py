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

DEMO_FACILITY_ID = "vf_00042_patna_general_hospi"


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

    aggregates = load_map_aggregates(
        capability_type=CapabilityType.SURGERY_APPENDECTOMY
    )
    assert aggregates
    assert all(
        a.capability_type == CapabilityType.SURGERY_APPENDECTOMY for a in aggregates
    )


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
    assert audit.total_contradictions == 2
    assert CapabilityType.SURGERY_APPENDECTOMY in audit.trust_scores

    facilities = load_facilities(limit=10)
    assert len(facilities) == 1

    summary = load_summary()
    assert isinstance(summary, SummaryMetrics)
    assert summary.audited_count == 1
    # The demo audit has total_contradictions == 2 -> flagged_count == 1.
    assert summary.flagged_count == 1


def test_parquet_mode_summary_filtered_by_capability(tmp_path, monkeypatch):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("SEAHEALTH_API_MODE", "parquet")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    data_access.reset_mode_cache()

    summary = load_summary(capability_type=CapabilityType.SURGERY_APPENDECTOMY)
    assert summary.capability_type == CapabilityType.SURGERY_APPENDECTOMY
    # The demo audit has score=65 and a HIGH contradiction -> not verified.
    assert summary.verified_count == 0
    # It does carry contradictions for SURGERY_APPENDECTOMY -> flagged.
    assert summary.flagged_count == 1


def test_parquet_mode_map_aggregates_falls_back_to_runtime_groupby(
    tmp_path, monkeypatch
):
    parquet = _write_demo_parquet(tmp_path)
    monkeypatch.setenv("SEAHEALTH_API_MODE", "parquet")
    monkeypatch.setenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", str(parquet))
    data_access.reset_mode_cache()

    rows = load_map_aggregates(
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        radius_km=500.0,
    )
    assert rows
    row = rows[0]
    assert row.capability_type == CapabilityType.SURGERY_APPENDECTOMY
    # The demo audit is flagged for SURGERY_APPENDECTOMY (HIGH contradiction).
    assert row.flagged_facilities_count == 1


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
