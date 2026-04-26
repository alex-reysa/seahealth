"""Contract tests: docs/api/openapi.yaml must reflect runtime API responses.

Phase 7 audit: HealthDataResponse and SummaryMetrics gained fields after the
yaml was last regenerated, so these tests pin the field set to the actual
FastAPI schema. If a future schema change breaks these tests, regenerate
the yaml from `app.openapi()` and update accordingly — don't loosen the
assertions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

OPENAPI_YAML = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.yaml"


def _committed_openapi() -> dict:
    """Load the committed YAML without pulling in PyYAML."""
    pytest.importorskip("yaml")
    import yaml  # type: ignore[import-not-found]

    with OPENAPI_YAML.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _live_openapi() -> dict:
    from seahealth.api.main import app

    return json.loads(json.dumps(app.openapi()))


def _props(schema: dict) -> set[str]:
    return set((schema or {}).get("properties", {}).keys())


def test_committed_openapi_matches_runtime_health_data() -> None:
    committed = _committed_openapi()
    live = _live_openapi()
    committed_props = _props(committed["components"]["schemas"]["HealthDataResponse"])
    live_props = _props(live["components"]["schemas"]["HealthDataResponse"])
    # Phase 2A and Phase 7 fields must be present in both.
    must_have = {
        "mode",
        "facility_audits_path",
        "delta_reachable",
        "retriever_mode",
        "vs_endpoint",
        "vs_index",
    }
    missing_committed = must_have - committed_props
    missing_live = must_have - live_props
    assert not missing_committed, (
        f"docs/api/openapi.yaml HealthDataResponse missing: {sorted(missing_committed)}"
    )
    assert not missing_live, (
        f"runtime HealthDataResponse missing: {sorted(missing_live)}"
    )


def test_committed_openapi_matches_runtime_summary_metrics() -> None:
    committed = _committed_openapi()
    live = _live_openapi()
    committed_props = _props(committed["components"]["schemas"]["SummaryMetrics"])
    live_props = _props(live["components"]["schemas"]["SummaryMetrics"])
    must_have = {
        "audited_count",
        "verified_count",
        "flagged_count",
        "last_audited_at",
        "capability_type",
        "verified_count_ci",
    }
    missing_committed = must_have - committed_props
    missing_live = must_have - live_props
    assert not missing_committed, (
        f"docs/api/openapi.yaml SummaryMetrics missing: {sorted(missing_committed)}"
    )
    assert not missing_live, f"runtime SummaryMetrics missing: {sorted(missing_live)}"


def test_committed_openapi_matches_runtime_query_result() -> None:
    """Phase 2 added trace + lifecycle fields onto QueryResult."""
    committed = _committed_openapi()
    live = _live_openapi()
    committed_props = _props(committed["components"]["schemas"]["QueryResult"])
    live_props = _props(live["components"]["schemas"]["QueryResult"])
    must_have = {
        "query",
        "parsed_intent",
        "ranked_facilities",
        "total_candidates",
        "query_trace_id",
        "mlflow_trace_id",
        "mlflow_trace_url",
        "execution_steps",
        "retriever_mode",
        "used_llm",
        "generated_at",
    }
    missing_committed = must_have - committed_props
    missing_live = must_have - live_props
    assert not missing_committed, (
        f"docs/api/openapi.yaml QueryResult missing: {sorted(missing_committed)}"
    )
    assert not missing_live, f"runtime QueryResult missing: {sorted(missing_live)}"


def test_committed_openapi_matches_runtime_map_region_aggregate() -> None:
    """Phase 4 added population_source so the UI can be honest about denominators."""
    committed = _committed_openapi()
    live = _live_openapi()
    committed_props = _props(committed["components"]["schemas"]["MapRegionAggregate"])
    live_props = _props(live["components"]["schemas"]["MapRegionAggregate"])
    must_have = {
        "region_id",
        "region_name",
        "state",
        "capability_type",
        "population",
        "verified_facilities_count",
        "flagged_facilities_count",
        "gap_population",
        "centroid",
        "population_source",
    }
    missing_committed = must_have - committed_props
    missing_live = must_have - live_props
    assert not missing_committed, (
        f"docs/api/openapi.yaml MapRegionAggregate missing: {sorted(missing_committed)}"
    )
    assert not missing_live, f"runtime MapRegionAggregate missing: {sorted(missing_live)}"
