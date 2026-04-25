"""QueryResult — Planner Console output, plus ParsedIntent and RankedFacility."""
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from .capability_type import CapabilityType
from .geo import GeoPoint
from .trust_score import TrustScore


class ParsedIntent(BaseModel):
    """Structured query intent used by retrieval and ranking."""

    capability_type: CapabilityType
    location: GeoPoint
    radius_km: float = Field(
        ..., gt=0.0, description="Search radius around location in kilometers."
    )


class RankedFacility(BaseModel):
    """One row in a QueryResult — a facility that matches the parsed query, with the relevant capability's TrustScore."""

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
    """Planner Console output. Drives the demo query: e.g. 'Which facilities within 50km of Patna can perform an appendectomy?'"""

    query: str = Field(..., description="Natural-language query as the user asked it.")
    parsed_intent: ParsedIntent
    ranked_facilities: List[RankedFacility] = Field(default_factory=list)
    total_candidates: int = Field(
        ..., ge=0, description="Candidates considered before ranking/cutoff."
    )
    query_trace_id: str = Field(..., description="MLflow trace id for the planner run.")
    generated_at: datetime
