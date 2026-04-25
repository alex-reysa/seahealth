"""Capability — a single claimed-or-denied capability for one facility, with evidence chain."""
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from .capability_type import CapabilityType
from .evidence import EvidenceRef


class Capability(BaseModel):
    """A single claimed-or-denied capability for one facility, with its supporting evidence chain."""

    facility_id: str
    capability_type: CapabilityType
    claimed: bool = Field(
        ..., description="True if the source asserts the facility offers this capability."
    )
    evidence_refs: List[EvidenceRef] = Field(
        default_factory=list, description="All evidence supporting the claim/denial."
    )
    source_doc_id: str = Field(..., description="Primary doc the claim was extracted from.")
    extracted_at: datetime
    extractor_model: str = Field(
        ...,
        description="Model id used for extraction (e.g. 'databricks-meta-llama-3-1-70b-instruct').",
    )
