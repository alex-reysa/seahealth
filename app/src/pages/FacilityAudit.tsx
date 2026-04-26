import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, MapPin, ShieldAlert, Activity } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { EvidenceCard, type EvidenceStance } from '@/src/components/domain/EvidenceCard';
import { ContradictionBanner } from '@/src/components/domain/ContradictionBanner';
import { TraceClassBadge } from '@/src/components/domain/TraceClassBadge';
import { AsyncBoundary } from '@/src/components/domain/AsyncBoundary';
import { useFacilityAudit } from '@/src/hooks/useFacilityAudit';
import type {
  Capability,
  CapabilityType,
  Contradiction,
  EvidenceRef,
  FacilityAudit as FacilityAuditModel,
  TrustScore as TrustScoreModel,
} from '@/src/types/api';
import { cn } from '@/src/lib/utils';

const CAPABILITY_LABELS: Partial<Record<CapabilityType, string>> = {
  ICU: 'Intensive Care', SURGERY_GENERAL: 'General Surgery', SURGERY_APPENDECTOMY: 'Appendectomy Surgery',
  DIALYSIS: 'Dialysis', ONCOLOGY: 'Oncology', NEONATAL: 'Neonatal Care', TRAUMA: 'Trauma',
  MATERNAL: 'Maternal Care', RADIOLOGY: 'Radiology', LAB: 'Laboratory', PHARMACY: 'Pharmacy',
  EMERGENCY_24_7: '24x7 Emergency',
};
const getCapabilityLabel = (c: CapabilityType): string => CAPABILITY_LABELS[c] ?? c;
const STANCE_ORDER: EvidenceStance[] = ['contradicts', 'verifies', 'silent'];
const SEVERITY_RANK: Record<Contradiction['severity'], number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

interface AnnotatedEvidence { evidence: EvidenceRef; stance: EvidenceStance; key: string; }

// Stance is derived: "contradicts" if a ref appears in any contradiction's evidence_against, else "verifies".
const refKey = (r: EvidenceRef) => `${r.source_doc_id}::${r.chunk_id}::${r.span?.[0] ?? 0}-${r.span?.[1] ?? 0}`;
function annotateEvidence(trust: TrustScoreModel): AnnotatedEvidence[] {
  const againstKeys = new Set<string>();
  for (const c of trust.contradictions) for (const r of c.evidence_against ?? []) againstKeys.add(refKey(r));
  const seen = new Set<string>();
  const out: AnnotatedEvidence[] = [];
  const refs = [...trust.evidence, ...trust.contradictions.flatMap((c) => c.evidence_against ?? [])];
  for (const ref of refs) {
    const key = refKey(ref);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ evidence: ref, key, stance: againstKeys.has(key) ? 'contradicts' : 'verifies' });
  }
  return out;
}

/** Pure "Why recommended" rationale; deterministic, per Phase 3 spec. */
export function buildRecommendationRationale(trust: TrustScoreModel, totalContradictions: number): string {
  const hasHigh = trust.contradictions.some((c) => c.severity === 'HIGH');
  const n = trust.evidence.length;
  const s = n === 1 ? '' : 's';
  if (trust.score >= 80 && !hasHigh) return `High-confidence verified — ${n} supporting source${s}, no high-severity flags.`;
  if (trust.score >= 50 && hasHigh) return 'Mixed signal — capability is claimed and partially verified, but a high-severity contradiction remains visible.';
  if (trust.score < 50) return 'Low confidence — verify in person before relying on this audit.';
  const flag = totalContradictions > 0 ? ` ${totalContradictions} flagged across audit.` : '';
  return `Moderate confidence — partial verification with ${n} supporting source${s}.${flag}`;
}

interface CapabilityRow { type: CapabilityType; label: string; claimed: boolean; trust?: TrustScoreModel; }

function getCapabilityRows(audit: FacilityAuditModel): CapabilityRow[] {
  const claimedSet = new Set(audit.capabilities.filter((c) => c.claimed).map((c) => c.capability_type));
  const allTypes = [...new Set<CapabilityType>([
    ...audit.capabilities.map((c) => c.capability_type),
    ...(Object.keys(audit.trust_scores) as CapabilityType[]),
  ])];
  return allTypes.map((type) => ({
    type, label: getCapabilityLabel(type), claimed: claimedSet.has(type), trust: audit.trust_scores[type],
  }));
}

function pickDefaultCapability(audit: FacilityAuditModel, rows: CapabilityRow[], param: CapabilityType | null): CapabilityType | undefined {
  if (param && audit.trust_scores[param]) return param;
  return (
    rows.find((r) => r.trust?.contradictions.some((c) => c.severity === 'HIGH'))?.type ??
    rows.find((r) => r.claimed && r.trust)?.type ??
    rows.find((r) => r.trust)?.type ??
    rows[0]?.type
  );
}

interface FacilityAuditViewProps {
  audit: FacilityAuditModel;
  capabilityParam: CapabilityType | null;
  from: string | null;
  q: string | null;
}

function FacilityAuditView({ audit, capabilityParam, from, q }: FacilityAuditViewProps) {
  const navigate = useNavigate();
  const rows = React.useMemo(() => getCapabilityRows(audit), [audit]);
  const defaultCapability = React.useMemo(
    () => pickDefaultCapability(audit, rows, capabilityParam),
    [audit, rows, capabilityParam],
  );
  const [selectedType, setSelectedType] = React.useState<CapabilityType | undefined>(defaultCapability);

  React.useEffect(() => {
    setSelectedType(defaultCapability);
  }, [defaultCapability]);

  const selectedTrust = selectedType ? audit.trust_scores[selectedType] : undefined;
  const selectedRow = rows.find((r) => r.type === selectedType);
  const selectedCapabilityRecord: Capability | undefined = audit.capabilities.find(
    (c) => c.capability_type === selectedType,
  );

  const handleBack = () => {
    if (from === 'planner-query') {
      navigate(q ? `/planner-query?q=${encodeURIComponent(q)}` : '/planner-query');
    } else if (from === 'dashboard' || from === 'desert-map' || from === 'map-workbench') {
      navigate('/');
    } else {
      navigate(-1);
    }
  };

  const backLabel = q ? `← Back to results for "${q}"` : '← Back';

  return (
    <div className="flex flex-col h-full overflow-hidden bg-surface-canvas">
      <div className="p-6 border-b border-border-subtle bg-white shrink-0">
        <div className="flex items-start justify-between gap-6">
          <div className="flex items-start gap-4">
            <Button variant="ghost" onClick={handleBack} className="p-2 -ml-2 text-content-tertiary hover:text-content-primary">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <div className="text-caption text-content-secondary mb-2">
                {from || q ? backLabel : 'Direct audit view'}
              </div>
              <div className="flex items-center gap-3">
                <h1 className="text-heading-l text-content-primary">{audit.name}</h1>
                {audit.total_contradictions > 0 && (
                  <div className="inline-flex items-center gap-1.5 text-semantic-critical bg-semantic-critical-subtle px-2.5 py-1 rounded-sm text-caption font-semibold">
                    <ShieldAlert className="w-4 h-4" />
                    {audit.total_contradictions} Contradictions
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4 mt-1 text-caption text-content-secondary flex-wrap">
                <span className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5" />
                  {audit.location.lat.toFixed(4)}, {audit.location.lng.toFixed(4)}
                  {audit.location.pin_code ? ` · PIN ${audit.location.pin_code}` : ''}
                </span>
                <span>·</span>
                <span className="flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" /> Audited: {new Date(audit.last_audited_at).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
          <div className="min-w-72 flex flex-col items-end gap-2">
            <TraceClassBadge traceId={audit.mlflow_trace_id} />
            {selectedCapabilityRecord?.extractor_model && (
              <span className="text-caption text-content-secondary">
                Extractor: <code className="font-mono">{selectedCapabilityRecord.extractor_model}</code>
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-[360px] shrink-0 border-r border-border-subtle bg-surface-canvas overflow-y-auto">
          <div className="p-4">
            <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-4 px-2">
              Capabilities
            </h3>
            <div className="flex flex-col gap-2">
              {rows.length === 0 ? (
                <div className="p-4 text-caption text-content-secondary">No capabilities recorded.</div>
              ) : (
                rows.map((row) => (
                  <CapabilityListItem
                    key={row.type}
                    row={row}
                    selected={selectedType === row.type}
                    onSelect={() => setSelectedType(row.type)}
                  />
                ))
              )}
            </div>
          </div>
        </aside>

        <main className="flex-1 bg-white overflow-y-auto">
          {selectedTrust && selectedRow ? (
            <SelectedCapabilityPanel
              row={selectedRow}
              trust={selectedTrust}
              totalContradictions={audit.total_contradictions}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-content-tertiary">
              {rows.length === 0
                ? 'No capabilities to display.'
                : 'Select a capability to view its audit trail.'}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

interface CapabilityListItemProps {
  key?: React.Key;
  row: CapabilityRow;
  selected: boolean;
  onSelect: () => void;
}

function CapabilityListItem({ row, selected, onSelect }: CapabilityListItemProps) {
  const score = row.trust?.score ?? 0;
  const evidenceCount = row.trust?.evidence.length ?? 0;
  const contradictionCount = row.trust?.contradictions.length ?? 0;
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'text-left p-4 rounded-lg border cursor-pointer transition-all',
        selected
          ? 'bg-white border-border-strong shadow-elevation-1'
          : 'bg-transparent border-transparent hover:bg-surface-sunken hover:border-border-subtle',
      )}
    >
      <div className="flex justify-between items-start gap-3 mb-2">
        <div className="flex flex-col gap-1">
          <span className="text-body-l font-medium text-content-primary">{row.label}</span>
          {row.claimed ? (
            <span className="text-semantic-verified flex items-center gap-1 text-caption">
              <CheckCircle2 className="w-3 h-3" /> Claimed
            </span>
          ) : (
            <span className="text-content-tertiary text-caption">Not Claimed</span>
          )}
        </div>
        {row.trust && (
          <TrustScore score={score} confidenceInterval={row.trust.confidence_interval} showLabel={false} />
        )}
      </div>
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border-subtle">
        <div className="text-caption text-content-secondary">
          <span className="font-semibold text-content-primary">{evidenceCount}</span> evidence
        </div>
        <div className="w-px h-3 bg-border-default" />
        <div className={cn(
          'text-caption',
          contradictionCount > 0 ? 'text-semantic-critical font-medium' : 'text-content-secondary',
        )}>
          {contradictionCount} contradictions
        </div>
      </div>
    </button>
  );
}

interface SelectedCapabilityPanelProps {
  row: CapabilityRow;
  trust: TrustScoreModel;
  totalContradictions: number;
}

function SelectedCapabilityPanel({ row, trust, totalContradictions }: SelectedCapabilityPanelProps) {
  const rationale = React.useMemo(
    () => buildRecommendationRationale(trust, totalContradictions),
    [trust, totalContradictions],
  );
  const annotated = React.useMemo(() => annotateEvidence(trust), [trust]);
  const sortedContradictions = React.useMemo(
    () => sortContradictions(trust.contradictions),
    [trust.contradictions],
  );

  return (
    <div className="p-8">
      <div className="flex items-start justify-between gap-6 mb-6">
        <div>
          <div className="text-caption text-content-secondary uppercase tracking-wider">Selected audit claim</div>
          <h2 className="text-heading-l mt-1">{row.label}</h2>
        </div>
        <TrustScore score={trust.score} confidenceInterval={trust.confidence_interval} />
      </div>

      <Card variant="glass" className="p-4 mb-4 bg-surface-canvas-tint">
        <div className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-1">
          Why recommended
        </div>
        <p className="text-body text-content-primary">{rationale}</p>
      </Card>

      <Card variant="glass" className="p-4 mb-8 bg-surface-canvas-tint">
        <div className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-1">
          Trust Score Reasoning
        </div>
        <p className="text-body text-content-primary">{trust.reasoning}</p>
        <p className="text-caption text-content-secondary mt-3">
          Score = round(confidence × 100) − severity penalties. HIGH contradictions carry a 30-point penalty.
        </p>
      </Card>

      <section className="mb-8">
        <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-3">
          Contradictions
        </h3>
        {sortedContradictions.length === 0 ? (
          <div className="p-4 rounded-md border border-border-subtle bg-surface-sunken/60 text-body text-content-secondary">
            No contradictions found for this claim.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {sortedContradictions.map((c, idx) => (
              <ContradictionBanner key={`${c.contradiction_type}-${idx}`} contradiction={c} />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-5">
        <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Evidence Trail</h3>
        {annotated.length === 0 ? (
          <div className="p-4 rounded-md border border-border-subtle bg-surface-sunken/60 text-body text-content-secondary">
            No evidence captured for this claim.
          </div>
        ) : (
          STANCE_ORDER.map((stance) => {
            const items = annotated.filter((a) => a.stance === stance);
            if (items.length === 0) return null;
            return (
              <div key={stance} className="flex flex-col gap-3">
                <div className="text-heading-s capitalize text-content-primary">
                  {stance === 'silent' ? 'Silent / No confirming evidence found' : stance}
                </div>
                {items.map((item) => (
                  <EvidenceCard key={item.key} evidence={item.evidence} stance={item.stance} />
                ))}
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}

const sortContradictions = (items: Contradiction[]): Contradiction[] =>
  [...items].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);

export function FacilityAudit() {
  const { facility_id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const from = searchParams.get('from');
  const q = searchParams.get('q');
  const capabilityParam = searchParams.get('capability') as CapabilityType | null;
  const { data, error, status, refetch } = useFacilityAudit(facility_id);

  const handleBack = () => {
    if (from === 'planner-query') {
      navigate(q ? `/planner-query?q=${encodeURIComponent(q)}` : '/planner-query');
    } else {
      navigate(-1);
    }
  };

  return (
    <AsyncBoundary
      status={status}
      data={data}
      error={error}
      context="facility audit"
      onRetry={refetch}
      empty={
        <div className="h-full flex items-center justify-center bg-surface-canvas p-8">
          <Card variant="glass-elevated" className="max-w-md p-8 text-center">
            <h1 className="text-heading-l mb-2">Facility audit unavailable</h1>
            <p className="text-body text-content-secondary mb-6">
              The backend has no audit record for <code className="font-mono">{facility_id}</code>.
            </p>
            <Button onClick={handleBack}>Back</Button>
          </Card>
        </div>
      }
    >
      {(audit) => (
        <FacilityAuditView audit={audit} capabilityParam={capabilityParam} from={from} q={q} />
      )}
    </AsyncBoundary>
  );
}
