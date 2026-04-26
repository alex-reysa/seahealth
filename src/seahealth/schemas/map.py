"""Desert Map UI schemas — region-level rollups + population reference.

This Phase-1 shape is the slim variant the UI consumes. The richer DATA_CONTRACT
desert-map shape (with explicit coverage_ratio / capability_count_ci) is preserved
for downstream Delta rollups; the UI layer reads MapRegionAggregate as defined here.
"""
from typing import Literal

from pydantic import BaseModel, Field

from .capability_type import CapabilityType
from .geo import GeoPoint

# Honest provenance for the population denominator. ``delta`` means the field
# came from the gold ``map_aggregates`` table; ``fixture`` means a bundled
# census snapshot; ``unavailable`` means the underlying source has no
# denominator and the UI MUST NOT show a percent-of-population claim.
PopulationSource = Literal["delta", "fixture", "unavailable"]


class PopulationReference(BaseModel):
    """Population denominator for one map region (UI variant)."""

    region_id: str = Field(..., description="Stable region identifier (e.g. district code).")
    population_total: int = Field(
        ..., ge=0, description="Total population in the region."
    )


class MapRegionAggregate(BaseModel):
    """Desert Map rollup for one region and capability, sized for the UI map layer."""

    region_id: str = Field(..., description="Stable region identifier (e.g. district code).")
    region_name: str = Field(..., description="Human-readable region name.")
    state: str = Field(..., description="State or province the region belongs to.")
    capability_type: CapabilityType
    population: int = Field(..., ge=0, description="Total population in the region.")
    verified_facilities_count: int = Field(
        ..., ge=0, description="Facilities with verified coverage for this capability."
    )
    flagged_facilities_count: int = Field(
        ..., ge=0, description="Facilities flagged with at least one contradiction."
    )
    gap_population: int = Field(
        ...,
        ge=0,
        description=(
            "Population minus a coverage estimate for this capability "
            "(uncovered population). Only meaningful when "
            "``population_source != 'unavailable'``."
        ),
    )
    centroid: GeoPoint = Field(..., description="Geographic centroid of the region.")
    population_source: PopulationSource = Field(
        default="unavailable",
        description=(
            "Provenance of the population denominator. ``delta`` = backed by "
            "the gold table; ``fixture`` = bundled census snapshot; "
            "``unavailable`` = no denominator. The UI MUST NOT compute "
            "percent-of-population when this is ``unavailable``."
        ),
    )
