"""SeaHealth FastAPI surface.

Phase 4 K-1 wires every endpoint to the unified ``data_access`` layer, which
auto-detects between three backends (DELTA -> PARQUET -> FIXTURE) and falls
back gracefully so the demo never hard-stops.

Endpoints:
    GET  /health             — liveness
    GET  /health/data        — current data-mode snapshot for the demo
    GET  /summary            — dashboard summary tile
    POST /query              — Planner Console query (Query Agent)
    GET  /facilities         — facet list
    GET  /facilities/{id}    — facility audit detail
    GET  /map/aggregates     — desert-map rollups

The 503 path surfaces ``DataLayerError`` with detail
``data unavailable: <reason>`` so the UI can distinguish a missing backend
from a 4xx caller error.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from seahealth.agents.query import run_query
from seahealth.schemas import (
    CapabilityType,
    FacilityAudit,
    MapRegionAggregate,
    QueryResult,
    SummaryMetrics,
)

from . import data_access
from .data_access import DataLayerError, DataMode

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """POST /query body."""

    query: str


class HealthDataResponse(BaseModel):
    """GET /health/data payload (used by the demo to confirm data wiring)."""

    mode: str
    facility_audits_path: str
    delta_reachable: bool


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="SeaHealth API",
    version="0.2.0",
    description=(
        "Phase-4 surface. Endpoints read through a unified data-access layer "
        "that auto-detects DELTA -> PARQUET -> FIXTURE and falls back "
        "gracefully so the demo never hard-stops."
    ),
)

# CORS: ``allow_origins=["*"]`` is fine for the local hackathon demo (read-only
# endpoints, no cookies, no credentials). TODO(prod): tighten to the deployed
# UI origin(s) before any non-demo deployment, e.g.
# ``allow_origins=["https://app.seahealth.example"]``.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _data_503(exc: DataLayerError) -> HTTPException:
    return HTTPException(status_code=503, detail=f"data unavailable: {exc}")


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/health/data", response_model=HealthDataResponse)
def health_data() -> HealthDataResponse:
    """Current data-mode snapshot. Useful for the demo to confirm wiring."""
    snapshot = data_access.health_snapshot()
    return HealthDataResponse(
        mode=snapshot["mode"],
        facility_audits_path=snapshot["facility_audits_path"],
        delta_reachable=bool(snapshot.get("delta_reachable", False)),
    )


@app.get("/summary", response_model=SummaryMetrics)
def get_summary(capability_type: CapabilityType | None = None) -> SummaryMetrics:
    """Dashboard summary tile (audited / verified / flagged counts)."""
    try:
        return data_access.load_summary(capability_type=capability_type)
    except DataLayerError as exc:
        raise _data_503(exc) from exc


QUERY_FIXTURE_PATH = data_access.FIXTURES_DIR / "demo_query_appendectomy.json"


def _query_fixture() -> QueryResult:
    """Load the bundled Planner Console demo fixture.

    Used in FIXTURE mode (no parquet/Delta available) so the demo always
    returns a populated ranked list — the heuristic agent has nothing to
    rank when the audits parquet is absent.
    """
    if not QUERY_FIXTURE_PATH.exists():
        raise DataLayerError(f"fixture missing: {QUERY_FIXTURE_PATH}")
    with QUERY_FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return QueryResult.model_validate(raw)


@app.post("/query", response_model=QueryResult)
def post_query(body: QueryRequest, response: Response) -> QueryResult:
    """Planner Console query endpoint.

    Routes through :func:`seahealth.agents.query.run_query` when real audit
    data is present (DELTA / PARQUET modes). In FIXTURE mode we serve the
    bundled ``demo_query_appendectomy.json`` so the demo always returns a
    populated ranked list. ``use_llm`` is enabled only when
    ``DATABRICKS_TOKEN`` is present; otherwise the deterministic heuristic
    path runs (no network calls).
    """
    mode = data_access.detect_mode()
    if mode is DataMode.FIXTURE:
        try:
            result = _query_fixture()
        except DataLayerError as exc:
            raise _data_503(exc) from exc
        result = result.model_copy(update={"query": body.query or result.query})
        response.headers["X-Query-Trace-Id"] = result.query_trace_id
        return result

    use_llm = bool(os.environ.get("DATABRICKS_TOKEN"))
    try:
        result = run_query(body.query, use_llm=use_llm)
    except Exception as exc:  # pragma: no cover - defensive; agent already swallows
        log.exception("run_query failed")
        raise HTTPException(
            status_code=503, detail=f"data unavailable: query agent failed ({exc})"
        ) from exc
    response.headers["X-Query-Trace-Id"] = result.query_trace_id
    return result


@app.get("/facilities/{facility_id}", response_model=FacilityAudit)
def get_facility(facility_id: str) -> FacilityAudit:
    """Facility Audit page payload."""
    try:
        audit = data_access.load_facility_audit(facility_id)
    except DataLayerError as exc:
        raise _data_503(exc) from exc
    if audit is None:
        raise HTTPException(
            status_code=404, detail=f"facility not found: {facility_id}"
        )
    return audit


@app.get("/map/aggregates", response_model=list[MapRegionAggregate])
def get_map_aggregates(
    capability_type: CapabilityType | None = None,
    radius_km: float | None = None,
) -> list[MapRegionAggregate]:
    """Desert Map choropleth payload."""
    try:
        rows = data_access.load_map_aggregates(
            capability_type=capability_type,
            radius_km=radius_km if radius_km is not None else data_access.DEFAULT_MAP_RADIUS_KM,
        )
    except DataLayerError as exc:
        raise _data_503(exc) from exc
    return rows


@app.get("/facilities", response_model=list[FacilityAudit])
def list_facilities(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=50,
            description="Maximum number of audits to return (1-50, default 50).",
        ),
    ] = 50,
) -> list[FacilityAudit]:
    """Faceted facility list. ``limit`` is validated to ``1 <= limit <= 50``."""
    try:
        return data_access.load_facilities(limit=limit)
    except DataLayerError as exc:
        raise _data_503(exc) from exc


__all__ = ["app"]
