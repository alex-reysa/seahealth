"""Capability — a single claimed-or-denied capability for one facility, with evidence chain."""

from pydantic import BaseModel, Field

from ._datetime import AwareDatetime
from .capability_type import CapabilityType
from .evidence import EvidenceRef


class Capability(BaseModel):
    """A single claimed-or-denied capability for one facility, with evidence chain."""

    facility_id: str
    capability_type: CapabilityType
    claimed: bool = Field(
        ..., description="True if the source asserts the facility offers this capability."
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list, description="All evidence supporting the claim/denial."
    )
    source_doc_id: str = Field(..., description="Primary doc the claim was extracted from.")
    extracted_at: AwareDatetime
    extractor_model: str = Field(
        ...,
        description="Model id used for extraction (e.g. 'databricks-meta-llama-3-1-70b-instruct').",
    )
