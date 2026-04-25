"""Validator agent — combines deterministic heuristics with an optional LLM pass.

Public entrypoint:

    validate_capability(cap, facts, retrieved_evidence=None, *, use_llm=True, ...)

Returns ``(contradictions, evidence_assessments)``.  The heuristics path runs
unconditionally and is the source of truth for the bulk of demo-time
contradictions.  The LLM path is best-effort: it adds reasoning to any heuristic
contradictions that are missing it, may add additional CONFLICTING_SOURCES /
VOLUME_MISMATCH / TEMPORAL_UNVERIFIED contradictions, and produces an
``EvidenceAssessment`` per retrieved evidence item.

If the Anthropic client cannot be imported (e.g. in CI without
``ANTHROPIC_API_KEY``) the LLM step is skipped with a warning and the heuristic
result is returned unchanged.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from seahealth.schemas import (
    Capability,
    Contradiction,
    ContradictionType,
    EvidenceAssessment,
    EvidenceRef,
)

from .heuristics import FacilityFacts, run_all_heuristics

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
VALIDATOR_ID = "validator.v1"

# Contradiction types the LLM is permitted to add on top of the heuristic set.
_LLM_ADDITIONAL_TYPES = {
    ContradictionType.VOLUME_MISMATCH,
    ContradictionType.TEMPORAL_UNVERIFIED,
    ContradictionType.CONFLICTING_SOURCES,
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _try_import_client() -> Any | None:
    """Best-effort import of the shared Anthropic structured-output helper.

    Returns the module if importable, else None.  We avoid raising so the
    validator stays useful in test/CI environments without the SDK key.
    """
    try:
        from seahealth.agents import anthropic_client  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised via mock in tests
        log.warning("anthropic_client unavailable; skipping LLM pass: %s", exc)
        return None
    return anthropic_client


def _build_llm_prompt(
    cap: Capability,
    facts: FacilityFacts,
    retrieved_evidence: list[EvidenceRef],
    heuristic_contradictions: list[Contradiction],
) -> str:
    """Assemble a compact prompt describing the claim, facts, and evidence."""
    snippets = "\n".join(
        f"- [{i}] ({ev.source_type}) {ev.snippet}" for i, ev in enumerate(retrieved_evidence)
    ) or "(none)"
    h_lines = "\n".join(
        f"- {c.contradiction_type.value} ({c.severity}): {c.reasoning}"
        for c in heuristic_contradictions
    ) or "(none)"
    return (
        f"Capability claim: {cap.capability_type.value} = {cap.claimed} "
        f"at facility {cap.facility_id}.\n"
        f"Facts: equipment={facts.equipment}, staff_count={facts.staff_count}, "
        f"capacity_beds={facts.capacity_beds}, "
        f"recency_months={facts.recency_of_page_update_months}.\n"
        f"Heuristic contradictions:\n{h_lines}\n"
        f"Retrieved evidence:\n{snippets}\n"
        "For each retrieved evidence, return stance ∈ {verifies, contradicts, silent} "
        "and a one-sentence reason.  You MAY return up to two additional "
        "contradictions of type VOLUME_MISMATCH, TEMPORAL_UNVERIFIED, or "
        "CONFLICTING_SOURCES, each with a one-sentence reasoning."
    )


def _normalize_llm_response(
    response: Any,
    cap: Capability,
    facts: FacilityFacts,
    retrieved_evidence: list[EvidenceRef],
) -> tuple[list[Contradiction], list[EvidenceAssessment]]:
    """Coerce a structured LLM response into typed objects.

    Expected shape (a dict-like / Pydantic model):
        {
          "evidence_assessments": [
              {"evidence_ref_id": str, "stance": "verifies"|"contradicts"|"silent",
               "reasoning": str}, ...
          ],
          "additional_contradictions": [
              {"contradiction_type": "VOLUME_MISMATCH"|...,
               "severity": "LOW"|"MEDIUM"|"HIGH",
               "reasoning": str}, ...
          ],
          "heuristic_reasoning_overrides": {  # keyed by ContradictionType.value
              "MISSING_EQUIPMENT": "one-sentence override", ...
          }
        }

    Unknown / malformed entries are skipped silently.
    """
    if response is None:
        return [], []

    if isinstance(response, dict):
        payload = response
    else:
        payload = getattr(response, "model_dump", lambda: {})()
    if not isinstance(payload, dict):
        return [], []

    now = _utcnow()
    assessments: list[EvidenceAssessment] = []
    raw_assessments = payload.get("evidence_assessments") or []
    by_ref_id = {f"{ev.source_doc_id}:{ev.chunk_id}": ev for ev in retrieved_evidence}
    for entry in raw_assessments:
        try:
            ref_id = entry["evidence_ref_id"]
            stance = entry["stance"]
            reasoning = entry["reasoning"]
        except (KeyError, TypeError):
            continue
        ev = by_ref_id.get(ref_id)
        facility_id = ev.facility_id if ev else cap.facility_id
        try:
            assessments.append(
                EvidenceAssessment(
                    evidence_ref_id=ref_id,
                    capability_type=cap.capability_type,
                    facility_id=facility_id,
                    stance=stance,
                    reasoning=reasoning,
                    assessed_at=now,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Skipping invalid evidence assessment: %s", exc)

    extras: list[Contradiction] = []
    raw_extras = payload.get("additional_contradictions") or []
    for entry in raw_extras:
        try:
            ctype = ContradictionType(entry["contradiction_type"])
        except (KeyError, ValueError, TypeError):
            continue
        if ctype not in _LLM_ADDITIONAL_TYPES:
            continue
        severity = entry.get("severity", "MEDIUM")
        if severity not in ("LOW", "MEDIUM", "HIGH"):
            severity = "MEDIUM"
        reasoning = entry.get("reasoning") or "LLM-detected contradiction."
        try:
            extras.append(
                Contradiction(
                    contradiction_type=ctype,
                    capability_type=cap.capability_type,
                    facility_id=facts.facility_id,
                    evidence_for=list(cap.evidence_refs),
                    evidence_against=list(retrieved_evidence),
                    severity=severity,  # type: ignore[arg-type]
                    reasoning=reasoning,
                    detected_by=f"{VALIDATOR_ID}.llm",
                    detected_at=now,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Skipping invalid LLM contradiction: %s", exc)

    return extras, assessments


def _apply_reasoning_overrides(
    contradictions: list[Contradiction], response: Any
) -> list[Contradiction]:
    """Let the LLM fill in `reasoning` fields that are blank, but never overwrite."""
    if isinstance(response, dict):
        payload = response
    else:
        payload = getattr(response, "model_dump", lambda: {})()
    if not isinstance(payload, dict):
        return contradictions
    overrides = payload.get("heuristic_reasoning_overrides") or {}
    if not isinstance(overrides, dict):
        return contradictions
    out: list[Contradiction] = []
    for c in contradictions:
        if not c.reasoning and c.contradiction_type.value in overrides:
            new_reason = overrides[c.contradiction_type.value]
            if isinstance(new_reason, str) and new_reason.strip():
                out.append(c.model_copy(update={"reasoning": new_reason.strip()}))
                continue
        out.append(c)
    return out


def validate_capability(
    cap: Capability,
    facts: FacilityFacts,
    retrieved_evidence: list[EvidenceRef] | None = None,
    *,
    use_llm: bool = True,
    model: str = DEFAULT_MODEL,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[list[Contradiction], list[EvidenceAssessment]]:
    """Validate one capability claim using heuristics + an optional LLM pass.

    Args:
        cap: The Capability claim under audit.
        facts: Normalized FacilityFacts derived from the source-of-truth tables.
        retrieved_evidence: Evidence pulled by retrieval/extractor agents that the
            LLM should adjudicate (verifies / contradicts / silent).
        use_llm: When False, skip the LLM step entirely (test default).
        model: Anthropic model id; only used if ``use_llm`` is True.
        client_factory: Optional callable returning an object with a
            ``structured_call(prompt, *, schema, model)`` method.  When None we
            attempt to import ``seahealth.agents.anthropic_client`` lazily.

    Returns:
        ``(contradictions, evidence_assessments)``.
    """
    contradictions = run_all_heuristics(cap, facts, validator_id=f"{VALIDATOR_ID}.heuristics")
    assessments: list[EvidenceAssessment] = []

    if not use_llm:
        return contradictions, assessments

    evidence = list(retrieved_evidence or [])
    if not evidence and not contradictions:
        # Nothing for the LLM to adjudicate.
        return contradictions, assessments

    client = None
    if client_factory is not None:
        try:
            client = client_factory()
        except Exception as exc:
            log.warning("client_factory raised; falling back to heuristics-only: %s", exc)
            return contradictions, assessments
    else:
        module = _try_import_client()
        if module is None:
            return contradictions, assessments
        factory = getattr(module, "get_client", None)
        if factory is None:
            log.warning("anthropic_client has no get_client(); skipping LLM pass.")
            return contradictions, assessments
        try:
            client = factory()
        except Exception as exc:
            log.warning("anthropic_client.get_client() failed: %s", exc)
            return contradictions, assessments

    prompt = _build_llm_prompt(cap, facts, evidence, contradictions)
    try:
        call = getattr(client, "structured_call", None)
        if call is None:
            log.warning("client has no structured_call(); skipping LLM pass.")
            return contradictions, assessments
        response = call(prompt, model=model)
    except Exception as exc:
        log.warning("LLM structured_call failed; returning heuristic-only result: %s", exc)
        return contradictions, assessments

    contradictions = _apply_reasoning_overrides(contradictions, response)
    extra_contradictions, assessments = _normalize_llm_response(
        response, cap, facts, evidence
    )
    contradictions = contradictions + extra_contradictions
    return contradictions, assessments
