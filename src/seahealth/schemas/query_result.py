"""QueryResult — Planner Console output, plus ParsedIntent and RankedFacility."""

from typing import Literal

from pydantic import BaseModel, Field

from ._datetime import AwareDatetime
from .capability_type import CapabilityType
from .geo import GeoPoint
from .trust_score import TrustScore

# Closed taxonomy for the optional third query qualifier. Brief example:
#   "...typically leverages parttime doctors."
# Stays Literal so the heuristic parser, the LLM tool-loop, and any downstream
# consumer all agree on a finite set. Any future addition must land here AND
# in DATA_CONTRACT.md.
StaffingQualifier = Literal["parttime", "fulltime", "twentyfour_seven", "low_volume"]


class ParsedIntent(BaseModel):
    """Structured query intent used by retrieval and ranking.

    ``capability_type`` and ``location`` are optional so the relaxed query
    path can return partial intents (capability-only or location-only
    searches). Backward-compatible: callers that always supply both keep
    working unchanged.
    """

    capability_type: CapabilityType | None = Field(
        default=None,
        description=(
            "Detected capability. ``None`` means a location-only or fully "
            "ambiguous query — relaxed search semantics apply."
        ),
    )
    location: GeoPoint | None = Field(
        default=None,
        description=(
            "Detected query origin. ``None`` means a capability-only or "
            "fully ambiguous query — relaxed national-scale search applies."
        ),
    )
    radius_km: float = Field(
        ..., gt=0.0, description="Search radius around location in kilometers."
    )
    # Optional third qualifier (e.g. "parttime doctors", "24/7"). When present
    # we apply a small soft re-rank on retrieval — never a hard filter, so
    # facilities with missing staffing data are still returned (just unboosted).
    staffing_qualifier: StaffingQualifier | None = Field(
        default=None,
        description=(
            "Optional staffing pattern qualifier extracted from the natural-"
            "language query. Used as a soft tiebreaker on ranking; missing "
            "facility staffing data never drops a candidate."
        ),
    )


class RankedFacility(BaseModel):
    """One row in a QueryResult with the relevant capability's TrustScore."""

    facility_id: str
    name: str
    location: GeoPoint
    distance_km: float = Field(..., ge=0.0, description="Great-circle distance from query origin.")
    trust_score: TrustScore = Field(
        ..., description="TrustScore for the capability the query asked about."
    )
    contradictions_flagged: int = Field(..., ge=0)
    evidence_count: int = Field(..., ge=0)
    rank: int = Field(..., ge=1, description="1-indexed rank in the result list.")


# Closed taxonomy for execution-step status. ``ok`` covers the happy path,
# ``fallback`` records that the heuristic / synthetic substitution kicked in
# for that step, and ``error`` is reserved for unrecoverable failures.
ExecutionStepStatus = Literal["ok", "fallback", "error"]


# Closed taxonomy for the active retriever during a query run. ``vector_search``
# is the Mosaic AI Vector Search path; ``faiss_local`` is the local FAISS /
# BM25 fallback; ``fixture`` means the FIXTURE-mode bundled response was used.
RetrieverMode = Literal["vector_search", "faiss_local", "fixture"]


class ExecutionStep(BaseModel):
    """One step in the planner agent timeline.

    The agent always emits a fixed set of step ``name`` values
    (``parse_intent``, ``retrieve``, ``score``, ``rank``) so the UI can render
    a stable timeline. ``status='fallback'`` distinguishes the heuristic
    path from a real LLM-driven step at the same name.
    """

    name: str = Field(..., description="Stable step identifier (parse_intent, retrieve, score, rank).")
    started_at: AwareDatetime
    finished_at: AwareDatetime
    status: ExecutionStepStatus = Field(..., description="ok | fallback | error.")
    detail: str | None = Field(default=None, description="Optional human-readable detail line.")


class QueryResult(BaseModel):
    """Planner Console output for the appendectomy demo query."""

    query: str = Field(..., description="Natural-language query as the user asked it.")
    parsed_intent: ParsedIntent
    ranked_facilities: list[RankedFacility] = Field(default_factory=list)
    total_candidates: int = Field(
        ..., ge=0, description="Candidates considered before ranking/cutoff."
    )
    # Always-present synthetic correlation id — `q_<uuid>` for live runs, used
    # in logs, telemetry, and the X-Query-Trace-Id response header. NOT an
    # MLflow trace id; that lives on ``mlflow_trace_id`` and is only set when
    # MLFLOW_TRACKING_URI is configured.
    query_trace_id: str = Field(
        ...,
        description=(
            "Correlation id for this planner run. Always present. Format "
            "``q_<uuid>`` for offline / synthetic runs; reused in the "
            "X-Query-Trace-Id response header."
        ),
    )
    mlflow_trace_id: str | None = Field(
        default=None,
        description=(
            "Real MLflow trace id when the run executed under "
            "MLFLOW_TRACKING_URI; otherwise null."
        ),
    )
    mlflow_trace_url: str | None = Field(
        default=None,
        description=(
            "Optional deep-link to the MLflow trace UI. Only populated when "
            "MLFLOW_HOST is set alongside MLFLOW_TRACKING_URI."
        ),
    )
    execution_steps: list[ExecutionStep] = Field(
        default_factory=list,
        description=(
            "Timeline of agent steps (parse_intent, retrieve, score, rank). "
            "Always four entries on success; fewer only when an early "
            "step errored."
        ),
    )
    retriever_mode: RetrieverMode = Field(
        default="faiss_local",
        description="Which retriever the run used (vector_search | faiss_local | fixture).",
    )
    used_llm: bool = Field(
        default=False,
        description="True when the LLM tool-loop ran; False when the heuristic path ran.",
    )
    generated_at: AwareDatetime
