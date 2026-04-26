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
    """Structured query intent used by retrieval and ranking."""

    capability_type: CapabilityType
    location: GeoPoint
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


class QueryResult(BaseModel):
    """Planner Console output for the appendectomy demo query."""

    query: str = Field(..., description="Natural-language query as the user asked it.")
    parsed_intent: ParsedIntent
    ranked_facilities: list[RankedFacility] = Field(default_factory=list)
    total_candidates: int = Field(
        ..., ge=0, description="Candidates considered before ranking/cutoff."
    )
    query_trace_id: str = Field(..., description="MLflow trace id for the planner run.")
    generated_at: AwareDatetime
