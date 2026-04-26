"""SeaHealth Pydantic v2 schemas — single source of truth for cross-module data shapes."""
from ._evidence_id import evidence_ref_id
from .capability import Capability
from .capability_type import CapabilityType
from .contradiction import (
    STALE_DATA_THRESHOLD_MONTHS,
    Contradiction,
    ContradictionType,
)
from .evidence import EvidenceRef, EvidenceStance, SourceType
from .evidence_assessment import EvidenceAssessment
from .facility_audit import FacilityAudit
from .geo import GeoPoint
from .indexed_doc import EMBEDDING_DIM, IndexedDoc
from .map import MapRegionAggregate, PopulationReference
from .query_result import ParsedIntent, QueryResult, RankedFacility, StaffingQualifier
from .summary import SummaryMetrics
from .trust_score import SEVERITY_PENALTY, TrustScore

__all__ = [
    # constants
    "EMBEDDING_DIM",
    "SEVERITY_PENALTY",
    "STALE_DATA_THRESHOLD_MONTHS",
    # type aliases
    "EvidenceStance",
    "SourceType",
    "StaffingQualifier",
    # core models
    "Capability",
    "CapabilityType",
    "Contradiction",
    "ContradictionType",
    "EvidenceAssessment",
    "EvidenceRef",
    "FacilityAudit",
    "GeoPoint",
    "IndexedDoc",
    "MapRegionAggregate",
    "ParsedIntent",
    "PopulationReference",
    "QueryResult",
    "RankedFacility",
    "SummaryMetrics",
    "TrustScore",
    # helpers
    "evidence_ref_id",
]
