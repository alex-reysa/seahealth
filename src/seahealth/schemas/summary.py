"""SummaryMetrics — UI summary tile aggregates.

Definitions:
    - audited_count        : total facilities (or facility/capability rows when capability_type
                             is set) that have a FacilityAudit.
    - verified_count       : audited rows whose TrustScore.score >= 80 AND that carry NO
                             HIGH-severity contradiction.
    - flagged_count        : audited rows where total_contradictions > 0 (any severity).
    - last_audited_at      : max(FacilityAudit.last_audited_at) across the set.
    - capability_type      : optional filter; when set, all counts are restricted to that
                             capability. When None, the metrics are global.
    - verified_count_ci    : optional 95% Wilson CI on verified_count (Phase 4B).
"""

from pydantic import BaseModel, Field

from ._datetime import AwareDatetime
from .capability_type import CapabilityType


class SummaryMetrics(BaseModel):
    """High-level audit tallies for the home/summary tile.

    Verified = TrustScore.score >= 80 AND no HIGH-severity contradiction.
    Flagged  = total_contradictions > 0.
    """

    audited_count: int = Field(
        ...,
        ge=0,
        description="Total audited facilities (or rows when capability_type is set).",
    )
    verified_count: int = Field(
        ...,
        ge=0,
        description="Count where TrustScore.score >= 80 AND no HIGH-severity contradiction.",
    )
    flagged_count: int = Field(
        ..., ge=0, description="Count where total_contradictions > 0."
    )
    last_audited_at: AwareDatetime = Field(
        ..., description="Most recent FacilityAudit.last_audited_at across the aggregate."
    )
    capability_type: CapabilityType | None = Field(
        default=None,
        description="When set, all counts are restricted to this capability; otherwise global.",
    )
    verified_count_ci: tuple[int, int] | None = Field(
        default=None,
        description=(
            "Optional 95% Wilson CI on verified_count, scaled back to integer counts in "
            "[0, audited_count]. None when audited_count is 0 or the caller asked for "
            "a point estimate."
        ),
    )
