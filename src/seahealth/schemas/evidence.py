"""EvidenceRef — citation shape pointing into a source document chunk."""
from datetime import datetime
from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field

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
    row_id: Optional[str] = Field(
        default=None,
        description="Row id when source is tabular (staff/equipment/volume).",
    )
    span: Tuple[int, int] = Field(
        ..., description="(start, end) char offsets within the chunk text."
    )
    snippet: str = Field(..., description="The highlighted sentence rendered in the citation chip.")
    source_type: SourceType = Field(..., description="Provenance class for downstream weighting.")
    source_observed_at: Optional[datetime] = Field(
        default=None,
        description="When the source content was published, observed, or last updated; used for STALE_DATA.",
    )
    retrieved_at: datetime = Field(
        ..., description="When the retrieval/extraction step pulled this evidence."
    )
