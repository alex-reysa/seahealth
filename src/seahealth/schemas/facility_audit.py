"""FacilityAudit — canonical per-facility audit record consumed by every UI surface."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .capability import Capability
from .capability_type import CapabilityType
from .geo import GeoPoint
from .trust_score import TrustScore


class FacilityAudit(BaseModel):
    """Canonical per-facility audit record.

    The Planner Console, Facility Card, Trust Score drawer, and contradiction list
    all read from this shape.
    """

    facility_id: str
    name: str
    location: GeoPoint
    capabilities: List[Capability] = Field(default_factory=list)
    trust_scores: Dict[CapabilityType, TrustScore] = Field(
        default_factory=dict,
        description="Keyed by CapabilityType for O(1) lookup from the UI.",
    )
    total_contradictions: int = Field(
        default=0,
        ge=0,
        description="Denormalized sum across trust_scores[*].contradictions; used for UI sort/filter.",
    )
    last_audited_at: datetime
    mlflow_trace_id: Optional[str] = Field(
        default=None,
        description="MLflow trace id linking to the agent run that produced this audit (transparency view).",
    )
