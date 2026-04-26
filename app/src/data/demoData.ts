export type CapabilityType =
  | 'SURGERY_APPENDECTOMY'
  | 'NEONATAL'
  | 'DIALYSIS'
  | 'ONCOLOGY'
  | 'TRAUMA';

export type EvidenceStance = 'verifies' | 'contradicts' | 'silent';
export type ContradictionSeverity = 'HIGH' | 'MEDIUM' | 'LOW';

export interface DemoEvidence {
  id: string;
  stance: EvidenceStance;
  snippet: string;
  sourceType: string;
  sourceDocId: string;
  span: string;
  sourceObservedAt: string;
  retrievedAt: string;
  rationale: string;
}

export interface DemoContradiction {
  id: string;
  severity: ContradictionSeverity;
  type: string;
  reasoning: string;
  evidenceFor: string;
  evidenceAgainst: string;
  detectedBy: string;
  detectedAt: string;
}

export interface DemoCapabilityAudit {
  id: CapabilityType;
  name: string;
  claimed: boolean;
  score: number;
  confidence: number;
  confidenceInterval: [number, number];
  evidenceCount: number;
  contradictionCount: number;
  reasoning: string;
  evidence: DemoEvidence[];
  contradictions: DemoContradiction[];
  computedAt: string;
}

export interface DemoFacility {
  id: string;
  name: string;
  locationLabel: string;
  pinCode: string;
  lat: number;
  lng: number;
  regionId: string;
  distanceKm: number;
  lastAuditedAt: string;
  totalContradictions: number;
  mlflowTraceId?: string;
  capabilities: DemoCapabilityAudit[];
}

export interface DemoRegionAggregate {
  id: string;
  name: string;
  state: string;
  capability: CapabilityType;
  pinCode: string;
  population: number;
  gapPopulation: number;
  coveredPopulation: number;
  coverageRatio: number;
  verifiedFacilitiesCount: number;
  flaggedFacilitiesCount: number;
  capabilityCountCi: [number, number];
  nearestVerifiedKm: number;
  generatedAt: string;
}

export interface DemoTraceSpan {
  id: string;
  label: string;
  toolName?: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'unavailable';
  durationMs?: number;
  detail: string;
  inputSummary?: string;
  outputSummary?: string;
  payload?: Record<string, unknown>;
}

export interface DemoQueryResult {
  query: string;
  queryTraceId: string;
  generatedAt: string;
  totalCandidates: number;
  parsedIntent: {
    capability: CapabilityType;
    location: string;
    lat: number;
    lng: number;
    pinCode: string;
    radiusKm: number;
    staffingConstraint?: string;
  };
  rankedFacilities: string[];
  spans: DemoTraceSpan[];
}

export interface DemoFundingCandidateRecommendation {
  facilityId: string;
  whyFund: string;
  trustRisk: string;
  missingResource: string;
  recommendedNextStep: string;
}

export interface DemoFundingPriorityRegion {
  regionId: string;
  name: string;
  capability: CapabilityType;
  priorityScore: number;
  needSignal: number;
  verifiedAccessScore: number;
  contradictionRisk: number;
  ruralityWeight: number;
  gapPopulation: number;
  nearestVerifiedKm: number;
  needLayerLabel: string;
  supplyLayerLabel: string;
  riskLayerLabel: string;
  regionSummary: string;
  fundingRationale: string;
  recommendedAction: string;
  recommendedFacilities: string[];
  candidateRecommendations: DemoFundingCandidateRecommendation[];
}

export const DEMO_QUERY = 'Which facilities within 50km of Patna can perform an appendectomy?';
export const CHALLENGE_QUERY =
  'Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors.';

export const CAPABILITIES: Array<{ id: CapabilityType; label: string }> = [
  { id: 'SURGERY_APPENDECTOMY', label: 'Appendectomy Surgery' },
  { id: 'NEONATAL', label: 'Neonatal Care' },
  { id: 'DIALYSIS', label: 'Dialysis' },
  { id: 'ONCOLOGY', label: 'Oncology' },
  { id: 'TRAUMA', label: 'Trauma' },
];

const appendectomyAudit: DemoCapabilityAudit = {
  id: 'SURGERY_APPENDECTOMY',
  name: 'Appendectomy Surgery',
  claimed: true,
  score: 72,
  confidence: 0.87,
  confidenceInterval: [65, 80],
  evidenceCount: 6,
  contradictionCount: 1,
  computedAt: '2026-04-25T14:32:00Z',
  reasoning:
    'Six documents verify active surgical capacity and part-time doctor staffing, but a HIGH MISSING_STAFF contradiction applies a 30-point penalty because the roster has no current anesthesiologist.',
  contradictions: [
    {
      id: 'contra-missing-staff',
      severity: 'HIGH',
      type: 'MISSING_STAFF',
      reasoning:
        'The facility claims appendectomy capability, but the current staff roster has no active anesthesiologist assigned to the surgical wing.',
      evidenceFor: 'claims-registry-2026:appendectomy-volume',
      evidenceAgainst: 'staff-roster-2026:anesthesia-gap',
      detectedBy: 'Validator Agent',
      detectedAt: '2026-04-25T14:30:20Z',
    },
  ],
  evidence: [
    {
      id: 'claims-registry-2026:appendectomy-volume',
      stance: 'verifies',
      snippet:
        'Patna Medical College reported 19 appendectomy procedures in Q1 2026 with no transfer-outs for general surgery.',
      sourceType: 'claims_registry',
      sourceDocId: 'claims-registry-2026',
      span: 'p12:l18-l22',
      sourceObservedAt: '2026-03-31T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:08Z',
      rationale: 'Recent procedure volume directly supports the claimed appendectomy capability.',
    },
    {
      id: 'equipment-inventory-2026:operating-theatre',
      stance: 'verifies',
      snippet:
        'Operating theatre 2 lists laparoscopic surgical tray, anesthesia workstation, and sterile recovery bay as available.',
      sourceType: 'equipment_inventory',
      sourceDocId: 'equipment-inventory-2026',
      span: 'p4:l7-l11',
      sourceObservedAt: '2026-04-05T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:14Z',
      rationale: 'Equipment inventory supports the facility being operational for abdominal surgery.',
    },
    {
      id: 'inspection-2026:general-surgery',
      stance: 'verifies',
      snippet:
        'General Surgery wing marked operational; elective and urgent procedures observed during March inspection.',
      sourceType: 'state_inspection',
      sourceDocId: 'inspection-2026',
      span: 'p2:l31-l36',
      sourceObservedAt: '2026-03-18T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:20Z',
      rationale: 'Inspection confirms the claimed surgical wing is active.',
    },
    {
      id: 'staffing-notes-2026:part-time-doctors',
      stance: 'verifies',
      snippet:
        'District staffing notes describe the surgical wing as typically leveraging part-time doctors for weekday emergency coverage.',
      sourceType: 'staffing_notes',
      sourceDocId: 'staffing-notes-2026',
      span: 'p3:l9-l14',
      sourceObservedAt: '2026-04-12T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:24Z',
      rationale: 'Directly supports the planner constraint that the facility leverages part-time doctors.',
    },
    {
      id: 'staff-roster-2026:anesthesia-gap',
      stance: 'contradicts',
      snippet:
        'No anesthesiologist listed as active. Dr. A. Sharma retired in 2023; replacement position remains vacant.',
      sourceType: 'staff_roster',
      sourceDocId: 'staff-roster-2026',
      span: 'p7:l4-l8',
      sourceObservedAt: '2026-04-01T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:27Z',
      rationale: 'Appendectomy requires anesthesia coverage; the roster contradicts safe current capability.',
    },
    {
      id: 'volume-report-2026:night-coverage',
      stance: 'silent',
      snippet: 'Night coverage section lists emergency nursing staff but does not identify on-call anesthesia coverage.',
      sourceType: 'volume_report',
      sourceDocId: 'volume-report-2026',
      span: 'p9:l1-l5',
      sourceObservedAt: '2026-04-10T00:00:00Z',
      retrievedAt: '2026-04-25T14:27:35Z',
      rationale: 'The source does not confirm whether appendectomy can be performed outside daytime staffing.',
    },
  ],
};

const neonatalAudit: DemoCapabilityAudit = {
  id: 'NEONATAL',
  name: 'Neonatal Care',
  claimed: true,
  score: 95,
  confidence: 0.95,
  confidenceInterval: [90, 98],
  evidenceCount: 8,
  contradictionCount: 0,
  computedAt: '2026-04-25T14:32:00Z',
  reasoning: 'Recent certification, equipment inventory, and staffing records consistently verify neonatal care.',
  contradictions: [],
  evidence: [
    {
      id: 'inspection-2026:nicu-certification',
      stance: 'verifies',
      snippet: 'NICU level-3 certification renewed through 2026 with neonatal ventilator inventory verified.',
      sourceType: 'state_inspection',
      sourceDocId: 'inspection-2026',
      span: 'p6:l12-l17',
      sourceObservedAt: '2026-03-18T00:00:00Z',
      retrievedAt: '2026-04-25T14:28:02Z',
      rationale: 'Certification directly verifies the neonatal capability.',
    },
  ],
};

function capabilityScore(
  id: CapabilityType,
  name: string,
  score: number,
  evidenceCount: number,
  contradictionCount = 0,
): DemoCapabilityAudit {
  return {
    id,
    name,
    claimed: score > 25,
    score,
    confidence: score / 100,
    confidenceInterval: [Math.max(0, score - 8), Math.min(100, score + 7)],
    evidenceCount,
    contradictionCount,
    computedAt: '2026-04-25T14:32:00Z',
    reasoning:
      score >= 80
        ? 'Multiple recent sources verify the capability with no high-severity contradictions.'
        : score >= 50
          ? 'Evidence is present, but one or more source gaps lower confidence.'
          : 'Evidence is insufficient or contradicted for this capability.',
    contradictions: [],
    evidence: [
      {
        id: `${id.toLowerCase()}:summary-evidence`,
        stance: score >= 50 ? 'verifies' : 'silent',
        snippet:
          score >= 50
            ? `${name} appears in recent inspection and service-volume records.`
            : `${name} was not confirmed in the available audit sources.`,
        sourceType: 'audit_summary',
        sourceDocId: `${id.toLowerCase()}-summary`,
        span: 'summary:l1-l3',
        sourceObservedAt: '2026-04-01T00:00:00Z',
        retrievedAt: '2026-04-25T14:28:30Z',
        rationale: score >= 50 ? 'Supports the capability at summary level.' : 'No confirming evidence found.',
      },
    ],
  };
}

export const FACILITIES: DemoFacility[] = [
  {
    id: 'facility_patna_medical',
    name: 'Patna Medical College',
    locationLabel: 'Patna, Bihar',
    pinCode: '800004',
    lat: 25.603,
    lng: 85.137,
    regionId: 'BR_PATNA',
    distanceKm: 12.4,
    lastAuditedAt: '2026-04-25T14:32:00Z',
    totalContradictions: 1,
    mlflowTraceId: 'mlf_facility_patna_medical_72',
    capabilities: [
      appendectomyAudit,
      neonatalAudit,
      capabilityScore('DIALYSIS', 'Dialysis', 61, 4),
      capabilityScore('ONCOLOGY', 'Oncology', 38, 1),
      capabilityScore('TRAUMA', 'Trauma', 47, 2),
    ],
  },
  {
    id: 'facility_nalanda_surgical',
    name: 'Nalanda Surgical Centre',
    locationLabel: 'Bihar Sharif, Bihar',
    pinCode: '803101',
    lat: 25.2,
    lng: 85.52,
    regionId: 'BR_PATNA',
    distanceKm: 34.2,
    lastAuditedAt: '2026-04-25T12:04:00Z',
    totalContradictions: 0,
    mlflowTraceId: 'mlf_facility_nalanda_surgical',
    capabilities: [
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 91, 9),
      capabilityScore('NEONATAL', 'Neonatal Care', 68, 5),
    ],
  },
  {
    id: 'facility_bihar_state_care',
    name: 'Bihar State Care Hospital',
    locationLabel: 'Danapur, Bihar',
    pinCode: '801503',
    lat: 25.62,
    lng: 85.04,
    regionId: 'BR_PATNA',
    distanceKm: 41.8,
    lastAuditedAt: '2026-04-24T19:16:00Z',
    totalContradictions: 2,
    mlflowTraceId: 'mlf_facility_bihar_state_care',
    capabilities: [
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 58, 4, 2),
      capabilityScore('TRAUMA', 'Trauma', 82, 7),
    ],
  },
  {
    id: 'facility_muzaffarpur_general',
    name: 'Muzaffarpur General Hospital',
    locationLabel: 'Muzaffarpur, Bihar',
    pinCode: '842001',
    lat: 26.12,
    lng: 85.39,
    regionId: 'BR_PATNA',
    distanceKm: 47.1,
    lastAuditedAt: '2026-04-24T09:50:00Z',
    totalContradictions: 1,
    mlflowTraceId: 'mlf_facility_muzaffarpur_general',
    capabilities: [
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 54, 3, 1),
      capabilityScore('DIALYSIS', 'Dialysis', 88, 8),
    ],
  },
  {
    id: 'facility_vaishali_community',
    name: 'Vaishali Community Hospital',
    locationLabel: 'Hajipur, Bihar',
    pinCode: '844101',
    lat: 25.69,
    lng: 85.21,
    regionId: 'BR_PATNA',
    distanceKm: 22.7,
    lastAuditedAt: '2026-04-23T17:38:00Z',
    totalContradictions: 0,
    mlflowTraceId: 'mlf_facility_vaishali_community',
    capabilities: [
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 66, 5),
      capabilityScore('NEONATAL', 'Neonatal Care', 75, 5),
    ],
  },
  {
    id: 'facility_madhubani_mission',
    name: 'Madhubani Mission Clinic',
    locationLabel: 'Madhubani, Bihar',
    pinCode: '847211',
    lat: 26.36,
    lng: 86.07,
    regionId: 'BR_MADHUBANI',
    distanceKm: 94,
    lastAuditedAt: '2026-04-23T10:12:00Z',
    totalContradictions: 2,
    mlflowTraceId: 'mlf_facility_madhubani_mission',
    capabilities: [
      capabilityScore('NEONATAL', 'Neonatal Care', 24, 1, 2),
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 35, 2, 1),
    ],
  },
  {
    id: 'facility_samastipur_care',
    name: 'Samastipur Care Trust',
    locationLabel: 'Samastipur, Bihar',
    pinCode: '848101',
    lat: 25.86,
    lng: 85.78,
    regionId: 'BR_PATNA',
    distanceKm: 49.6,
    lastAuditedAt: '2026-04-22T08:05:00Z',
    totalContradictions: 0,
    mlflowTraceId: 'mlf_facility_samastipur_care',
    capabilities: [
      capabilityScore('SURGERY_APPENDECTOMY', 'Appendectomy Surgery', 52, 3),
      capabilityScore('DIALYSIS', 'Dialysis', 71, 4),
    ],
  },
];

export const REGION_AGGREGATES: DemoRegionAggregate[] = [
  {
    id: 'BR_PATNA',
    name: 'Patna / Bihar Region',
    state: 'Bihar',
    capability: 'SURGERY_APPENDECTOMY',
    pinCode: '800001',
    population: 128000000,
    gapPopulation: 45000000,
    coveredPopulation: 83000000,
    coverageRatio: 0.65,
    verifiedFacilitiesCount: 2,
    flaggedFacilitiesCount: 3,
    capabilityCountCi: [1, 4],
    nearestVerifiedKm: 12,
    generatedAt: '2026-04-25T14:40:00Z',
  },
  {
    id: 'BR_MADHUBANI',
    name: 'Madhubani District',
    state: 'Bihar',
    capability: 'NEONATAL',
    pinCode: '847211',
    population: 4480000,
    gapPopulation: 312000,
    coveredPopulation: 4168000,
    coverageRatio: 0.93,
    verifiedFacilitiesCount: 0,
    flaggedFacilitiesCount: 2,
    capabilityCountCi: [0, 1],
    nearestVerifiedKm: 94,
    generatedAt: '2026-04-25T14:40:00Z',
  },
];

export const FUNDING_PRIORITY_REGIONS: DemoFundingPriorityRegion[] = [
  {
    regionId: 'BR_PATNA',
    name: 'Patna Appendectomy Catchment',
    capability: 'SURGERY_APPENDECTOMY',
    priorityScore: 68,
    needSignal: 0.74,
    verifiedAccessScore: 0.46,
    contradictionRisk: 0.66,
    ruralityWeight: 1.18,
    gapPopulation: 45000000,
    nearestVerifiedKm: 12,
    needLayerLabel: 'High emergency surgery burden',
    supplyLayerLabel: 'Mixed verified surgical access',
    riskLayerLabel: 'Staffing contradictions visible',
    regionSummary:
      'A dense catchment where surgical need is high, but verified emergency appendectomy capacity depends on resolving staffing contradictions.',
    fundingRationale:
      'High catchment population with several surgical claims, but audited supply is weakened by staffing contradictions and uneven verified coverage.',
    recommendedAction:
      'Prioritize facilities with verified surgical throughput, then fund staffing or anesthesia gaps before counting them as reliable emergency surgery capacity.',
    recommendedFacilities: [
      'facility_patna_medical',
      'facility_nalanda_surgical',
      'facility_vaishali_community',
      'facility_bihar_state_care',
    ],
    candidateRecommendations: [
      {
        facilityId: 'facility_patna_medical',
        whyFund: 'Closest high-volume surgical hub in the priority catchment.',
        trustRisk: 'Trust Score 72; one HIGH staffing contradiction remains visible.',
        missingResource: 'Verified anesthesia coverage for emergency appendectomy.',
        recommendedNextStep: 'Audit staffing before funding emergency surgery readiness.',
      },
      {
        facilityId: 'facility_nalanda_surgical',
        whyFund: 'Strong audited appendectomy evidence can anchor catchment referrals.',
        trustRisk: 'Trust Score 91 with no current contradiction flags.',
        missingResource: 'Referral and transport coverage for rural patients.',
        recommendedNextStep: 'Fund referral linkage if service volumes can absorb demand.',
      },
      {
        facilityId: 'facility_vaishali_community',
        whyFund: 'Adds secondary access within the Patna corridor.',
        trustRisk: 'Trust Score 66; evidence is present but not strong enough for sole reliance.',
        missingResource: 'Recent emergency surgery volume confirmation.',
        recommendedNextStep: 'Verify procedure logs before using as backup capacity.',
      },
      {
        facilityId: 'facility_bihar_state_care',
        whyFund: 'Could close a local access pocket if contradictions are resolved.',
        trustRisk: 'Trust Score 58 with two contradiction flags.',
        missingResource: 'Clean staff and equipment evidence for current capability.',
        recommendedNextStep: 'Hold capital funding until audit contradictions are cleared.',
      },
    ],
  },
  {
    regionId: 'BR_MADHUBANI',
    name: 'Rural Bihar Neonatal Priority Zone',
    capability: 'NEONATAL',
    priorityScore: 86,
    needSignal: 0.91,
    verifiedAccessScore: 0.18,
    contradictionRisk: 0.82,
    ruralityWeight: 1.34,
    gapPopulation: 312000,
    nearestVerifiedKm: 94,
    needLayerLabel: 'High newborn mortality burden',
    supplyLayerLabel: 'Very low verified neonatal access',
    riskLayerLabel: 'NICU readiness contradictions',
    regionSummary:
      'A high-priority neonatal gap where newborn need is high, verified local access is low, and nearby claims need equipment and staffing validation.',
    fundingRationale:
      'High newborn need signal with very low verified neonatal access. Local facilities either lack confirming NICU evidence or carry staffing and equipment gaps.',
    recommendedAction:
      'Treat this as a high-priority neonatal funding zone; validate equipment readiness and fund neonatal stabilization capacity before referral distance becomes fatal.',
    recommendedFacilities: [
      'facility_madhubani_mission',
      'facility_muzaffarpur_general',
      'facility_samastipur_care',
    ],
    candidateRecommendations: [
      {
        facilityId: 'facility_madhubani_mission',
        whyFund: 'Closest local facility in the neonatal priority zone.',
        trustRisk: 'Trust Score 24; neonatal claim has two contradictions.',
        missingResource: 'Verified NICU equipment and staffed neonatal coverage.',
        recommendedNextStep: 'Audit before funding; fund equipment only if staffing is confirmed.',
      },
      {
        facilityId: 'facility_muzaffarpur_general',
        whyFund: 'Nearest broader referral option for the rural catchment.',
        trustRisk: 'No verified neonatal audit in this mock result; surgical contradiction history remains relevant.',
        missingResource: 'Neonatal-specific audit evidence and referral capacity.',
        recommendedNextStep: 'Use as referral comparison, not as proof of local gap closure.',
      },
      {
        facilityId: 'facility_samastipur_care',
        whyFund: 'Potential support node for nearby rural clinics.',
        trustRisk: 'Current mock evidence verifies other capabilities, not neonatal readiness.',
        missingResource: 'Documented neonatal stabilization staff and equipment.',
        recommendedNextStep: 'Request neonatal audit before ranking as fundable capacity.',
      },
    ],
  },
  {
    regionId: 'BR_STATE',
    name: 'Bihar State Background',
    capability: 'NEONATAL',
    priorityScore: 52,
    needSignal: 0.62,
    verifiedAccessScore: 0.44,
    contradictionRisk: 0.48,
    ruralityWeight: 1.08,
    gapPopulation: 12800000,
    nearestVerifiedKm: 47,
    needLayerLabel: 'Moderate statewide newborn burden',
    supplyLayerLabel: 'Uneven verified neonatal access',
    riskLayerLabel: 'Mixed self-report reliability',
    regionSummary:
      'A statewide context layer showing mixed access: urban corridors look stronger while rural districts still require contradiction-aware drilldown.',
    fundingRationale:
      'Statewide access is mixed: urban corridors show stronger verified care, while rural districts remain sensitive to staffing and equipment contradictions.',
    recommendedAction:
      'Use district-level drilldown to separate credible referral hubs from facilities that only self-report capabilities.',
    recommendedFacilities: [
      'facility_patna_medical',
      'facility_vaishali_community',
      'facility_madhubani_mission',
    ],
    candidateRecommendations: [
      {
        facilityId: 'facility_patna_medical',
        whyFund: 'Reliable referral benchmark for statewide neonatal access.',
        trustRisk: 'Trust Score 95 for neonatal care with no contradictions.',
        missingResource: 'Rural reach and transport linkage, not core capability.',
        recommendedNextStep: 'Use as verified supply anchor when comparing district gaps.',
      },
      {
        facilityId: 'facility_vaishali_community',
        whyFund: 'Credible secondary corridor capacity.',
        trustRisk: 'Trust Score 75 with no current contradiction flags.',
        missingResource: 'Expanded rural referral coverage.',
        recommendedNextStep: 'Validate catchment coverage before assigning grant impact.',
      },
      {
        facilityId: 'facility_madhubani_mission',
        whyFund: 'Shows where local rural capacity could reduce referral distance.',
        trustRisk: 'Trust Score 24; contradiction risk is high.',
        missingResource: 'Verified NICU readiness.',
        recommendedNextStep: 'Treat as an audit-first opportunity.',
      },
    ],
  },
];

export const APPENDECTOMY_QUERY_RESULT: DemoQueryResult = {
  query: DEMO_QUERY,
  queryTraceId: 'query_appendectomy_patna_50km',
  generatedAt: '2026-04-25T14:41:11Z',
  totalCandidates: 34,
  parsedIntent: {
    capability: 'SURGERY_APPENDECTOMY',
    location: 'Patna',
    lat: 25.61,
    lng: 85.14,
    pinCode: '800001',
    radiusKm: 50,
  },
  rankedFacilities: [
    'facility_nalanda_surgical',
    'facility_patna_medical',
    'facility_vaishali_community',
    'facility_bihar_state_care',
    'facility_muzaffarpur_general',
    'facility_samastipur_care',
    'facility_madhubani_mission',
  ],
  spans: [
    {
      id: 'span-parse',
      label: 'parse_intent',
      toolName: 'parse_intent',
      status: 'complete',
      durationMs: 420,
      detail: 'Capability appendectomy, Patna, 50km radius.',
      inputSummary: DEMO_QUERY,
      outputSummary: 'SURGERY_APPENDECTOMY / Patna / 50km',
      payload: { capability: 'SURGERY_APPENDECTOMY', location: 'Patna', radiusKm: 50 },
    },
    {
      id: 'span-geocode',
      label: 'geocode',
      toolName: 'geocode',
      status: 'complete',
      durationMs: 280,
      detail: 'Resolved Patna to 25.61, 85.14 and PIN 800001.',
      inputSummary: 'Patna',
      outputSummary: '25.61, 85.14 / PIN 800001',
      payload: { lat: 25.61, lng: 85.14, pinCode: '800001' },
    },
    {
      id: 'span-search',
      label: 'search_facilities',
      toolName: 'search_facilities',
      status: 'complete',
      durationMs: 910,
      detail: '34 candidates within radius before audit filtering.',
      inputSummary: '50km radius around Patna',
      outputSummary: '34 candidates',
      payload: { candidates: 34, radiusKm: 50 },
    },
    {
      id: 'span-audit',
      label: 'get_facility_audit',
      toolName: 'get_facility_audit',
      status: 'complete',
      durationMs: 780,
      detail: 'Fetched canonical FacilityAudit records from mock gold table.',
      inputSummary: 'Top regional candidates',
      outputSummary: '7 audits loaded',
      payload: { auditsLoaded: 7 },
    },
    {
      id: 'span-rank',
      label: 'rank_results',
      toolName: 'rank_results',
      status: 'complete',
      durationMs: 190,
      detail: 'Ranked by Trust Score descending, then distance ascending.',
      inputSummary: 'Trust Score + distance',
      outputSummary: 'Nalanda Surgical Centre ranked #1',
      payload: { primarySort: 'trust_score_desc', tieBreaker: 'distance_asc' },
    },
  ],
};

export const CHALLENGE_QUERY_RESULT: DemoQueryResult = {
  query: CHALLENGE_QUERY,
  queryTraceId: 'query_rural_bihar_appendectomy_staffing',
  generatedAt: '2026-04-25T14:43:18Z',
  totalCandidates: 34,
  parsedIntent: {
    capability: 'SURGERY_APPENDECTOMY',
    location: 'rural Bihar',
    lat: 25.61,
    lng: 85.14,
    pinCode: '800001',
    radiusKm: 50,
    staffingConstraint: 'part_time_doctors',
  },
  rankedFacilities: [
    'facility_patna_medical',
    'facility_nalanda_surgical',
    'facility_vaishali_community',
    'facility_bihar_state_care',
    'facility_muzaffarpur_general',
    'facility_samastipur_care',
    'facility_madhubani_mission',
  ],
  spans: [
    {
      id: 'challenge-parse',
      label: 'parse_intent',
      toolName: 'parse_intent',
      status: 'complete',
      durationMs: 440,
      detail: 'Parsed appendectomy capability, rural Bihar location, and part-time doctor staffing constraint.',
      inputSummary: CHALLENGE_QUERY,
      outputSummary: 'SURGERY_APPENDECTOMY / rural Bihar / part_time_doctors',
      payload: { capability: 'SURGERY_APPENDECTOMY', location: 'rural Bihar', staffingConstraint: 'part_time_doctors' },
    },
    {
      id: 'challenge-geocode',
      label: 'geocode',
      toolName: 'geocode',
      status: 'complete',
      durationMs: 310,
      detail: 'Loaded Bihar focus with Patna fallback centroid and PIN context.',
      inputSummary: 'rural Bihar',
      outputSummary: 'Bihar focus / Patna fallback centroid / PIN 800001',
      payload: { focus: 'Bihar', fallbackCentroid: [25.61, 85.14], pinCode: '800001' },
    },
    {
      id: 'challenge-capability',
      label: 'set_capability',
      toolName: 'set_capability',
      status: 'complete',
      durationMs: 90,
      detail: 'Set map capability filter to emergency appendectomy.',
      inputSummary: 'emergency appendectomy',
      outputSummary: 'SURGERY_APPENDECTOMY',
      payload: { capability: 'SURGERY_APPENDECTOMY' },
    },
    {
      id: 'challenge-radius',
      label: 'set_radius',
      toolName: 'set_radius',
      status: 'complete',
      durationMs: 70,
      detail: 'Applied default 50km planning radius for Bihar demo.',
      inputSummary: 'No explicit radius',
      outputSummary: '50km',
      payload: { radiusKm: 50 },
    },
    {
      id: 'challenge-search',
      label: 'search_facilities',
      toolName: 'search_facilities',
      status: 'complete',
      durationMs: 940,
      detail: 'Found 34 candidate facilities within the Bihar planning context.',
      inputSummary: 'Bihar / appendectomy / 50km',
      outputSummary: '34 candidates',
      payload: { candidates: 34, radiusKm: 50 },
    },
    {
      id: 'challenge-audit',
      label: 'get_facility_audit',
      toolName: 'get_facility_audit',
      status: 'complete',
      durationMs: 810,
      detail: 'Loaded seven canonical audits for ranked candidate review.',
      inputSummary: 'Candidate facility ids',
      outputSummary: '7 FacilityAudit records',
      payload: { auditsLoaded: 7 },
    },
    {
      id: 'challenge-staffing',
      label: 'validate_staffing',
      toolName: 'validate_staffing',
      status: 'complete',
      durationMs: 520,
      detail: 'Found part-time doctor notes and a HIGH missing anesthesiologist contradiction.',
      inputSummary: 'part_time_doctors constraint',
      outputSummary: 'Part-time notes verified / HIGH MISSING_STAFF',
      payload: { staffingConstraint: 'part_time_doctors', contradiction: 'MISSING_STAFF', severity: 'HIGH' },
    },
    {
      id: 'challenge-rank',
      label: 'rank_results',
      toolName: 'rank_results',
      status: 'complete',
      durationMs: 210,
      detail: 'Ranked the nearest staffing-matching facility first, with Trust Score 72 and one HIGH contradiction visible.',
      inputSummary: 'Trust Score, distance, staffing evidence, contradictions',
      outputSummary: 'Patna Medical College ranked #1 / Trust Score 72',
      payload: { topFacilityId: 'facility_patna_medical', trustScore: 72, highContradictions: 1 },
    },
    {
      id: 'challenge-update-map',
      label: 'update_map',
      toolName: 'update_map',
      status: 'complete',
      durationMs: 160,
      detail: 'Focused Bihar/Patna, highlighted seven candidates, and selected Patna Medical College.',
      inputSummary: 'Ranked results',
      outputSummary: 'Map focus updated / 7 highlights',
      payload: { selectedRegionId: 'BR_PATNA', highlightedFacilities: 7 },
    },
  ],
};

export const FACILITY_TRACE_SPANS: DemoTraceSpan[] = [
  {
    id: 'extract',
    label: 'Extraction',
    toolName: 'extract_claims',
    status: 'complete',
    durationMs: 1200,
    detail: 'Extractor found appendectomy, neonatal, and dialysis claims.',
  },
  {
    id: 'validate',
    label: 'Validation',
    toolName: 'validate_claims',
    status: 'complete',
    durationMs: 840,
    detail: 'Validator compared claims against staff, equipment, and volume reports.',
  },
  {
    id: 'score',
    label: 'Trust scoring',
    toolName: 'score_trust',
    status: 'complete',
    durationMs: 310,
    detail: 'Applied HIGH severity penalty for missing anesthesia coverage.',
  },
  {
    id: 'build',
    label: 'FacilityAudit build',
    toolName: 'build_facility_audit',
    status: 'complete',
    durationMs: 160,
    detail: 'Assembled canonical audit record with evidence and trace id.',
  },
];

export function getCapabilityLabel(capability: CapabilityType) {
  return CAPABILITIES.find((item) => item.id === capability)?.label ?? capability;
}

export function getFacilityById(id?: string) {
  return FACILITIES.find((facility) => facility.id === id);
}

export function getCapabilityAudit(facility: DemoFacility, capability: CapabilityType) {
  return facility.capabilities.find((item) => item.id === capability);
}

export function getRankedFacilities(result = APPENDECTOMY_QUERY_RESULT) {
  return result.rankedFacilities.map((id) => getFacilityById(id)).filter(Boolean) as DemoFacility[];
}

export function getFacilityScore(facility: DemoFacility, capability: CapabilityType) {
  return getCapabilityAudit(facility, capability)?.score ?? 0;
}

export function getFacilityRowsForRegion(regionId: string, capability: CapabilityType) {
  return FACILITIES.filter((facility) => facility.regionId === regionId && getCapabilityAudit(facility, capability))
    .sort((a, b) => getFacilityScore(b, capability) - getFacilityScore(a, capability) || a.distanceKm - b.distanceKm);
}

export function getRegionAggregate(regionId = 'BR_PATNA', capability: CapabilityType = 'SURGERY_APPENDECTOMY') {
  return (
    REGION_AGGREGATES.find((region) => region.id === regionId && region.capability === capability) ??
    REGION_AGGREGATES.find((region) => region.id === regionId) ??
    REGION_AGGREGATES[0]
  );
}

export function getFundingPriorityRegion(regionId = 'BR_PATNA', capability?: CapabilityType) {
  return (
    FUNDING_PRIORITY_REGIONS.find((region) => region.regionId === regionId && (!capability || region.capability === capability)) ??
    FUNDING_PRIORITY_REGIONS.find((region) => region.regionId === regionId) ??
    FUNDING_PRIORITY_REGIONS[0]
  );
}

export function getFundingCandidateRecommendation(region: DemoFundingPriorityRegion, facilityId: string) {
  return region.candidateRecommendations.find((candidate) => candidate.facilityId === facilityId);
}

export function parseDemoCommand(input: string) {
  const lowered = input.toLowerCase();
  const capability: CapabilityType = lowered.includes('neonatal')
    ? 'NEONATAL'
    : lowered.includes('dialysis')
      ? 'DIALYSIS'
      : lowered.includes('oncology')
        ? 'ONCOLOGY'
        : lowered.includes('trauma')
          ? 'TRAUMA'
          : 'SURGERY_APPENDECTOMY';
  const radiusMatch = lowered.match(/(\d+)\s?km/);
  const radiusKm = radiusMatch ? Number(radiusMatch[1]) : capability === 'SURGERY_APPENDECTOMY' ? 50 : 60;
  const pinMatch = input.match(/\b\d{6}\b/);
  const regionId = lowered.includes('madhubani') || pinMatch?.[0] === '847211' || capability === 'NEONATAL' ? 'BR_MADHUBANI' : 'BR_PATNA';
  const pinCode = pinMatch?.[0] ?? (regionId === 'BR_MADHUBANI' ? '847211' : '800001');
  const staffingConstraint = lowered.includes('part-time') || lowered.includes('part time') ? 'part_time_doctors' : undefined;
  const location = lowered.includes('rural bihar') ? 'rural Bihar' : pinMatch ? `PIN ${pinMatch[0]}` : regionId === 'BR_MADHUBANI' ? 'Madhubani' : 'Patna';
  return {
    capability,
    radiusKm,
    regionId,
    pinCode,
    staffingConstraint,
    location,
  };
}

export function getQueryResultForCommand(input: string) {
  const lowered = input.toLowerCase();
  if (lowered.includes('rural bihar') || lowered.includes('part-time') || lowered.includes('part time')) {
    return CHALLENGE_QUERY_RESULT;
  }
  return APPENDECTOMY_QUERY_RESULT;
}

export function formatNumber(value: number) {
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return String(value);
}
