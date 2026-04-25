"""Query Agent — turns a natural-language planner question into a QueryResult.

Two execution modes:

1. **Heuristic** (``use_llm=False`` or no LLM client available):
   regex / keyword parser over a closed map of capability synonyms plus the
   static India city geocoder. This is the deterministic path tests rely on
   and the fallback when ``DATABRICKS_TOKEN`` is missing.

2. **LLM tool-loop** (``use_llm=True``): the Databricks Foundation Model is
   given three tools — ``geocode``, ``search_facilities``,
   ``get_facility_audit`` — plus a final ``emit_QueryPlan`` tool that the
   agent must invoke once it has chosen the candidates. The loop is bounded
   by ``max_steps`` and ``retries``; on any failure we fall back to the
   heuristic path so the demo never hard-stops mid-query.

Both paths emit the same ``QueryResult`` shape.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from seahealth.schemas import (
    CapabilityType,
    GeoPoint,
    ParsedIntent,
    QueryResult,
    RankedFacility,
    TrustScore,
)

from .geocode import geocode
from .llm_client import DEFAULT_HEAVY_MODEL
from .tools import (
    tool_geocode,
    tool_get_facility_audit,
    tool_search_facilities,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_HEAVY_MODEL
DEFAULT_RADIUS_KM = 50.0
MAX_RANKED_FACILITIES = 20

# Map a few common natural-language hooks onto closed CapabilityType members.
# Order matters: SURGERY_APPENDECTOMY needs to win over SURGERY_GENERAL when a
# query contains "appendectomy".
_CAPABILITY_KEYWORDS: list[tuple[str, CapabilityType]] = [
    ("appendicitis", CapabilityType.SURGERY_APPENDECTOMY),
    ("appendectomy", CapabilityType.SURGERY_APPENDECTOMY),
    ("appendix surgery", CapabilityType.SURGERY_APPENDECTOMY),
    ("appendix removal", CapabilityType.SURGERY_APPENDECTOMY),
    ("appendix", CapabilityType.SURGERY_APPENDECTOMY),
    ("dialysis", CapabilityType.DIALYSIS),
    ("oncology", CapabilityType.ONCOLOGY),
    ("cancer", CapabilityType.ONCOLOGY),
    ("neonatal", CapabilityType.NEONATAL),
    ("nicu", CapabilityType.NEONATAL),
    ("trauma", CapabilityType.TRAUMA),
    ("emergency", CapabilityType.EMERGENCY_24_7),
    ("icu", CapabilityType.ICU),
    ("intensive care", CapabilityType.ICU),
    ("surgery", CapabilityType.SURGERY_GENERAL),
    ("operation", CapabilityType.SURGERY_GENERAL),
    ("abdominal procedure", CapabilityType.SURGERY_GENERAL),
    ("abdominal surgery", CapabilityType.SURGERY_GENERAL),
]

_RADIUS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:km|kilometre|kilometer)s?\b", re.IGNORECASE)
_NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}
_WORD_RADIUS_RE = re.compile(
    r"\b("
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred"
    r")\s*(?:km|kilometre|kilometer)s?\b",
    re.IGNORECASE,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_trace_id() -> str:
    return f"q_{uuid.uuid4().hex}"


def _detect_capability(query: str) -> CapabilityType | None:
    lowered = query.lower()
    for keyword, cap_type in _CAPABILITY_KEYWORDS:
        if keyword in lowered:
            return cap_type
    return None


def _detect_radius(query: str) -> float:
    match = _RADIUS_RE.search(query)
    if match:
        try:
            value = float(match.group(1))
        except ValueError:
            return DEFAULT_RADIUS_KM
        return value if value > 0 else DEFAULT_RADIUS_KM

    word_match = _WORD_RADIUS_RE.search(query)
    if not word_match:
        return DEFAULT_RADIUS_KM
    value = _number_word_to_float(word_match.group(1))
    if value is None:
        return DEFAULT_RADIUS_KM
    return value if value > 0 else DEFAULT_RADIUS_KM


def _number_word_to_float(raw: str) -> float | None:
    normalized = raw.lower().replace("-", " ").strip()
    parts = normalized.split()
    if not parts:
        return None
    total = 0
    for part in parts:
        value = _NUMBER_WORDS.get(part)
        if value is None:
            return None
        total += value
    return float(total)


def _detect_location(query: str) -> GeoPoint | None:
    """Look up a known Indian city referenced in the query."""
    return geocode(query)


def _empty_intent() -> ParsedIntent:
    """Sentinel intent used when nothing parses — shape-safe for the API stub."""
    return ParsedIntent(
        capability_type=CapabilityType.SURGERY_GENERAL,
        location=GeoPoint(lat=0.0, lng=0.0),
        radius_km=DEFAULT_RADIUS_KM,
    )


def _trust_score_from_audit(
    audit: dict[str, Any], capability_type: CapabilityType
) -> TrustScore | None:
    """Extract a TrustScore for ``capability_type`` from a FacilityAudit dict."""
    if not audit:
        return None
    raw_scores = audit.get("trust_scores") or {}
    if not isinstance(raw_scores, dict):
        return None
    raw = raw_scores.get(capability_type.value) or raw_scores.get(capability_type)
    if not isinstance(raw, dict):
        return None
    try:
        return TrustScore.model_validate(raw)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to coerce TrustScore for %s: %s", capability_type, exc)
        return None


def _build_ranked(
    candidates: list[dict[str, Any]],
    parsed: ParsedIntent,
    *,
    audits_path: str | None,
) -> list[RankedFacility]:
    """Materialize RankedFacility rows by joining search hits with audit details."""
    ranked: list[RankedFacility] = []
    for hit in candidates[:MAX_RANKED_FACILITIES]:
        facility_id = hit.get("facility_id")
        if not facility_id:
            continue
        audit = tool_get_facility_audit(facility_id, audits_path=audits_path)
        if not audit:
            continue
        trust = _trust_score_from_audit(audit, parsed.capability_type)
        if trust is None:
            continue
        location = audit.get("location")
        if isinstance(location, dict):
            try:
                point = GeoPoint(
                    lat=float(location["lat"]),
                    lng=float(location["lng"]),
                    pin_code=location.get("pin_code"),
                )
            except (KeyError, TypeError, ValueError):
                continue
        elif isinstance(location, GeoPoint):
            point = location
        else:
            continue
        ranked.append(
            RankedFacility(
                facility_id=str(facility_id),
                name=str(audit.get("name") or facility_id),
                location=point,
                distance_km=float(hit.get("distance_km", 0.0)),
                trust_score=trust,
                contradictions_flagged=int(hit.get("contradictions_flagged", 0)),
                evidence_count=int(hit.get("evidence_count", 0)),
                rank=1,
            )
        )
    ranked.sort(key=lambda item: (-item.trust_score.score, item.distance_km))
    for idx, item in enumerate(ranked, start=1):
        item.rank = idx
    return ranked


# ---------------------------------------------------------------------------
# Heuristic path
# ---------------------------------------------------------------------------


def _run_heuristic(query: str, *, audits_path: str | None) -> QueryResult:
    capability = _detect_capability(query)
    location = _detect_location(query)
    radius = _detect_radius(query)
    trace_id = _new_trace_id()
    now = _utcnow()

    if capability is None or location is None:
        # We can still emit a shape-correct empty result so callers (e.g. the
        # API stub) don't crash on unknown queries.
        return QueryResult(
            query=query,
            parsed_intent=ParsedIntent(
                capability_type=capability or CapabilityType.SURGERY_GENERAL,
                location=location or GeoPoint(lat=0.0, lng=0.0),
                radius_km=radius,
            ),
            ranked_facilities=[],
            total_candidates=0,
            query_trace_id=trace_id,
            generated_at=now,
        )

    parsed = ParsedIntent(capability_type=capability, location=location, radius_km=radius)
    candidates = tool_search_facilities(
        capability.value,
        location.lat,
        location.lng,
        radius,
        audits_path=audits_path,
    )
    ranked = _build_ranked(candidates, parsed, audits_path=audits_path)
    return QueryResult(
        query=query,
        parsed_intent=parsed,
        ranked_facilities=ranked,
        total_candidates=len(candidates),
        query_trace_id=trace_id,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# LLM tool-use path
# ---------------------------------------------------------------------------


class _QueryPlan(BaseModel):
    """Final structured payload the LLM emits after its tool calls.

    ``selected_facility_ids`` is the ranked list (best first) the agent
    chose; we re-join against the search hits/audit table to materialize the
    full ``RankedFacility`` rows. Anything the model recommends that we
    don't have an audit for is silently skipped.
    """

    capability_type: CapabilityType
    location: GeoPoint
    radius_km: float = Field(default=DEFAULT_RADIUS_KM, gt=0.0)
    selected_facility_ids: list[str] = Field(default_factory=list)


_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "geocode",
        "description": "Resolve an Indian city name to a GeoPoint with lat/lng/pin_code.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_facilities",
        "description": (
            "Find facilities within radius_km of (lat, lng) that have a "
            "TrustScore for the given CapabilityType."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability_type": {"type": "string"},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "radius_km": {"type": "number"},
            },
            "required": ["capability_type", "lat", "lng", "radius_km"],
        },
    },
    {
        "name": "get_facility_audit",
        "description": "Fetch a full FacilityAudit by id.",
        "input_schema": {
            "type": "object",
            "properties": {"facility_id": {"type": "string"}},
            "required": ["facility_id"],
        },
    },
    {
        "name": "emit_QueryPlan",
        "description": (
            "Emit the final QueryPlan once enough facility evidence has been "
            "gathered. Call this exactly once at the end."
        ),
        "input_schema": _QueryPlan.model_json_schema(),
    },
]


_SYSTEM_PROMPT = """You are SeaHealth's Planner Console query agent.

Given a natural-language question, you must:

1. Use ``geocode`` to resolve the location.
2. Use ``search_facilities`` to find candidate facilities for the requested
   capability within the requested radius (default 50 km).
3. Optionally call ``get_facility_audit`` for the most promising candidates.
4. Finish by calling ``emit_QueryPlan`` exactly once with the chosen
   capability_type, location, radius_km, and a ranked list of facility ids.

Use ONLY the closed CapabilityType enum. Do not invent facility ids — only
return ids that ``search_facilities`` returned.
"""


def _block_field(block: Any, field: str) -> Any:
    value = getattr(block, field, None)
    if value is None and isinstance(block, dict):
        value = block.get(field)
    return value


def _iter_tool_calls(message: Any) -> list[dict[str, Any]]:
    blocks = _block_field(message, "content") or []
    calls: list[dict[str, Any]] = []
    for block in blocks:
        if _block_field(block, "type") != "tool_use":
            continue
        calls.append(
            {
                "id": _block_field(block, "id"),
                "name": _block_field(block, "name"),
                "input": _block_field(block, "input") or {},
            }
        )
    return calls


def _execute_tool_call(name: str, arguments: dict[str, Any], *, audits_path: str | None) -> Any:
    if name == "geocode":
        return tool_geocode(str(arguments.get("query", "")))
    if name == "search_facilities":
        return tool_search_facilities(
            capability_type=str(arguments.get("capability_type", "")),
            lat=float(arguments.get("lat", 0.0)),
            lng=float(arguments.get("lng", 0.0)),
            radius_km=float(arguments.get("radius_km", DEFAULT_RADIUS_KM)),
            audits_path=audits_path,
        )
    if name == "get_facility_audit":
        return tool_get_facility_audit(
            str(arguments.get("facility_id", "")), audits_path=audits_path
        )
    return {"error": f"unknown_tool:{name}"}


def _try_import_structured_call() -> Any | None:
    try:
        from seahealth.agents import llm_client  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised in tests
        log.warning("llm_client unavailable; falling back to heuristics: %s", exc)
        return None
    return llm_client


def _run_llm(
    query: str,
    *,
    model: str,
    max_steps: int,
    retries: int,
    audits_path: str | None,
    client_factory: Callable[..., Any] | None,
) -> QueryResult | None:
    """Run the bounded tool-use loop. Returns None on failure (caller should
    fall back to the heuristic path)."""
    module = _try_import_structured_call()
    if module is None:
        return None
    structured_call = getattr(module, "structured_call", None)
    if structured_call is None:
        return None

    client = None
    if client_factory is not None:
        try:
            client = client_factory()
        except Exception as exc:
            log.warning("client_factory raised; falling back to heuristics: %s", exc)
            return None

    plan: _QueryPlan | None = None
    last_search: list[dict[str, Any]] = []
    transcript: list[str] = [f"User asked: {query}"]

    for _ in range(max_steps):
        prompt = "\n\n".join(transcript)
        try:
            response = structured_call(
                model=model,
                system=_SYSTEM_PROMPT,
                user=prompt,
                response_model=_QueryPlan,
                tools=_TOOL_DEFS,
                retries=retries,
                client=client,
            )
        except TypeError:
            # Older structured_call signatures don't accept tools/retries.
            try:
                response = structured_call(
                    model=model,
                    system=_SYSTEM_PROMPT,
                    user=prompt,
                    response_model=_QueryPlan,
                    client=client,
                )
            except Exception as exc:
                log.warning("structured_call failed: %s", exc)
                return None
        except Exception as exc:
            log.warning("structured_call failed: %s", exc)
            return None

        # If the helper directly returned a _QueryPlan, we are done.
        if isinstance(response, _QueryPlan):
            plan = response
            break

        # Otherwise treat the response as a raw Chat Completion message and
        # walk through any tool_call blocks before looping again.
        tool_calls = _iter_tool_calls(response)
        if not tool_calls:
            log.warning("LLM returned no tool calls and no plan; aborting.")
            return None
        for call in tool_calls:
            tool_name = call.get("name") or ""
            args = call.get("input") or {}
            if tool_name == "emit_QueryPlan":
                try:
                    plan = _QueryPlan.model_validate(args)
                except Exception as exc:
                    log.warning("emit_QueryPlan payload invalid: %s", exc)
                    return None
                break
            result = _execute_tool_call(tool_name, args, audits_path=audits_path)
            if tool_name == "search_facilities" and isinstance(result, list):
                last_search = result
            transcript.append(f"tool {tool_name} -> {result}")
        if plan is not None:
            break

    if plan is None:
        return None

    parsed = ParsedIntent(
        capability_type=plan.capability_type,
        location=plan.location,
        radius_km=plan.radius_km,
    )

    # Re-run the search authoritatively so distance/score numbers reflect the
    # parquet table even if the model invented them.
    candidates = (
        tool_search_facilities(
            parsed.capability_type.value,
            parsed.location.lat,
            parsed.location.lng,
            parsed.radius_km,
            audits_path=audits_path,
        )
        or last_search
    )

    if plan.selected_facility_ids:
        ordered = []
        seen = set()
        by_id = {c.get("facility_id"): c for c in candidates}
        for fid in plan.selected_facility_ids:
            hit = by_id.get(fid)
            if hit and fid not in seen:
                ordered.append(hit)
                seen.add(fid)
        for hit in candidates:
            fid = hit.get("facility_id")
            if fid and fid not in seen:
                ordered.append(hit)
                seen.add(fid)
        candidates = ordered

    ranked = _build_ranked(candidates, parsed, audits_path=audits_path)
    return QueryResult(
        query=query,
        parsed_intent=parsed,
        ranked_facilities=ranked,
        total_candidates=len(candidates),
        query_trace_id=_new_trace_id(),
        generated_at=_utcnow(),
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_query(
    query: str,
    *,
    model: str = DEFAULT_MODEL,
    max_steps: int = 6,
    retries: int = 1,
    use_llm: bool = True,
    client_factory: Callable[..., Any] | None = None,
    audits_path: str | None = None,
) -> QueryResult:
    """Resolve a natural-language facility query into a ``QueryResult``.

    See module docstring for the heuristic vs. LLM tool-loop split.
    """
    # MLflow span is best-effort — never fatal.
    if os.environ.get("MLFLOW_TRACKING_URI"):
        try:
            import mlflow  # type: ignore

            with mlflow.start_span(name="seahealth.query"):
                pass
        except Exception:
            pass

    if use_llm:
        result = _run_llm(
            query,
            model=model,
            max_steps=max_steps,
            retries=retries,
            audits_path=audits_path,
            client_factory=client_factory,
        )
        if result is not None:
            return result
        log.info("LLM path unavailable or failed; falling back to heuristics.")

    return _run_heuristic(query, audits_path=audits_path)


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_RADIUS_KM",
    "MAX_RANKED_FACILITIES",
    "run_query",
]
