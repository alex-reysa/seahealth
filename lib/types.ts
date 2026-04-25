// Based on docs/DATA_CONTRACT.md - TypeScript equivalents of Pydantic schemas

export interface GeoPoint {
  lat: number;
  lng: number;
  pin_code?: string;
}

export type CapabilityType =
  | "ICU"
  | "SURGERY_GENERAL"
  | "SURGERY_APPENDECTOMY"
  | "DIALYSIS"
  | "ONCOLOGY"
  | "NEONATAL"
  | "TRAUMA"
  | "MATERNAL"
  | "RADIOLOGY"
  | "LAB"
  | "PHARMACY"
  | "EMERGENCY_24_7";

export const CAPABILITY_LABELS: Record<CapabilityType, string> = {
  ICU: "ICU",
  SURGERY_GENERAL: "General Surgery",
  SURGERY_APPENDECTOMY: "Appendectomy",
  DIALYSIS: "Dialysis",
  ONCOLOGY: "Oncology",
  NEONATAL: "Neonatal Care",
  TRAUMA: "Trauma",
  MATERNAL: "Maternal Care",
  RADIOLOGY: "Radiology",
  LAB: "Laboratory",
  PHARMACY: "Pharmacy",
  EMERGENCY_24_7: "24/7 Emergency",
};

export type SourceType =
  | "facility_note"
  | "staff_roster"
  | "equipment_inventory"
  | "volume_report"
  | "external";

export type EvidenceStance = "verifies" | "contradicts" | "silent";

export interface EvidenceRef {
  source_doc_id: string;
  facility_id: string;
  chunk_id: string;
  row_id?: string;
  span: [number, number];
  snippet: string;
  source_type: SourceType;
  source_observed_at?: string;
  retrieved_at: string;
}

export interface Capability {
  facility_id: string;
  capability_type: CapabilityType;
  claimed: boolean;
  evidence_refs: EvidenceRef[];
  source_doc_id: string;
  extracted_at: string;
  extractor_model: string;
}

export type ContradictionType =
  | "MISSING_EQUIPMENT"
  | "MISSING_STAFF"
  | "VOLUME_MISMATCH"
  | "TEMPORAL_UNVERIFIED"
  | "CONFLICTING_SOURCES"
  | "STALE_DATA";

export const CONTRADICTION_LABELS: Record<ContradictionType, string> = {
  MISSING_EQUIPMENT: "Missing Equipment",
  MISSING_STAFF: "Missing Staff",
  VOLUME_MISMATCH: "Volume Mismatch",
  TEMPORAL_UNVERIFIED: "Temporal Unverified",
  CONFLICTING_SOURCES: "Conflicting Sources",
  STALE_DATA: "Stale Data",
};

export type Severity = "LOW" | "MEDIUM" | "HIGH";

export const SEVERITY_PENALTY: Record<Severity, number> = {
  LOW: 5,
  MEDIUM: 15,
  HIGH: 30,
};

export interface Contradiction {
  contradiction_type: ContradictionType;
  capability_type: CapabilityType;
  facility_id: string;
  evidence_for: EvidenceRef[];
  evidence_against: EvidenceRef[];
  severity: Severity;
  reasoning: string;
  detected_by: string;
  detected_at: string;
}

export interface EvidenceAssessment {
  evidence_ref: EvidenceRef;
  stance: EvidenceStance;
  capability_type: CapabilityType;
  contradiction_type?: ContradictionType;
  rationale: string;
}

export interface TrustScore {
  capability_type: CapabilityType;
  claimed: boolean;
  evidence: EvidenceRef[];
  contradictions: Contradiction[];
  confidence: number;
  confidence_interval: [number, number];
  score: number;
  reasoning: string;
  computed_at: string;
}

export interface FacilityAudit {
  facility_id: string;
  name: string;
  location: GeoPoint;
  capabilities: Capability[];
  trust_scores: Record<CapabilityType, TrustScore>;
  total_contradictions: number;
  last_audited_at: string;
  mlflow_trace_id?: string;
}

export interface ParsedIntent {
  capability_type: CapabilityType;
  location: GeoPoint;
  radius_km: number;
}

export interface RankedFacility {
  facility_id: string;
  name: string;
  location: GeoPoint;
  distance_km: number;
  trust_score: TrustScore;
  contradictions_flagged: number;
  evidence_count: number;
  rank: number;
}

export interface QueryResult {
  query: string;
  parsed_intent: ParsedIntent;
  ranked_facilities: RankedFacility[];
  total_candidates: number;
  query_trace_id: string;
  generated_at: string;
}

export interface PopulationReference {
  region_id: string;
  region_name: string;
  centroid: GeoPoint;
  population_count: number;
  source_doc_id: string;
  source_observed_at?: string;
}

export interface MapRegionAggregate {
  region_id: string;
  region_name: string;
  capability_type: CapabilityType;
  centroid: GeoPoint;
  population: PopulationReference;
  radius_km: number;
  verified_capability_count: number;
  capability_count_ci: [number, number];
  covered_population: number;
  gap_population: number;
  coverage_ratio: number;
  generated_at: string;
}

// Map command types for agent control
export type MapCommandType =
  | "focus_location"
  | "set_capability"
  | "set_radius"
  | "select_region"
  | "highlight_facilities"
  | "open_facility"
  | "reset_map";

export interface MapCommand {
  type: MapCommandType;
  location_label?: string;
  center?: GeoPoint;
  zoom?: number;
  capability_type?: CapabilityType;
  radius_km?: number;
  region_id?: string;
  facility_ids?: string[];
  facility_id?: string;
}

// Dashboard summary metrics
export interface AuditSummary {
  audited_facilities: number;
  verified_facilities: number;
  flagged_facilities: number;
  last_audited_at?: string;
  current_capability: CapabilityType;
}
