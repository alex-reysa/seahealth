"""IndexedDoc — one chunk in the vector index. Embedding dim locked to 1024."""

from pydantic import BaseModel, Field

from ._datetime import AwareDatetime
from .evidence import SourceType

# BAAI/bge-large-en-v1.5 — locked for the demo. See DECISIONS.md if changed.
EMBEDDING_DIM: int = 1024


class IndexedDoc(BaseModel):
    """One chunk in the vector index. Embedding dim is fixed at 1024 for BAAI/bge-large-en-v1.5."""

    doc_id: str
    facility_id: str | None = None
    text: str = Field(..., description="The chunk text as embedded.")
    embedding: list[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    chunk_index: int = Field(
        ..., ge=0, description="Position of this chunk within its parent document."
    )
    source_type: SourceType
    source_observed_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the source content was published, observed, or last updated; "
            "used for STALE_DATA."
        ),
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Free-form string metadata (region, doc_date, etc.).",
    )
