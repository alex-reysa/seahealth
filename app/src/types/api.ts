/**
 * Typed shapes for SeaHealth API responses. Mirror src/seahealth/schemas.
 *
 * These types are a compile-time subset of the Pydantic schemas — only the
 * fields the UI consumes today. There is no runtime validation: a shape
 * mismatch will surface as a TypeScript error during build or as `undefined`
 * at the call site. Treat the canonical contract in
 * `docs/api/openapi.yaml` as the source of truth and keep this file in
 * sync by hand.
 */

export type CapabilityType =
  | 'ICU'
  | 'SURGERY_GENERAL'
  | 'SURGERY_APPENDECTOMY'
  | 'DIALYSIS'
  | 'ONCOLOGY'
  | 'NEONATAL'
  | 'TRAUMA'
  | 'MATERNAL'
  | 'RADIOLOGY'
  | 'LAB'
  | 'PHARMACY'
  | 'EMERGENCY_24_7';

export type ContradictionSeverity = 'LOW' | 'MEDIUM' | 'HIGH';

export interface GeoPoint {
  lat: number;
  lng: number;
  pin_code?: string | null;
}

export interface EvidenceRef {
  source_doc_id: string;
  facility_id: string;
  chunk_id: string;
  row_id?: string | null;
  span: [number, number];
  snippet: string;
  source_type: string;
  source_observed_at?: string | null;
  retrieved_at: string;
}

export interface Contradiction {
  contradiction_type: string;
  capability_type: CapabilityType;
  facility_id: string;
  evidence_for: EvidenceRef[];
  evidence_against: EvidenceRef[];
  severity: ContradictionSeverity;
  reasoning: string;
  detected_by: string;
  detected_at: string;
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

export interface Capability {
  facility_id: string;
  capability_type: CapabilityType;
  claimed: boolean;
  evidence_refs: EvidenceRef[];
  source_doc_id: string;
  extracted_at: string;
  extractor_model: string;
  mlflow_trace_id?: string | null;
}

export interface FacilityAudit {
  facility_id: string;
  name: string;
  location: GeoPoint;
  capabilities: Capability[];
  trust_scores: Partial<Record<CapabilityType, TrustScore>>;
  total_contradictions: number;
  last_audited_at: string;
  mlflow_trace_id?: string | null;
}

export interface SummaryMetrics {
  audited_count: number;
  verified_count: number;
  flagged_count: number;
  last_audited_at: string;
  capability_type?: CapabilityType | null;
  /** 95% Wilson interval on verified_count / audited_count, or null when N=0. */
  verified_count_ci?: [number, number] | null;
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

export interface ParsedIntent {
  capability_type: CapabilityType;
  location: GeoPoint;
  radius_km: number;
  staffing_qualifier?: 'parttime' | 'fulltime' | 'twentyfour_seven' | 'low_volume' | null;
}

export type ExecutionStepStatus = 'ok' | 'fallback' | 'error';
export type RetrieverMode = 'vector_search' | 'faiss_local' | 'fixture';

export interface ExecutionStep {
  name: string;
  started_at: string;
  finished_at: string;
  status: ExecutionStepStatus;
  detail?: string | null;
}

export interface QueryResult {
  query: string;
  parsed_intent: ParsedIntent;
  ranked_facilities: RankedFacility[];
  total_candidates: number;
  /** Always-present synthetic correlation id (`q_<uuid>`). */
  query_trace_id: string;
  /** Real MLflow trace id when MLFLOW_TRACKING_URI is configured; else null. */
  mlflow_trace_id?: string | null;
  /** Optional deep-link to the MLflow trace UI. */
  mlflow_trace_url?: string | null;
  execution_steps: ExecutionStep[];
  retriever_mode: RetrieverMode;
  used_llm: boolean;
  generated_at: string;
}

export type PopulationSource = 'delta' | 'fixture' | 'unavailable';

export interface MapRegionAggregate {
  region_id: string;
  region_name: string;
  state: string;
  capability_type: CapabilityType;
  population: number;
  verified_facilities_count: number;
  flagged_facilities_count: number;
  gap_population: number;
  centroid: GeoPoint;
  /** Honest provenance of the population denominator. */
  population_source: PopulationSource;
}

export interface HealthData {
  mode: 'delta' | 'parquet' | 'fixture';
  facility_audits_path: string;
  delta_reachable: boolean;
  retriever_mode: 'vector_search' | 'faiss_local' | 'unknown';
  vs_endpoint?: string | null;
  vs_index?: string | null;
}

/** Trace classification mirror of seahealth.agents.facility_audit_builder.classify_trace_id. */
export type TraceClass = 'live' | 'synthetic' | 'missing';

export function classifyTraceId(traceId: string | null | undefined): TraceClass {
  if (!traceId) return 'missing';
  if (traceId.startsWith('local::')) return 'synthetic';
  return 'live';
}
