"""Stable id formula for joining EvidenceAssessment to EvidenceRef.

The id is `f"{source_doc_id}:{chunk_id}"`. Centralized so all agents agree.
"""

from __future__ import annotations

from .evidence import EvidenceRef


def evidence_ref_id(ref: EvidenceRef) -> str:
    """Stable id for an EvidenceRef. Use this in EvidenceAssessment.evidence_ref_id."""
    return f"{ref.source_doc_id}:{ref.chunk_id}"
