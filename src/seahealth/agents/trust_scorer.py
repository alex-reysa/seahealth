"""Trust Scorer agent — derives a deterministic :class:`TrustScore` for one capability.

The scorer composes:

1. A deterministic ``confidence`` recipe driven by evidence breadth (distinct
   ``source_type`` count) and depth (number of evidence refs). Claims with zero
   evidence are pinned to the minimum confidence because there is no defensible
   support to score from.
2. The contract-locked penalty formula
   ``score = clamp(round(confidence * 100) - Σseverity_weights, 0, 100)``
   with ``LOW=5, MEDIUM=15, HIGH=30``.
3. A reproducible bootstrap of the score distribution (n=200) used to derive
   a 95% confidence interval expressed as confidence proxies in ``[0.0, 1.0]``.
4. An optional one-sentence ``reasoning`` string sourced from a tiny LLM call
   (mock-friendly via ``client_factory``); falls back to a deterministic
   templated sentence when the LLM is disabled or unavailable.

No I/O happens unless ``use_llm=True`` and a working ``client_factory`` /
``llm_client`` is wired in. Tests must drive the LLM path through
``client_factory`` and never hit the network.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from seahealth.schemas import (
    SEVERITY_PENALTY,
    Capability,
    Contradiction,
    TrustScore,
)

from .llm_client import DEFAULT_LIGHT_MODEL

log = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_LIGHT_MODEL
SCORER_ID = "trust_scorer.v1"

# Bootstrap iteration count is fixed for reproducibility of the CI bounds.
_BOOTSTRAP_ITERS = 200
# Confidence is clamped into this band so a hot streak of evidence cannot
# imply absolute certainty and a complete absence cannot imply absolute denial.
_CONFIDENCE_MIN = 0.05
_CONFIDENCE_MAX = 0.95
# Recipe constants — kept as module-level so tests/diagnostics can import them.
_CONFIDENCE_BASE = 0.5
_PER_SOURCE_TYPE_BONUS = 0.1
_PER_EVIDENCE_BONUS = 0.05
_SOURCE_TYPE_CAP = 4
_EVIDENCE_CAP = 4


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compute_confidence(cap: Capability) -> float:
    """Deterministic recipe producing ``confidence`` ∈ [0.05, 0.95]."""
    if not cap.evidence_refs:
        return _CONFIDENCE_MIN
    distinct_types = {ev.source_type for ev in cap.evidence_refs}
    type_bonus = _PER_SOURCE_TYPE_BONUS * min(len(distinct_types), _SOURCE_TYPE_CAP)
    depth_bonus = _PER_EVIDENCE_BONUS * min(len(cap.evidence_refs), _EVIDENCE_CAP)
    raw = _CONFIDENCE_BASE + type_bonus + depth_bonus
    return _clamp(raw, _CONFIDENCE_MIN, _CONFIDENCE_MAX)


def _penalty(contradictions: list[Contradiction]) -> int:
    return sum(SEVERITY_PENALTY[c.severity] for c in contradictions)


def _score_from(confidence: float, contradictions: list[Contradiction]) -> int:
    base = round(confidence * 100)
    return max(0, min(100, base - _penalty(contradictions)))


def _bootstrap_ci(
    confidence: float,
    contradictions: list[Contradiction],
    *,
    rng_seed: int,
) -> tuple[float, float]:
    """Reproducible bootstrap CI over contradiction-severity perturbations.

    Each iteration resamples ``len(contradictions)`` items with replacement
    from the input list and recomputes the score. We collect 200 scores and
    take the 2.5 / 97.5 percentiles, dividing by 100 to express the CI as a
    confidence proxy in ``[0.0, 1.0]``.
    """
    rng = random.Random(rng_seed)
    n = len(contradictions)
    if n == 0:
        # No perturbation -> CI collapses to the deterministic confidence.
        c = _clamp(confidence, 0.0, 1.0)
        return c, c

    scores: list[int] = []
    for _ in range(_BOOTSTRAP_ITERS):
        sample = [contradictions[rng.randrange(n)] for _ in range(n)]
        scores.append(_score_from(confidence, sample))

    scores.sort()
    # Percentile via nearest-rank with linear-ish indexing; deterministic given
    # the seeded RNG above so two runs produce identical CI bounds.
    lo_idx = max(0, int(round(0.025 * (len(scores) - 1))))
    hi_idx = min(len(scores) - 1, int(round(0.975 * (len(scores) - 1))))
    lo = scores[lo_idx] / 100.0
    hi = scores[hi_idx] / 100.0
    if lo > hi:
        lo, hi = hi, lo
    return _clamp(lo, 0.0, 1.0), _clamp(hi, 0.0, 1.0)


def _contradiction_type_names(contradictions: list[Contradiction]) -> list[str]:
    return sorted({c.contradiction_type.name for c in contradictions})


def _templated_reasoning(
    score: int,
    n_evidence: int,
    contradictions: list[Contradiction],
) -> str:
    n_contradictions = len(contradictions)
    if n_contradictions:
        names = ", ".join(_contradiction_type_names(contradictions))
        return (
            f"Score {score} based on {n_evidence} evidence sources and "
            f"{n_contradictions} contradictions: {names}."
        )
    return (
        f"Score {score} based on {n_evidence} evidence sources and "
        "no contradictions."
    )


def _llm_reasoning(
    cap: Capability,
    contradictions: list[Contradiction],
    score: int,
    *,
    model: str,
    client_factory: Callable[..., Any] | None,
) -> str | None:
    """Best-effort one-sentence reasoning. Returns ``None`` on any failure."""
    client: Any | None = None
    if client_factory is not None:
        try:
            client = client_factory()
        except Exception as exc:  # pragma: no cover - exercised via fake factory
            log.warning("trust_scorer client_factory raised: %s", exc)
            return None
    else:
        try:
            from seahealth.agents import llm_client  # type: ignore
        except Exception as exc:
            log.warning("trust_scorer llm_client unavailable: %s", exc)
            return None
        factory = getattr(llm_client, "get_client", None)
        if factory is None:
            return None
        try:
            client = factory()
        except Exception as exc:
            log.warning("trust_scorer llm_client.get_client failed: %s", exc)
            return None

    call = getattr(client, "structured_call", None)
    if call is None:
        return None
    prompt = (
        f"Capability {cap.capability_type.value} (claimed={cap.claimed}) at "
        f"facility {cap.facility_id}. Score={score} with "
        f"{len(cap.evidence_refs)} evidence sources and "
        f"{len(contradictions)} contradictions"
        f" ({', '.join(_contradiction_type_names(contradictions)) or 'none'}). "
        "Return ONE sentence summarizing why this trust score is appropriate."
    )
    try:
        result = call(prompt, model=model)
    except Exception as exc:
        log.warning("trust_scorer structured_call failed: %s", exc)
        return None

    if isinstance(result, str):
        text = result.strip()
        return text or None
    # Tolerate Pydantic models / dicts with a ``reasoning`` field.
    if hasattr(result, "reasoning"):
        text = str(result.reasoning).strip()
        return text or None
    if isinstance(result, dict):
        text = str(result.get("reasoning", "")).strip()
        return text or None
    return None


def score_capability(
    cap: Capability,
    contradictions: list[Contradiction],
    *,
    use_llm: bool = True,
    model: str = DEFAULT_MODEL,
    client_factory: Callable[..., Any] | None = None,
    rng_seed: int = 42,
) -> TrustScore:
    """Compute a deterministic :class:`TrustScore` for one capability claim.

    See module docstring for the formula. ``use_llm=False`` short-circuits the
    network call and uses a templated reasoning string. ``rng_seed`` is the only
    source of stochasticity (bootstrap CI) and is exposed so tests can pin it.

    Args:
        cap: The :class:`Capability` claim under audit.
        contradictions: All contradictions tied to this capability for this
            facility (already filtered upstream in the audit builder).
        use_llm: When False, reasoning is the deterministic template.
        model: Databricks serving-endpoint name used when ``use_llm=True``.
        client_factory: Optional callable returning an object with a
            ``structured_call(prompt, *, model)`` method. When ``None`` we lazy
            import ``seahealth.agents.llm_client`` and call ``get_client``.
        rng_seed: Seed for the bootstrap RNG. Same seed → same CI bounds.

    Returns:
        A fully-validated :class:`TrustScore`.
    """
    confidence = _compute_confidence(cap)
    score = _score_from(confidence, contradictions)
    ci_lo, ci_hi = _bootstrap_ci(confidence, contradictions, rng_seed=rng_seed)

    reasoning: str | None = None
    if use_llm:
        reasoning = _llm_reasoning(
            cap,
            contradictions,
            score,
            model=model,
            client_factory=client_factory,
        )
    if reasoning is None:
        reasoning = _templated_reasoning(score, len(cap.evidence_refs), contradictions)

    return TrustScore(
        capability_type=cap.capability_type,
        claimed=cap.claimed,
        evidence=list(cap.evidence_refs),
        contradictions=list(contradictions),
        confidence=confidence,
        confidence_interval=(ci_lo, ci_hi),
        score=score,
        reasoning=reasoning,
        computed_at=_utcnow(),
    )
