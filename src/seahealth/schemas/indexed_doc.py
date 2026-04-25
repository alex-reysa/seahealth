"""IndexedDoc — one chunk in the vector index. Embedding dim locked to 1024."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .evidence import SourceType

EMBEDDING_DIM: int = 1024  # BAAI/bge-large-en-v1.5 — locked for the demo. See DECISIONS.md if changed.


class IndexedDoc(BaseModel):
    """One chunk in the vector index. Embedding dim is fixed at 1024 for BAAI/bge-large-en-v1.5."""

    doc_id: str
    facility_id: Optional[str] = None
    text: str = Field(..., description="The chunk text as embedded.")
    embedding: List[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    chunk_index: int = Field(
        ..., ge=0, description="Position of this chunk within its parent document."
    )
    source_type: SourceType
    source_observed_at: Optional[datetime] = Field(
        default=None,
        description="When the source content was published, observed, or last updated; used for STALE_DATA.",
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Free-form string metadata (region, doc_date, etc.).",
    )
