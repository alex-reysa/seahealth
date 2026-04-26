"""Desert Map UI schemas — region-level rollups + population reference.

This Phase-1 shape is the slim variant the UI consumes. The richer DATA_CONTRACT
desert-map shape (with explicit coverage_ratio / capability_count_ci) is preserved
for downstream Delta rollups; the UI layer reads MapRegionAggregate as defined here.
"""
from pydantic import BaseModel, Field

from .capability_type import CapabilityType
from .geo import GeoPoint


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
            "(uncovered population)."
        ),
    )
    centroid: GeoPoint = Field(..., description="Geographic centroid of the region.")
