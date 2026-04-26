"""FacilityAudit — canonical per-facility audit record consumed by every UI surface."""

from pydantic import BaseModel, Field

from ._datetime import AwareDatetime
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
    capabilities: list[Capability] = Field(default_factory=list)
    trust_scores: dict[CapabilityType, TrustScore] = Field(
        default_factory=dict,
        description="Keyed by CapabilityType for O(1) lookup from the UI.",
    )
    total_contradictions: int = Field(
        default=0,
        ge=0,
        description=(
            "Denormalized sum across trust_scores[*].contradictions; used for UI "
            "sort/filter."
        ),
    )
    last_audited_at: AwareDatetime
    mlflow_trace_id: str | None = Field(
        default=None,
        description=(
            "MLflow trace id linking to the agent run that produced this audit "
            "(transparency view)."
        ),
    )
