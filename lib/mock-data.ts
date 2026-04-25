import type {
  FacilityAudit,
  QueryResult,
  MapRegionAggregate,
  AuditSummary,
  CapabilityType,
  TrustScore,
  Contradiction,
  EvidenceRef,
} from "./types";

// India bounds for map initialization
export const INDIA_BOUNDS: [[number, number], [number, number]] = [
  [68.1, 6.5], // Southwest
  [97.4, 35.5], // Northeast
];

export const INDIA_CENTER: [number, number] = [78.9629, 22.5937];
export const PATNA_CENTER: [number, number] = [85.1376, 25.5941];

// Fixed reference timestamp so server and client render identically
// (avoids hydration mismatches from Date.now() at module load).
const NOW_ISO = "2026-04-25T14:32:00.000Z";
const HOUR_MS = 3600000;
const tsAgo = (hours: number) =>
  new Date(new Date(NOW_ISO).getTime() - hours * HOUR_MS).toISOString();

// Mock evidence references
const createEvidenceRef = (
  facilityId: string,
  snippet: string,
  sourceType: "facility_note" | "staff_roster" | "equipment_inventory" = "facility_note"
): EvidenceRef => ({
  source_doc_id: `doc_${Math.random().toString(36).substr(2, 9)}`,
  facility_id: facilityId,
  chunk_id: `chunk_${Math.random().toString(36).substr(2, 9)}`,
  span: [0, snippet.length],
  snippet,
  source_type: sourceType,
  retrieved_at: NOW_ISO,
});

// Mock contradictions
const createContradiction = (
  facilityId: string,
  capabilityType: CapabilityType,
  type: "MISSING_STAFF" | "MISSING_EQUIPMENT",
  severity: "LOW" | "MEDIUM" | "HIGH"
): Contradiction => ({
  contradiction_type: type,
  capability_type: capabilityType,
  facility_id: facilityId,
  evidence_for: [
    createEvidenceRef(
      facilityId,
      "Facility claims to offer appendectomy surgical services with fully equipped operation theater."
    ),
  ],
  evidence_against: [
    createEvidenceRef(
      facilityId,
      type === "MISSING_STAFF"
        ? "Staff roster shows no certified anesthesiologist on duty."
        : "Equipment inventory does not list anesthesia machine.",
      type === "MISSING_STAFF" ? "staff_roster" : "equipment_inventory"
    ),
  ],
  severity,
  reasoning:
    type === "MISSING_STAFF"
      ? "Appendectomy requires anesthesia support. No anesthesiologist found in staff roster."
      : "Appendectomy requires anesthesia machine. Not found in equipment inventory.",
  detected_by: "validator.equipment_v1",
  detected_at: NOW_ISO,
});

// Mock trust scores
const createTrustScore = (
  capabilityType: CapabilityType,
  score: number,
  facilityId: string,
  hasContradiction: boolean = false
): TrustScore => {
  const contradictions = hasContradiction
    ? [createContradiction(facilityId, capabilityType, "MISSING_STAFF", "MEDIUM")]
    : [];

  return {
    capability_type: capabilityType,
    claimed: true,
    evidence: [
      createEvidenceRef(
        facilityId,
        "Facility documentation confirms operational capacity for this service."
      ),
      createEvidenceRef(
        facilityId,
        "Recent inspection report validates equipment availability.",
        "equipment_inventory"
      ),
    ],
    contradictions,
    confidence: score / 100,
    confidence_interval: [Math.max(0, score - 7) / 100, Math.min(100, score + 7) / 100],
    score,
    reasoning: hasContradiction
      ? `This facility claims ${capabilityType} capability with supporting documentation, but staff roster analysis reveals potential gaps in required personnel. Score reflects evidence strength minus contradiction penalty.`
      : `Strong evidence supports this facility's ${capabilityType} capability. Documentation, equipment inventory, and staff credentials align with claimed services.`,
    computed_at: NOW_ISO,
  };
};

// Mock facilities in Bihar/Patna region
export const MOCK_FACILITIES: FacilityAudit[] = [
  {
    facility_id: "fac_001",
    name: "Patna Medical College Hospital",
    location: { lat: 25.6115, lng: 85.1557, pin_code: "800004" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 94, "fac_001"),
      ICU: createTrustScore("ICU", 91, "fac_001"),
      EMERGENCY_24_7: createTrustScore("EMERGENCY_24_7", 96, "fac_001"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 0,
    last_audited_at: tsAgo(1),
    mlflow_trace_id: "mlflow_trace_001",
  },
  {
    facility_id: "fac_002",
    name: "AIIMS Patna",
    location: { lat: 25.6235, lng: 85.0876, pin_code: "801507" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 98, "fac_002"),
      ICU: createTrustScore("ICU", 97, "fac_002"),
      NEONATAL: createTrustScore("NEONATAL", 95, "fac_002"),
      TRAUMA: createTrustScore("TRAUMA", 96, "fac_002"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 0,
    last_audited_at: tsAgo(2),
    mlflow_trace_id: "mlflow_trace_002",
  },
  {
    facility_id: "fac_003",
    name: "Indira Gandhi Institute of Medical Sciences",
    location: { lat: 25.5973, lng: 85.1127, pin_code: "800014" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 72, "fac_003", true),
      ICU: createTrustScore("ICU", 85, "fac_003"),
      ONCOLOGY: createTrustScore("ONCOLOGY", 88, "fac_003"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 1,
    last_audited_at: tsAgo(3),
    mlflow_trace_id: "mlflow_trace_003",
  },
  {
    facility_id: "fac_004",
    name: "Nalanda Medical College Hospital",
    location: { lat: 25.6022, lng: 85.1371, pin_code: "800004" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 81, "fac_004"),
      MATERNAL: createTrustScore("MATERNAL", 89, "fac_004"),
      NEONATAL: createTrustScore("NEONATAL", 76, "fac_004", true),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 1,
    last_audited_at: tsAgo(4),
    mlflow_trace_id: "mlflow_trace_004",
  },
  {
    facility_id: "fac_005",
    name: "Mahavir Cancer Sansthan",
    location: { lat: 25.5855, lng: 85.0699, pin_code: "801505" },
    capabilities: [],
    trust_scores: {
      ONCOLOGY: createTrustScore("ONCOLOGY", 94, "fac_005"),
      RADIOLOGY: createTrustScore("RADIOLOGY", 92, "fac_005"),
      LAB: createTrustScore("LAB", 90, "fac_005"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 0,
    last_audited_at: tsAgo(5),
    mlflow_trace_id: "mlflow_trace_005",
  },
  {
    facility_id: "fac_006",
    name: "Ruban Memorial Hospital",
    location: { lat: 25.6143, lng: 85.1013, pin_code: "800001" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 67, "fac_006", true),
      EMERGENCY_24_7: createTrustScore("EMERGENCY_24_7", 74, "fac_006", true),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 2,
    last_audited_at: tsAgo(6),
    mlflow_trace_id: "mlflow_trace_006",
  },
  {
    facility_id: "fac_007",
    name: "Paras HMRI Hospital",
    location: { lat: 25.6267, lng: 85.0234, pin_code: "800013" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 89, "fac_007"),
      ICU: createTrustScore("ICU", 93, "fac_007"),
      DIALYSIS: createTrustScore("DIALYSIS", 91, "fac_007"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 0,
    last_audited_at: tsAgo(7),
    mlflow_trace_id: "mlflow_trace_007",
  },
  {
    facility_id: "fac_008",
    name: "Kurji Holy Family Hospital",
    location: { lat: 25.6456, lng: 85.0912, pin_code: "800010" },
    capabilities: [],
    trust_scores: {
      SURGERY_APPENDECTOMY: createTrustScore("SURGERY_APPENDECTOMY", 84, "fac_008"),
      MATERNAL: createTrustScore("MATERNAL", 92, "fac_008"),
      NEONATAL: createTrustScore("NEONATAL", 88, "fac_008"),
    } as Record<CapabilityType, TrustScore>,
    total_contradictions: 0,
    last_audited_at: tsAgo(8),
    mlflow_trace_id: "mlflow_trace_008",
  },
];

// Mock query result for the demo query
export const MOCK_QUERY_RESULT: QueryResult = {
  query: "Which facilities within 50km of Patna can perform an appendectomy?",
  parsed_intent: {
    capability_type: "SURGERY_APPENDECTOMY",
    location: { lat: 25.5941, lng: 85.1376, pin_code: "800001" },
    radius_km: 50,
  },
  ranked_facilities: MOCK_FACILITIES.filter(
    (f) => f.trust_scores.SURGERY_APPENDECTOMY
  )
    .sort(
      (a, b) =>
        (b.trust_scores.SURGERY_APPENDECTOMY?.score || 0) -
        (a.trust_scores.SURGERY_APPENDECTOMY?.score || 0)
    )
    .map((facility, index) => ({
      facility_id: facility.facility_id,
      name: facility.name,
      location: facility.location,
      distance_km: Math.random() * 30 + 2,
      trust_score: facility.trust_scores.SURGERY_APPENDECTOMY!,
      contradictions_flagged: facility.total_contradictions,
      evidence_count: facility.trust_scores.SURGERY_APPENDECTOMY?.evidence.length || 0,
      rank: index + 1,
    })),
  total_candidates: 24,
  query_trace_id: "query_trace_001",
  generated_at: NOW_ISO,
};

// Mock region aggregates for desert map
export const MOCK_REGION_AGGREGATES: MapRegionAggregate[] = [
  {
    region_id: "BR_PATNA",
    region_name: "Patna",
    capability_type: "SURGERY_APPENDECTOMY",
    centroid: { lat: 25.5941, lng: 85.1376, pin_code: "800001" },
    population: {
      region_id: "BR_PATNA",
      region_name: "Patna",
      centroid: { lat: 25.5941, lng: 85.1376 },
      population_count: 5838465,
      source_doc_id: "census_2021",
    },
    radius_km: 50,
    verified_capability_count: 5,
    capability_count_ci: [4, 6],
    covered_population: 4200000,
    gap_population: 1638465,
    coverage_ratio: 0.72,
    generated_at: NOW_ISO,
  },
  {
    region_id: "BR_GAYA",
    region_name: "Gaya",
    capability_type: "SURGERY_APPENDECTOMY",
    centroid: { lat: 24.7955, lng: 85.0002 },
    population: {
      region_id: "BR_GAYA",
      region_name: "Gaya",
      centroid: { lat: 24.7955, lng: 85.0002 },
      population_count: 4391418,
      source_doc_id: "census_2021",
    },
    radius_km: 50,
    verified_capability_count: 2,
    capability_count_ci: [1, 3],
    covered_population: 1800000,
    gap_population: 2591418,
    coverage_ratio: 0.41,
    generated_at: NOW_ISO,
  },
  {
    region_id: "BR_MUZAFFARPUR",
    region_name: "Muzaffarpur",
    capability_type: "SURGERY_APPENDECTOMY",
    centroid: { lat: 26.1209, lng: 85.3647 },
    population: {
      region_id: "BR_MUZAFFARPUR",
      region_name: "Muzaffarpur",
      centroid: { lat: 26.1209, lng: 85.3647 },
      population_count: 4801062,
      source_doc_id: "census_2021",
    },
    radius_km: 50,
    verified_capability_count: 3,
    capability_count_ci: [2, 4],
    covered_population: 2800000,
    gap_population: 2001062,
    coverage_ratio: 0.58,
    generated_at: NOW_ISO,
  },
  {
    region_id: "BR_BHAGALPUR",
    region_name: "Bhagalpur",
    capability_type: "SURGERY_APPENDECTOMY",
    centroid: { lat: 25.2425, lng: 87.0041 },
    population: {
      region_id: "BR_BHAGALPUR",
      region_name: "Bhagalpur",
      centroid: { lat: 25.2425, lng: 87.0041 },
      population_count: 3037766,
      source_doc_id: "census_2021",
    },
    radius_km: 50,
    verified_capability_count: 1,
    capability_count_ci: [0, 2],
    covered_population: 800000,
    gap_population: 2237766,
    coverage_ratio: 0.26,
    generated_at: NOW_ISO,
  },
];

// Mock audit summary
export const MOCK_AUDIT_SUMMARY: AuditSummary = {
  audited_facilities: MOCK_FACILITIES.length,
  verified_facilities: MOCK_FACILITIES.filter(
    (f) =>
      f.trust_scores.SURGERY_APPENDECTOMY &&
      f.trust_scores.SURGERY_APPENDECTOMY.score >= 80
  ).length,
  flagged_facilities: MOCK_FACILITIES.filter((f) => f.total_contradictions > 0).length,
  last_audited_at: MOCK_FACILITIES[0].last_audited_at,
  current_capability: "SURGERY_APPENDECTOMY",
};

// Helper to get facility by ID
export function getFacilityById(id: string): FacilityAudit | undefined {
  return MOCK_FACILITIES.find((f) => f.facility_id === id);
}

// Helper to search facilities
export function searchFacilities(query: string): FacilityAudit[] {
  const q = query.toLowerCase();
  return MOCK_FACILITIES.filter(
    (f) =>
      f.name.toLowerCase().includes(q) ||
      f.location.pin_code?.includes(q) ||
      f.facility_id.includes(q)
  );
}
