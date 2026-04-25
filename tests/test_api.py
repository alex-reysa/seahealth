"""FastAPI Phase-1E stub tests — exercise the in-process app via TestClient.

Each fixture-backed endpoint must:
  - return 200,
  - round-trip cleanly through its declared Pydantic response model,
  - mirror the demo fixture content the UI was sized against.

Phase 4 K-1 added a real-data path; the existing tests still run in FIXTURE
mode (no ``tables/facility_audits.parquet`` is checked into the worktree).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from seahealth.api import data_access
from seahealth.api.main import app
from seahealth.schemas import (
    FacilityAudit,
    MapRegionAggregate,
    QueryResult,
    SummaryMetrics,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_data_mode():
    """Ensure each test gets a fresh mode-detection."""
    data_access.reset_mode_cache()
    yield
    data_access.reset_mode_cache()

# Pin the demo facility id so renames in the fixture surface as test failures.
DEMO_FACILITY_ID = "vf_00042_patna_general_hospi"


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_summary_returns_valid_metrics_and_accepts_capability_filter():
    # Unfiltered: capability_type is None.
    base = client.get("/summary")
    assert base.status_code == 200
    base_model = SummaryMetrics.model_validate(base.json())
    assert base_model.capability_type is None
    assert base_model.audited_count >= 0

    # Filtered: param is accepted and surfaced on the response.
    filtered = client.get("/summary", params={"capability_type": "SURGERY_APPENDECTOMY"})
    assert filtered.status_code == 200
    filt_model = SummaryMetrics.model_validate(filtered.json())
    assert filt_model.capability_type == "SURGERY_APPENDECTOMY"


def test_query_returns_valid_result_and_top_row_has_missing_staff_contradiction():
    resp = client.post("/query", json={"query": "appendectomy near Patna?"})
    assert resp.status_code == 200
    result = QueryResult.model_validate(resp.json())
    assert result.query == "appendectomy near Patna?"
    assert len(result.ranked_facilities) >= 5

    top = result.ranked_facilities[0]
    assert top.facility_id == DEMO_FACILITY_ID
    assert any(c.contradiction_type == "MISSING_STAFF" for c in top.trust_score.contradictions)


def test_query_missing_body_field_returns_422():
    # Missing the required `query` key.
    resp = client.post("/query", json={})
    assert resp.status_code == 422


def test_facility_audit_returns_valid_audit_for_demo_id():
    resp = client.get(f"/facilities/{DEMO_FACILITY_ID}")
    assert resp.status_code == 200
    audit = FacilityAudit.model_validate(resp.json())
    assert audit.facility_id == DEMO_FACILITY_ID
    assert audit.total_contradictions == 2
    assert "SURGERY_APPENDECTOMY" in audit.trust_scores


def test_facility_audit_unknown_id_returns_404():
    resp = client.get("/facilities/does_not_exist")
    assert resp.status_code == 404


def test_map_aggregates_returns_valid_rows_and_capability_filter_works():
    resp = client.get("/map/aggregates")
    assert resp.status_code == 200
    rows = [MapRegionAggregate.model_validate(r) for r in resp.json()]
    assert len(rows) >= 5
    assert all(r.capability_type == "SURGERY_APPENDECTOMY" for r in rows)

    # Filtering for a capability with no rows yields an empty list (still 200).
    empty = client.get("/map/aggregates", params={"capability_type": "ICU"})
    assert empty.status_code == 200
    assert empty.json() == []


def test_facilities_list_returns_at_most_50_valid_audits():
    resp = client.get("/facilities")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) <= 50
    for entry in payload:
        FacilityAudit.model_validate(entry)


# ---------------------------------------------------------------------------
# Phase 4 K-1 additions
# ---------------------------------------------------------------------------


def test_query_endpoint_uses_heuristic_when_no_api_key(monkeypatch):
    """When DATABRICKS_TOKEN is unset, /query must still resolve a Patna
    appendectomy query into a shape-correct QueryResult."""
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    # Force PARQUET-look-alike off so the FIXTURE shortcut is engaged but the
    # heuristic path is also exercised by the underlying agent if invoked.
    monkeypatch.delenv("DATABRICKS_SQL_HTTP_PATH", raising=False)
    monkeypatch.delenv("SEAHEALTH_API_MODE", raising=False)
    data_access.reset_mode_cache()

    resp = client.post("/query", json={"query": "appendectomy near Patna?"})
    assert resp.status_code == 200
    body = resp.json()
    result = QueryResult.model_validate(body)
    assert result.query == "appendectomy near Patna?"
    # parsed_intent + ranked_facilities + trace id must all be present.
    assert result.query_trace_id
    assert result.parsed_intent is not None


def test_query_endpoint_emits_trace_header(monkeypatch):
    """The X-Query-Trace-Id response header must be non-empty."""
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    data_access.reset_mode_cache()

    resp = client.post("/query", json={"query": "appendectomy near Patna?"})
    assert resp.status_code == 200
    trace_id = resp.headers.get("X-Query-Trace-Id")
    assert trace_id is not None
    assert trace_id.strip()


def test_health_data_endpoint(monkeypatch):
    """/health/data returns a {mode, facility_audits_path, delta_reachable} triple."""
    # Default posture: no env override -> FIXTURE mode (no parquet on disk).
    monkeypatch.delenv("DATABRICKS_SQL_HTTP_PATH", raising=False)
    monkeypatch.delenv("SEAHEALTH_API_MODE", raising=False)
    monkeypatch.delenv("SEAHEALTH_FACILITY_AUDITS_PARQUET", raising=False)
    data_access.reset_mode_cache()

    resp = client.get("/health/data")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"mode", "facility_audits_path", "delta_reachable"}
    assert body["mode"] in {"delta", "parquet", "fixture"}
    assert isinstance(body["delta_reachable"], bool)
    assert isinstance(body["facility_audits_path"], str)


# ---------------------------------------------------------------------------
# AUD-07 hardening — error-path + pagination + content-type + fixture-503
# ---------------------------------------------------------------------------


def test_query_rejects_non_json_content_type():
    """POST /query must accept JSON only — form-encoded bodies are 422."""
    resp = client.post(
        "/query",
        content=b"query=appendectomy",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # FastAPI parses the body via the Pydantic model, which only accepts JSON;
    # a form-encoded body fails validation rather than being silently accepted.
    assert resp.status_code == 422


def test_facilities_limit_param_rejects_out_of_range_values():
    """The ``limit`` query param is validated to 1 <= limit <= 50."""
    too_low = client.get("/facilities", params={"limit": 0})
    assert too_low.status_code == 422
    too_high = client.get("/facilities", params={"limit": 51})
    assert too_high.status_code == 422
    negative = client.get("/facilities", params={"limit": -1})
    assert negative.status_code == 422


def test_facilities_limit_param_accepts_in_range_values():
    """``limit=1`` returns at most one row; ``limit=50`` is the documented max."""
    resp_one = client.get("/facilities", params={"limit": 1})
    assert resp_one.status_code == 200
    assert len(resp_one.json()) <= 1

    resp_max = client.get("/facilities", params={"limit": 50})
    assert resp_max.status_code == 200
    assert len(resp_max.json()) <= 50


def test_summary_503_when_fixture_missing(monkeypatch, tmp_path):
    """If the summary fixture is unreadable AND we're in FIXTURE mode, surface 503."""
    monkeypatch.setenv("SEAHEALTH_API_MODE", "fixture")
    # Point the loader at a non-existent fixture path.
    missing = tmp_path / "no_such_summary.json"
    monkeypatch.setattr(data_access, "SUMMARY_FIXTURE", missing)
    data_access.reset_mode_cache()

    resp = client.get("/summary")
    assert resp.status_code == 503
    detail = resp.json().get("detail", "")
    assert "data unavailable" in detail


def test_query_endpoint_returns_query_trace_id_in_body_too(monkeypatch):
    """Trace id is exposed on both the response body and the X-Query-Trace-Id header."""
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    data_access.reset_mode_cache()
    resp = client.post("/query", json={"query": "appendectomy near Patna?"})
    assert resp.status_code == 200
    body = resp.json()
    header_id = resp.headers.get("X-Query-Trace-Id")
    assert body["query_trace_id"] == header_id
