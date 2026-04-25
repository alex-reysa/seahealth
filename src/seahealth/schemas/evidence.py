"""EvidenceRef — citation shape pointing into a source document chunk."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ._datetime import AwareDatetime

SourceType = Literal[
    "facility_note",
    "staff_roster",
    "equipment_inventory",
    "volume_report",
    "external",
]

EvidenceStance = Literal["verifies", "contradicts", "silent"]


class EvidenceRef(BaseModel):
    """A pointer to the exact span in a source document that supports or refutes a claim.

    Every UI citation chip resolves through this object.
    """

    source_doc_id: str = Field(..., description="Stable id of the originating document.")
    facility_id: str = Field(..., description="Facility this evidence is attached to.")
    chunk_id: str = Field(..., description="Id of the chunk within the indexed doc.")
    row_id: str | None = Field(
        default=None,
        description="Row id when source is tabular (staff/equipment/volume).",
    )
    span: tuple[int, int] = Field(
        ..., description="(start, end) char offsets within the chunk text."
    )
    snippet: str = Field(..., description="The highlighted sentence rendered in the citation chip.")
    source_type: SourceType = Field(..., description="Provenance class for downstream weighting.")
    source_observed_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the source content was published, observed, or last updated; "
            "used for STALE_DATA."
        ),
    )
    retrieved_at: AwareDatetime = Field(
        ..., description="When the retrieval/extraction step pulled this evidence."
    )

    @field_validator("span")
    @classmethod
    def _validate_span(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if start < 0 or end < 0:
            raise ValueError("span offsets must be >= 0")
        if start > end:
            raise ValueError("span start must be <= end")
        return value
