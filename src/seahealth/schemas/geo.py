"""GeoPoint — geographic point used for facility location and radius queries."""
from typing import Optional

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    """A geographic point with optional Indian PIN code; used for facility location and radius queries."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees.")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees.")
    pin_code: Optional[str] = Field(
        default=None,
        pattern=r"^\d{6}$",
        description="Indian Postal Index Number, exactly 6 digits.",
    )
