import React from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, MapPin, ShieldAlert, Activity } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { EvidenceCard } from '@/src/components/domain/EvidenceCard';
import { ContradictionBanner } from '@/src/components/domain/ContradictionBanner';
import { TracePanel } from '@/src/components/domain/TracePanel';
import {
  FACILITY_TRACE_SPANS,
  type CapabilityType,
  type EvidenceStance,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityById,
} from '@/src/data/demoData';
import { cn } from '@/src/lib/utils';

const STANCE_ORDER: EvidenceStance[] = ['contradicts', 'verifies', 'silent'];

export function FacilityAudit() {
  const { facility_id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const from = searchParams.get('from');
  const q = searchParams.get('q');
  const capabilityParam = searchParams.get('capability') as CapabilityType | null;
  const facility = getFacilityById(facility_id);

  const defaultCapability = React.useMemo(() => {
    if (!facility) return undefined;
    const withHigh = facility.capabilities.find((capability) => capability.contradictions.some((item) => item.severity === 'HIGH'));
    return withHigh?.id ?? facility.capabilities.find((capability) => capability.claimed)?.id ?? facility.capabilities[0]?.id;
  }, [facility]);

  const [selectedCapabilityId, setSelectedCapabilityId] = React.useState<CapabilityType | undefined>(capabilityParam ?? defaultCapability);

  React.useEffect(() => {
    setSelectedCapabilityId(capabilityParam ?? defaultCapability);
  }, [capabilityParam, defaultCapability]);

  if (!facility) {
    return (
      <div className="h-full flex items-center justify-center bg-surface-canvas p-8">
        <Card variant="glass-elevated" className="max-w-md p-8 text-center">
          <h1 className="text-heading-l mb-2">Facility audit unavailable</h1>
          <p className="text-body text-content-secondary mb-6">No mock FacilityAudit record exists for `{facility_id}`.</p>
          <Button onClick={() => navigate('/planner-query')}>Back to Planner Query</Button>
        </Card>
      </div>
    );
  }

  const selectedCapability = selectedCapabilityId ? getCapabilityAudit(facility, selectedCapabilityId) : undefined;

  const handleBack = () => {
    const capability = selectedCapabilityId ?? 'SURGERY_APPENDECTOMY';
    if (from === 'desert-map') {
      navigate(`/desert-map?capability=${capability}&radius_km=50&region_id=${facility.regionId}`);
    } else if (from === 'planner-query') {
      navigate(q ? `/planner-query?q=${encodeURIComponent(q)}` : '/planner-query');
    } else if (from === 'dashboard') {
      navigate(`/?capability=${capability}&radius_km=50&region_id=${facility.regionId}&pin_code=${facility.pinCode}`);
    } else {
      navigate(-1);
    }
  };

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
                {from ? `Back target: ${from}` : 'Direct audit view'}
              </div>
              <div className="flex items-center gap-3">
                <h1 className="text-heading-l text-content-primary">{facility.name}</h1>
                {facility.totalContradictions > 0 && (
                  <div className="inline-flex items-center gap-1.5 text-semantic-critical bg-semantic-critical-subtle px-2.5 py-1 rounded-sm text-caption font-semibold">
                    <ShieldAlert className="w-4 h-4" />
                    {facility.totalContradictions} Contradictions
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4 mt-1 text-caption text-content-secondary">
                <span className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5" /> {facility.locationLabel} · PIN {facility.pinCode}
                </span>
                <span>·</span>
                <span className="flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" /> Audited: {new Date(facility.lastAuditedAt).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
          <div className="min-w-72">
            <TracePanel mlflowTraceId={facility.mlflowTraceId} spans={FACILITY_TRACE_SPANS} />
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-[360px] shrink-0 border-r border-border-subtle bg-surface-canvas overflow-y-auto">
          <div className="p-4">
            <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-4 px-2">Claimed Capabilities</h3>
            <div className="flex flex-col gap-2">
              {facility.capabilities.map((capability) => {
                const isSelected = selectedCapabilityId === capability.id;
                return (
                  <button
                    type="button"
                    key={capability.id}
                    onClick={() => setSelectedCapabilityId(capability.id)}
                    className={cn(
                      'text-left p-4 rounded-lg border cursor-pointer transition-all',
                      isSelected ? 'bg-white border-border-strong shadow-elevation-1' : 'bg-transparent border-transparent hover:bg-surface-sunken hover:border-border-subtle',
                    )}
                  >
                    <div className="flex justify-between items-start gap-3 mb-2">
                      <div className="flex flex-col gap-1">
                        <span className="text-body-l font-medium text-content-primary">{capability.name}</span>
                        {capability.claimed ? (
                          <span className="text-semantic-verified flex items-center gap-1 text-caption">
                            <CheckCircle2 className="w-3 h-3" /> Claimed
                          </span>
                        ) : (
                          <span className="text-content-tertiary text-caption">Not Claimed</span>
                        )}
                      </div>
                      <TrustScore score={capability.score} confidenceInterval={capability.confidenceInterval} showLabel={false} />
                    </div>
                    <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border-subtle">
                      <div className="text-caption text-content-secondary">
                        <span className="font-semibold text-content-primary">{capability.evidenceCount}</span> evidence
                      </div>
                      <div className="w-px h-3 bg-border-default" />
                      <div className={cn('text-caption', capability.contradictionCount > 0 ? 'text-semantic-critical font-medium' : 'text-content-secondary')}>
                        {capability.contradictionCount} contradictions
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <main className="flex-1 bg-white overflow-y-auto">
          {selectedCapability ? (
            <div className="p-8">
              <div className="flex items-start justify-between gap-6 mb-6">
                <div>
                  <div className="text-caption text-content-secondary uppercase tracking-wider">Selected audit claim</div>
                  <h2 className="text-heading-l mt-1">{getCapabilityLabel(selectedCapability.id)}</h2>
                </div>
                <TrustScore score={selectedCapability.score} confidenceInterval={selectedCapability.confidenceInterval} />
              </div>

              <Card variant="glass" className="p-4 mb-8 bg-surface-canvas-tint">
                <div className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-1">Trust Score Reasoning</div>
                <p className="text-body text-content-primary">{selectedCapability.reasoning}</p>
                <p className="text-caption text-content-secondary mt-3">
                  Deterministic score logic: score = round(confidence * 100) - severity penalties. HIGH contradictions carry a 30-point penalty.
                </p>
              </Card>

              <section className="mb-8">
                <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider mb-3">Contradictions</h3>
                {selectedCapability.contradictions.length === 0 ? (
                  <div className="p-4 rounded-md border border-border-subtle bg-surface-sunken/60 text-body text-content-secondary">
                    No contradictions found for this claim.
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {selectedCapability.contradictions
                      .slice()
                      .sort((a, b) => (a.severity === 'HIGH' ? -1 : b.severity === 'HIGH' ? 1 : 0))
                      .map((contradiction) => (
                        <ContradictionBanner
                          key={contradiction.id}
                          severity={contradiction.severity}
                          type={contradiction.type}
                          reasoning={contradiction.reasoning}
                          evidenceFor={contradiction.evidenceFor}
                          evidenceAgainst={contradiction.evidenceAgainst}
                          detectedBy={contradiction.detectedBy}
                          detectedAt={contradiction.detectedAt}
                        />
                      ))}
                  </div>
                )}
              </section>

              <section className="flex flex-col gap-5">
                <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Evidence Trail</h3>
                {STANCE_ORDER.map((stance) => {
                  const evidence = selectedCapability.evidence.filter((item) => item.stance === stance);
                  if (evidence.length === 0) return null;
                  return (
                    <div key={stance} className="flex flex-col gap-3">
                      <div className="text-heading-s capitalize text-content-primary">{stance === 'silent' ? 'Silent / No confirming evidence found' : stance}</div>
                      {evidence.map((item) => (
                        <EvidenceCard
                          key={item.id}
                          stance={item.stance}
                          snippet={item.snippet}
                          sourceType={item.sourceType}
                          sourceDocId={item.sourceDocId}
                          span={item.span}
                          sourceObservedAt={item.sourceObservedAt}
                          retrievedAt={item.retrievedAt}
                          rationale={item.rationale}
                        />
                      ))}
                    </div>
                  );
                })}
              </section>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-content-tertiary">Select a capability to view its audit trail.</div>
          )}
        </main>
      </div>
    </div>
  );
}
