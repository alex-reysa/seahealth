"""TrustScore — per-capability trust assessment with deterministic score derivation."""

from pydantic import BaseModel, Field, model_validator

from ._datetime import AwareDatetime
from .capability_type import CapabilityType
from .contradiction import Contradiction
from .evidence import EvidenceRef

SEVERITY_PENALTY: dict[str, int] = {"LOW": 5, "MEDIUM": 15, "HIGH": 30}


class TrustScore(BaseModel):
    """Per-capability trust assessment. First-class structured object — never a bare float.

    Score derivation (deterministic, document the mapping here so downstream agents agree):
      base        = round(confidence * 100)            # 0..100
      penalty     = sum of severity weights across contradictions
                    (LOW=5, MEDIUM=15, HIGH=30)
      score       = max(0, min(100, base - penalty))

    Bands used by the UI:
      80-100 = green, 50-79 = amber, 0-49 = red.
    """

    capability_type: CapabilityType
    claimed: bool
    evidence: list[EvidenceRef] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model-reported probability the claim is true."
    )
    confidence_interval: tuple[float, float] = Field(
        ...,
        description="95% CI on confidence; both endpoints in [0.0, 1.0], lo <= hi.",
    )
    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Derived 0-100 headline number per the docstring formula.",
    )
    reasoning: str = Field(
        ...,
        description="Short paragraph, model-generated, shown in the Trust Score drawer.",
    )
    computed_at: AwareDatetime

    @model_validator(mode="after")
    def _validate_ci_and_score(self) -> "TrustScore":
        lo, hi = self.confidence_interval
        if not (0.0 <= lo <= hi <= 1.0):
            raise ValueError("confidence_interval must satisfy 0.0 <= lo <= hi <= 1.0")
        self.confidence_interval = (min(lo, self.confidence), max(hi, self.confidence))
        base = round(self.confidence * 100)
        penalty = sum(SEVERITY_PENALTY[c.severity] for c in self.contradictions)
        expected_score = max(0, min(100, base - penalty))
        if self.score != expected_score:
            raise ValueError(
                "score must equal max(0, min(100, round(confidence * 100) - severity_penalty_sum))"
            )
        return self
