"""Capability extractor agent.

Given the chunks for a single facility, runs ONE Anthropic call that emits a
structured ``ExtractedCapabilities`` payload. The agent is constrained to the
closed :class:`CapabilityType` enum, and every ``EvidenceRef`` snippet is
re-anchored against the source chunk so downstream UI can highlight the
exact span.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from pydantic import BaseModel

from seahealth.schemas import Capability, CapabilityType, EvidenceRef

from .anthropic_client import structured_call

# Default extractor model id. Tests pass an explicit override; production uses
# whatever the orchestrator wires in. Sonnet 4.6 is a reasonable, cheap default.
DEFAULT_EXTRACTOR_MODEL = "claude-sonnet-4-6"


_SYSTEM_PROMPT = """You are SeaHealth's capability extractor.

Given the chunks for ONE Indian healthcare facility, return the structured set
of capabilities the facility verifiably claims (or explicitly denies). Use ONLY
the closed enum of capability types provided in the schema. Do not invent
new capability names.

For every Capability you emit, attach one or more EvidenceRefs. Each
EvidenceRef MUST:

* quote the supporting snippet verbatim from one of the input chunks (snippet
  is the exact substring; it will be re-anchored downstream),
* set chunk_id to the chunk_id of that source chunk,
* set source_type to that chunk's source_type,
* leave span as [0, 0] — the host will overwrite it via string match.

If a chunk explicitly denies a capability (e.g., "no anesthesiologist"), emit
the Capability with claimed=false. If the evidence is silent on a capability,
do not emit it.

Be conservative. Prefer fewer, higher-evidence capabilities over speculation.
"""


class ExtractedCapabilities(BaseModel):
    """Container model for the extractor's structured output.

    The LLM is asked to emit instances of this type via tool-use; the
    extractor then post-processes each Capability to re-anchor evidence spans.
    """

    facility_id: str
    capabilities: list[Capability]


def _format_chunks_for_prompt(chunks: list[dict]) -> str:
    rendered = []
    for chunk in chunks:
        rendered.append(
            json.dumps(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "source_type": chunk.get("source_type"),
                    "text": chunk.get("text", ""),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(rendered)


def _build_chunk_index(chunks: Iterable[dict]) -> dict[str, dict]:
    return {str(chunk["chunk_id"]): chunk for chunk in chunks if "chunk_id" in chunk}


def _resolve_span(snippet: str, chunk_text: str) -> tuple[int, int]:
    if not snippet or not chunk_text:
        return (0, 0)
    idx = chunk_text.find(snippet)
    if idx < 0:
        return (0, 0)
    return (idx, idx + len(snippet))


def _normalize_capabilities(
    raw: ExtractedCapabilities,
    *,
    facility_id: str,
    chunk_index: dict[str, dict],
    extractor_model: str,
    extracted_at: datetime,
) -> ExtractedCapabilities:
    """Re-anchor evidence snippets and stamp metadata onto each capability."""
    cleaned: list[Capability] = []
    for cap in raw.capabilities:
        new_refs: list[EvidenceRef] = []
        for ref in cap.evidence_refs:
            chunk = chunk_index.get(ref.chunk_id, {})
            chunk_text = str(chunk.get("text", ""))
            chunk_source_doc = chunk.get("source_doc_id")
            span = _resolve_span(ref.snippet, chunk_text)
            new_refs.append(
                ref.model_copy(
                    update={
                        "facility_id": facility_id,
                        "span": span,
                        "source_doc_id": (
                            chunk_source_doc
                            if chunk_source_doc
                            else (ref.source_doc_id or f"vf::{ref.chunk_id}")
                        ),
                    }
                )
            )

        # Pick a primary source_doc_id for the Capability — prefer one of the
        # underlying chunks, else fall back to a vf:: synthetic id keyed off
        # the first evidence chunk_id (else the facility id).
        primary_source_doc: str | None = None
        if cap.source_doc_id:
            primary_source_doc = cap.source_doc_id
        if not primary_source_doc and new_refs:
            first_chunk = chunk_index.get(new_refs[0].chunk_id, {})
            primary_source_doc = (
                str(first_chunk.get("source_doc_id"))
                if first_chunk.get("source_doc_id")
                else f"vf::{new_refs[0].chunk_id}"
            )
        if not primary_source_doc:
            primary_source_doc = f"vf::{facility_id}"

        cleaned.append(
            cap.model_copy(
                update={
                    "facility_id": facility_id,
                    "evidence_refs": new_refs,
                    "source_doc_id": primary_source_doc,
                    "extracted_at": extracted_at,
                    "extractor_model": extractor_model,
                }
            )
        )

    return ExtractedCapabilities(facility_id=facility_id, capabilities=cleaned)


def extract_capabilities(
    facility_id: str,
    chunks: list[dict],
    *,
    model: str = DEFAULT_EXTRACTOR_MODEL,
    extractor_model_id: str = DEFAULT_EXTRACTOR_MODEL,
    client_factory: Callable[[], object] | None = None,
) -> ExtractedCapabilities:
    """Run a single LLM call summarizing all chunks for one facility.

    Args:
        facility_id: Stable VF facility id.
        chunks: Rows from ``tables/chunks.parquet`` for a single facility.
            Required keys: ``chunk_id``, ``source_type``, ``text``.
            Optional: ``source_doc_id`` (used to fill EvidenceRef.source_doc_id
            when the model omits it).
        model: Anthropic model id used in the API call.
        extractor_model_id: Model id stamped onto each Capability for
            provenance — kept separate so we can A/B against the API model.
        client_factory: Optional callable returning an Anthropic-compatible
            client. Used by tests to inject mocks.

    Returns:
        ExtractedCapabilities with re-anchored evidence spans.
    """
    if not chunks:
        return ExtractedCapabilities(facility_id=facility_id, capabilities=[])

    chunk_index = _build_chunk_index(chunks)
    user_prompt = (
        f"facility_id: {facility_id}\n"
        f"Allowed capability_type values: {[ct.value for ct in CapabilityType]}\n\n"
        "Chunks (one JSON object per line):\n"
        f"{_format_chunks_for_prompt(chunks)}\n"
    )

    client = client_factory() if client_factory is not None else None
    raw = structured_call(
        model=model,
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        response_model=ExtractedCapabilities,
        client=client,  # type: ignore[arg-type]
    )

    extracted_at = datetime.now(UTC)
    return _normalize_capabilities(
        raw,
        facility_id=facility_id,
        chunk_index=chunk_index,
        extractor_model=extractor_model_id,
        extracted_at=extracted_at,
    )
