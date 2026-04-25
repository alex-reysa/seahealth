# DATA_CONTRACT

> The load-bearing spec. If this is wrong, we lose the hackathon. Lock before any extraction code is written. **One person owns this file and has veto power on changes after hour 4.**
>
> **Schema owner: Alejandro (acting schema owner).**
>
> Every schema below MUST be implemented in `src/schemas/` (module paths shown in snippet headers, re-exported from `src/schemas/__init__.py`). Code blocks are module contracts: type aliases, classes, fields, constants, validators, and formulas are authoritative. Lines beginning `# from .` are required imports in `src`; they are commented here only so snippets remain readable in one doc. Agents, validators, the Planner Console, and the Trust Score UI all import from `src/schemas/`. Drift between this file and `src/schemas/` is a hackathon-killer.

---

## GeoPoint

```python
# src/schemas/geo.py — module contract.
from pydantic import BaseModel, Field
from typing import Optional

class GeoPoint(BaseModel):
    """A geographic point with optional Indian PIN code; used for facility location and radius queries."""
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees.")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees.")
    pin_code: Optional[str] = Field(
        default=None,
        pattern=r"^\d{6}$",
        description="Indian Postal Index Number, exactly 6 digits.",
    )
```

---

## CapabilityType

```python
# src/schemas/capability_type.py — module contract.
from enum import StrEnum

class CapabilityType(StrEnum):
    """Closed set of facility capabilities considered in scope for the hackathon demo."""
    ICU = "ICU"
    SURGERY_GENERAL = "SURGERY_GENERAL"
    SURGERY_APPENDECTOMY = "SURGERY_APPENDECTOMY"
    DIALYSIS = "DIALYSIS"
    ONCOLOGY = "ONCOLOGY"
    NEONATAL = "NEONATAL"
    TRAUMA = "TRAUMA"
    MATERNAL = "MATERNAL"
    RADIOLOGY = "RADIOLOGY"
    LAB = "LAB"
    PHARMACY = "PHARMACY"
    EMERGENCY_24_7 = "EMERGENCY_24_7"
```

---

## EvidenceRef — citation shape

```python
# src/schemas/evidence.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal, Optional, Tuple

SourceType = Literal[
    "facility_note",
    "staff_roster",
    "equipment_inventory",
    "volume_report",
    "external",
]

EvidenceStance = Literal["verifies", "contradicts", "silent"]

class EvidenceRef(BaseModel):
    """A pointer to the exact span in a source document that supports or refutes a claim. Every UI citation chip resolves through this object."""
    source_doc_id: str = Field(..., description="Stable id of the originating document.")
    facility_id: str = Field(..., description="Facility this evidence is attached to.")
    chunk_id: str = Field(..., description="Id of the chunk within the indexed doc.")
    row_id: Optional[str] = Field(default=None, description="Row id when source is tabular (staff/equipment/volume).")
    span: Tuple[int, int] = Field(..., description="(start, end) char offsets within the chunk text.")
    snippet: str = Field(..., description="The highlighted sentence rendered in the citation chip.")
    source_type: SourceType = Field(..., description="Provenance class for downstream weighting.")
    source_observed_at: Optional[datetime] = Field(default=None, description="When the source content was published, observed, or last updated; used for STALE_DATA.")
    retrieved_at: datetime = Field(..., description="When the retrieval/extraction step pulled this evidence.")
```

---

## Pydantic schemas — extracted capabilities

```python
# src/schemas/capability.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List

# from .capability_type import CapabilityType
# from .evidence import EvidenceRef

class Capability(BaseModel):
    """A single claimed-or-denied capability for one facility, with its supporting evidence chain."""
    facility_id: str
    capability_type: CapabilityType
    claimed: bool = Field(..., description="True if the source asserts the facility offers this capability.")
    evidence_refs: List[EvidenceRef] = Field(default_factory=list, description="All evidence supporting the claim/denial.")
    source_doc_id: str = Field(..., description="Primary doc the claim was extracted from.")
    extracted_at: datetime
    extractor_model: str = Field(..., description="Model id used for extraction (e.g. 'databricks-meta-llama-3-1-70b-instruct').")
```

---

## Contradiction taxonomy (enum)

The taxonomy is **closed**. New types require an explicit DECISIONS.md entry and a schema bump.

- `MISSING_EQUIPMENT` — capability claimed without supporting equipment (e.g. surgery, no anesthesia machine).
- `MISSING_STAFF` — capability claimed without supporting staff (e.g. ICU, no critical care nurse).
- `VOLUME_MISMATCH` — claim inconsistent with reported volume (e.g. trauma center, 2 beds).
- `TEMPORAL_UNVERIFIED` — temporal claim unsupported (e.g. 24/7 with one named doctor).
- `CONFLICTING_SOURCES` — two sources disagree on the same capability.
- `STALE_DATA` — supporting evidence older than `STALE_DATA_THRESHOLD_MONTHS`.

```python
# src/schemas/contradiction.py — module contract.
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field
from typing import List, Literal

# from .capability_type import CapabilityType
# from .evidence import EvidenceRef

STALE_DATA_THRESHOLD_MONTHS: int = 24  # Evidence older than this trips STALE_DATA.

class ContradictionType(StrEnum):
    """Closed taxonomy of validator-detectable contradictions for the hackathon demo."""
    MISSING_EQUIPMENT = "MISSING_EQUIPMENT"
    MISSING_STAFF = "MISSING_STAFF"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"
    TEMPORAL_UNVERIFIED = "TEMPORAL_UNVERIFIED"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    STALE_DATA = "STALE_DATA"

class Contradiction(BaseModel):
    """A single detected contradiction tying a claim to the evidence that contests it. Rendered as a flag in FacilityAudit and RankedFacility."""
    contradiction_type: ContradictionType
    capability_type: CapabilityType
    facility_id: str
    evidence_for: List[EvidenceRef] = Field(default_factory=list, description="Evidence supporting the original claim.")
    evidence_against: List[EvidenceRef] = Field(default_factory=list, description="Evidence undermining the claim.")
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str = Field(..., description="One-sentence model-generated rationale.")
    detected_by: str = Field(..., description="Validator agent id (e.g. 'validator.equipment_v1').")
    detected_at: datetime
```

---

## EvidenceAssessment — validator output

```python
# src/schemas/evidence_assessment.py — module contract.
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# from .capability_type import CapabilityType

class EvidenceAssessment(BaseModel):
    """Validator's per-evidence stance, joined into the Facility Audit View.

    Each row pins one evidence span to one capability claim and records whether the
    Validator agent thinks that span verifies, contradicts, or is silent on the claim.
    The join key is the EvidenceRef id — see seahealth.schemas.evidence_ref_id().
    """
    evidence_ref_id: str = Field(..., description="Stable id of the EvidenceRef this assessment refers to.")
    capability_type: CapabilityType = Field(..., description="The capability this evidence was assessed against.")
    facility_id: str = Field(..., description="Facility the evidence belongs to.")
    stance: Literal["verifies", "contradicts", "silent"] = Field(
        ..., description="Validator stance on this evidence relative to the capability claim."
    )
    reasoning: str = Field(..., description="One-sentence Validator rationale for the stance.")
    assessed_at: datetime = Field(..., description="When the Validator produced this stance.")
```

---

## Trust Score object

```python
# src/schemas/trust_score.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Tuple

# from .capability_type import CapabilityType
# from .evidence import EvidenceRef
# from .contradiction import Contradiction

SEVERITY_PENALTY: Dict[str, int] = {"LOW": 5, "MEDIUM": 15, "HIGH": 30}

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
    evidence: List[EvidenceRef] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model-reported probability the claim is true.")
    confidence_interval: Tuple[float, float] = Field(
        ...,
        description="95% CI on confidence; endpoints in [0.0, 1.0], lo <= confidence <= hi.",
    )
    score: int = Field(..., ge=0, le=100, description="Derived 0-100 headline number per the docstring formula.")
    reasoning: str = Field(..., description="Short paragraph, model-generated, shown in the Trust Score drawer.")
    computed_at: datetime

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
            raise ValueError("score must equal max(0, min(100, round(confidence * 100) - severity_penalty_sum))")
        return self
```

---

## Facility audit record (canonical output)

_The single artifact every UI surface reads._

```python
# src/schemas/facility_audit.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

# from .geo import GeoPoint
# from .capability import Capability
# from .capability_type import CapabilityType
# from .trust_score import TrustScore

class FacilityAudit(BaseModel):
    """Canonical per-facility audit record. The Planner Console, Facility Card, Trust Score drawer, and contradiction list all read from this shape."""
    facility_id: str
    name: str
    location: GeoPoint
    capabilities: List[Capability] = Field(default_factory=list)
    trust_scores: Dict[CapabilityType, TrustScore] = Field(
        default_factory=dict,
        description="Keyed by CapabilityType for O(1) lookup from the UI.",
    )
    total_contradictions: int = Field(
        default=0, ge=0,
        description="Denormalized sum across trust_scores[*].contradictions; used for UI sort/filter.",
    )
    last_audited_at: datetime
    mlflow_trace_id: Optional[str] = Field(
        default=None,
        description="MLflow trace id linking to the agent run that produced this audit (transparency view).",
    )
```

---

## Vector index document shape

```python
# src/schemas/indexed_doc.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

# from .evidence import SourceType

EMBEDDING_DIM: int = 1024  # BAAI/bge-large-en-v1.5 — locked for the demo. See DECISIONS.md if changed.

class IndexedDoc(BaseModel):
    """One chunk in the vector index. Embedding dim is fixed at 1024 for BAAI/bge-large-en-v1.5."""
    doc_id: str
    facility_id: Optional[str] = None
    text: str = Field(..., description="The chunk text as embedded.")
    embedding: List[float] = Field(..., min_length=EMBEDDING_DIM, max_length=EMBEDDING_DIM)
    chunk_index: int = Field(..., ge=0, description="Position of this chunk within its parent document.")
    source_type: SourceType
    source_observed_at: Optional[datetime] = Field(default=None, description="When the source content was published, observed, or last updated; used for STALE_DATA.")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Free-form string metadata (region, doc_date, etc.).")
```

---

## QueryResult — Planner Console output

```python
# src/schemas/query_result.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List

# from .capability_type import CapabilityType
# from .geo import GeoPoint
# from .trust_score import TrustScore

class ParsedIntent(BaseModel):
    """Structured query intent used by retrieval and ranking."""
    capability_type: CapabilityType
    location: GeoPoint
    radius_km: float = Field(..., gt=0.0, description="Search radius around location in kilometers.")

class RankedFacility(BaseModel):
    """One row in a QueryResult — a facility that matches the parsed query, with the relevant capability's TrustScore."""
    facility_id: str
    name: str
    location: GeoPoint
    distance_km: float = Field(..., ge=0.0, description="Great-circle distance from query origin.")
    trust_score: TrustScore = Field(..., description="TrustScore for the capability the query asked about.")
    contradictions_flagged: int = Field(..., ge=0)
    evidence_count: int = Field(..., ge=0)
    rank: int = Field(..., ge=1, description="1-indexed rank in the result list.")

class QueryResult(BaseModel):
    """Planner Console output. Drives the demo query: e.g. 'Which facilities within 50km of Patna can perform an appendectomy?'"""
    query: str = Field(..., description="Natural-language query as the user asked it.")
    parsed_intent: ParsedIntent
    ranked_facilities: List[RankedFacility] = Field(default_factory=list)
    total_candidates: int = Field(..., ge=0, description="Candidates considered before ranking/cutoff.")
    query_trace_id: str = Field(..., description="MLflow trace id for the planner run.")
    generated_at: datetime
```

---

## Desert Map schemas

```python
# src/schemas/desert_map.py — module contract.
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Tuple

# from .capability_type import CapabilityType
# from .geo import GeoPoint

class PopulationReference(BaseModel):
    """Population denominator for one map region."""
    region_id: str
    region_name: str
    centroid: GeoPoint
    population_count: int = Field(..., ge=0)
    source_doc_id: str = Field(..., description="Stable id for the population source.")
    source_observed_at: Optional[datetime] = Field(default=None, description="When the population source was published, observed, or last updated.")

class MapRegionAggregate(BaseModel):
    """Desert Map rollup for one region and capability."""
    region_id: str
    region_name: str
    capability_type: CapabilityType
    centroid: GeoPoint
    population: PopulationReference
    radius_km: float = Field(..., gt=0.0, description="Access radius used for population coverage.")
    verified_capability_count: int = Field(..., ge=0, description="Facilities in region with trust score >= 80 for this capability.")
    capability_count_ci: Tuple[int, int] = Field(..., description="Inclusive 95% CI for verified_capability_count; lo <= hi.")
    covered_population: int = Field(..., ge=0, description="Population within radius_km of a verified facility.")
    gap_population: int = Field(..., ge=0, description="Population not covered for this capability.")
    coverage_ratio: float = Field(..., ge=0.0, le=1.0, description="covered_population / population.population_count; 0.0 when denominator is 0.")
    generated_at: datetime
```

---

## Phase-1 additions (UI-driven)

These three shapes are required by UI surfaces and were not previously defined in this contract. The implementations live in `src/seahealth/schemas/{evidence_assessment,summary,map}.py` and are re-exported from `src/seahealth/schemas/__init__.py`. Where a name overlaps with an earlier section (e.g. `EvidenceAssessment`, `PopulationReference`, `MapRegionAggregate`), the Phase-1 shape below is the slim variant the UI consumes; the richer Delta-rollup shapes from earlier sections remain valid for downstream gold tables, but the schema package exports the Phase-1 variant.

### EvidenceAssessment

```python
# src/seahealth/schemas/evidence_assessment.py — module contract.
# Validator's per-evidence stance, joined into the Facility Audit View.
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# from .capability_type import CapabilityType

class EvidenceAssessment(BaseModel):
    """Validator's per-evidence stance, joined into the Facility Audit View."""
    evidence_ref_id: str = Field(..., description="Stable id of the EvidenceRef this assessment refers to.")
    capability_type: CapabilityType
    facility_id: str
    stance: Literal["verifies", "contradicts", "silent"]
    reasoning: str = Field(..., description="One-sentence Validator rationale for the stance.")
    assessed_at: datetime
```

> The evidence_ref_id MUST be `f"{source_doc_id}:{chunk_id}"`. See `seahealth.schemas.evidence_ref_id`.


### SummaryMetrics

```python
# src/seahealth/schemas/summary.py — module contract.
# Verified = TrustScore.score >= 80 AND no HIGH-severity contradiction.
# Flagged  = total_contradictions > 0.
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# from .capability_type import CapabilityType

class SummaryMetrics(BaseModel):
    """High-level audit tallies for the home/summary tile."""
    audited_count: int = Field(..., ge=0)
    verified_count: int = Field(..., ge=0, description="score>=80 AND no HIGH-severity contradiction.")
    flagged_count: int = Field(..., ge=0, description="total_contradictions > 0.")
    last_audited_at: datetime
    capability_type: Optional[CapabilityType] = None
```

### MapRegionAggregate / PopulationReference

```python
# src/seahealth/schemas/map.py — module contract.
from pydantic import BaseModel, Field

# from .capability_type import CapabilityType
# from .geo import GeoPoint

class PopulationReference(BaseModel):
    """Population denominator for one map region (UI variant)."""
    region_id: str
    population_total: int = Field(..., ge=0)

class MapRegionAggregate(BaseModel):
    """Desert Map rollup for one region and capability, sized for the UI map layer."""
    region_id: str
    region_name: str
    state: str
    capability_type: CapabilityType
    population: int = Field(..., ge=0)
    verified_facilities_count: int = Field(..., ge=0)
    flagged_facilities_count: int = Field(..., ge=0)
    gap_population: int = Field(..., ge=0, description="Population minus a coverage estimate for this capability.")
    centroid: GeoPoint
```

---

## Schema invariants

These invariants are enforced in `src/seahealth/schemas/` and must remain stable unless
`DECISIONS.md` records a schema bump.

- All schema datetime fields are normalized to timezone-aware UTC. JSON serialization
  uses ISO-8601 UTC with a trailing `Z` (for example, `2026-04-25T22:30:00Z`).
- Nullable UI-facing fields stay nullable: `GeoPoint.pin_code`, `EvidenceRef.row_id`,
  `EvidenceRef.source_observed_at`, `IndexedDoc.facility_id`,
  `IndexedDoc.source_observed_at`, `FacilityAudit.mlflow_trace_id`, and
  `SummaryMetrics.capability_type` may be `null`.
- `EvidenceRef.span` must satisfy `start >= 0`, `end >= 0`, and `start <= end`.
- `evidence_ref_id(ref)` is the canonical join id for `EvidenceAssessment` and is
  exactly `f"{ref.source_doc_id}:{ref.chunk_id}"`; it is deterministic and total for
  any valid `EvidenceRef`.
- `IndexedDoc.embedding` length is pinned by the exported `EMBEDDING_DIM` constant
  (`1024`). Do not duplicate the dimension in callers.
- `TrustScore.confidence_interval` input bounds must satisfy `0.0 <= lo <= hi <= 1.0`;
  valid bounds are normalized outward when necessary so the stored model satisfies
  `lo <= confidence <= hi`.
- `TrustScore.score` is deterministic:
  `clamp(round(confidence * 100) - severity_penalty_sum, 0, 100)`, where
  `LOW=5`, `MEDIUM=15`, and `HIGH=30`.
- `MapRegionAggregate.gap_population` must be non-negative.

---

## Change log

_Any change to this file after hour 4 must be logged here AND in `DECISIONS.md`._

- **2026-04-25** — Initial schema lock — all canonical schemas defined (`GeoPoint`, `CapabilityType`, `EvidenceRef`, `EvidenceStance`, `EvidenceAssessment`, `Capability`, `ContradictionType`, `Contradiction`, `TrustScore`, `FacilityAudit`, `IndexedDoc`, `ParsedIntent`, `QueryResult`, `RankedFacility`, `PopulationReference`, `MapRegionAggregate`). Schema owner: **Alejandro (acting schema owner).**
- **2026-04-25** — Schema-lock hardening: added `EvidenceStance`, `EvidenceAssessment`, typed source dates, aligned `SourceType`, typed `ParsedIntent`, ranked facility location, Desert Map population aggregates, and deterministic `TrustScore.score` validation.
- **2026-04-25 22:30** — Added `EvidenceAssessment`, `SummaryMetrics`, `MapRegionAggregate`, `PopulationReference`. Reason: required by UI surfaces; not previously defined.
- **2026-04-25** — Added schema invariants for UTC/Z datetime serialization, evidence span bounds, confidence interval containment, embedding dimension source of truth, non-negative map gap population, and `evidence_ref_id` join semantics.
