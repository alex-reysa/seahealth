"""FastAPI Phase-1E stub.

Six endpoints, each backed by a hand-crafted JSON fixture. No Databricks calls
yet — that's Phase 4. Every response goes through its Pydantic model so OpenAPI
is auto-generated from the same schemas the rest of the codebase imports.

Fixtures live under ``<repo_root>/fixtures/*.json``. They are loaded lazily on
first request (via ``functools.lru_cache``) so a missing file never crashes
import. Missing files surface as HTTP 503.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, TypeAdapter, ValidationError

from seahealth.schemas import (
    CapabilityType,
    FacilityAudit,
    MapRegionAggregate,
    QueryResult,
    SummaryMetrics,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# main.py -> api -> seahealth -> src -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"

SUMMARY_FIXTURE = FIXTURES_DIR / "summary_demo.json"
QUERY_FIXTURE = FIXTURES_DIR / "demo_query_appendectomy.json"
FACILITY_AUDIT_FIXTURE = FIXTURES_DIR / "facility_audit_demo.json"
MAP_AGGREGATES_FIXTURE = FIXTURES_DIR / "map_aggregates_demo.json"


# ---------------------------------------------------------------------------
# Lazy fixture loaders (cached on first hit, re-raise as 503 on miss)
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> object:
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"fixture not loaded: {path.relative_to(REPO_ROOT)}",
        )
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupted on disk
        raise HTTPException(
            status_code=503,
            detail=f"fixture not loaded: {path.relative_to(REPO_ROOT)} ({exc.msg})",
        )


@lru_cache(maxsize=1)
def _summary() -> SummaryMetrics:
    raw = _load_json(SUMMARY_FIXTURE)
    return SummaryMetrics.model_validate(raw)


@lru_cache(maxsize=1)
def _query_result() -> QueryResult:
    raw = _load_json(QUERY_FIXTURE)
    return QueryResult.model_validate(raw)


@lru_cache(maxsize=1)
def _facility_audit() -> FacilityAudit:
    raw = _load_json(FACILITY_AUDIT_FIXTURE)
    return FacilityAudit.model_validate(raw)


_MAP_AGGREGATES_ADAPTER = TypeAdapter(List[MapRegionAggregate])


@lru_cache(maxsize=1)
def _map_aggregates() -> List[MapRegionAggregate]:
    raw = _load_json(MAP_AGGREGATES_FIXTURE)
    return _MAP_AGGREGATES_ADAPTER.validate_python(raw)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """POST /query body."""

    query: str


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="SeaHealth API",
    version="0.1.0",
    description=(
        "Phase-1 stub serving hand-crafted demo fixtures. "
        "Phase 4 will swap the fixture loaders for live Databricks reads."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/summary", response_model=SummaryMetrics)
def get_summary(capability_type: Optional[CapabilityType] = None) -> SummaryMetrics:
    """Dashboard summary tile.

    The ``capability_type`` query param is currently advisory — Phase 1 returns
    the same fixture regardless, but the param is accepted and validated so the
    Phase 4 swap is a pure backend change.
    """
    metrics = _summary()
    if capability_type is not None:
        return metrics.model_copy(update={"capability_type": capability_type})
    return metrics


@app.post("/query", response_model=QueryResult)
def post_query(body: QueryRequest) -> QueryResult:
    """Planner Console query endpoint."""
    result = _query_result()
    # Echo the user-supplied query string so the UI shows what was asked.
    return result.model_copy(update={"query": body.query or result.query})


@app.get("/facilities/{facility_id}", response_model=FacilityAudit)
def get_facility(facility_id: str) -> FacilityAudit:
    """Facility Audit page payload."""
    audit = _facility_audit()
    if facility_id != audit.facility_id:
        raise HTTPException(
            status_code=404, detail=f"facility not found: {facility_id}"
        )
    return audit


@app.get("/map/aggregates", response_model=List[MapRegionAggregate])
def get_map_aggregates(
    capability_type: Optional[CapabilityType] = None,
    radius_km: Optional[float] = None,
) -> List[MapRegionAggregate]:
    """Desert Map choropleth payload."""
    rows = _map_aggregates()
    if capability_type is not None:
        rows = [r for r in rows if r.capability_type == capability_type]
    return rows


@app.get("/facilities", response_model=List[FacilityAudit])
def list_facilities() -> List[FacilityAudit]:
    """Faceted facility list (Phase 1 returns up to 50 from the demo fixture)."""
    return [_facility_audit()][:50]


__all__ = ["app"]
