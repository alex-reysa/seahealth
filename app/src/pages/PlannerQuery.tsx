import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, Download, Loader2, Search, ShieldAlert } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { TracePanel } from '@/src/components/domain/TracePanel';
import {
  APPENDECTOMY_QUERY_RESULT,
  DEMO_QUERY,
  type CapabilityType,
  getCapabilityAudit,
  getCapabilityLabel,
  getFacilityRowsForRegion,
  getRankedFacilities,
  parseDemoCommand,
} from '@/src/data/demoData';

type SortKey = 'rank' | 'name' | 'distance' | 'score' | 'contradictions' | 'evidence';
type AgentStage = 'idle' | 'parsing' | 'geocoding' | 'searching' | 'ranking' | 'complete';

const STAGE_LABELS: Record<AgentStage, string> = {
  idle: 'Ready',
  parsing: 'Parsing query',
  geocoding: 'Geocoding Patna',
  searching: 'Searching facility audits',
  ranking: 'Ranking by trust score',
  complete: 'Structured result ready',
};

export function PlannerQuery() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const qParam = searchParams.get('q');
  const [query, setQuery] = React.useState(qParam || '');
  const [hasSearched, setHasSearched] = React.useState(!!qParam);
  const [stage, setStage] = React.useState<AgentStage>(qParam ? 'complete' : 'idle');
  const [sortKey, setSortKey] = React.useState<SortKey>('rank');
  const [sortDirection, setSortDirection] = React.useState<'asc' | 'desc'>('asc');

  const intent = React.useMemo(() => parseDemoCommand(query || DEMO_QUERY), [query]);
  const capability = intent.capability;
  const rows = React.useMemo(() => {
    const ranked =
      capability === 'SURGERY_APPENDECTOMY' && intent.location === 'Patna'
        ? getRankedFacilities(APPENDECTOMY_QUERY_RESULT)
        : getFacilityRowsForRegion(intent.regionId, capability);

    return ranked
      .map((facility, index) => {
        const audit = getCapabilityAudit(facility, capability);
        return { facility, audit, rank: index + 1 };
      })
      .filter((row) => row.audit);
  }, [capability, intent.regionId, intent.location]);

  const sortedRows = React.useMemo(() => {
    const sorted = [...rows].sort((a, b) => {
      const scoreA = a.audit?.score ?? 0;
      const scoreB = b.audit?.score ?? 0;
      const compare =
        sortKey === 'rank'
          ? a.rank - b.rank
          : sortKey === 'name'
            ? a.facility.name.localeCompare(b.facility.name)
            : sortKey === 'distance'
              ? a.facility.distanceKm - b.facility.distanceKm
              : sortKey === 'score'
                ? scoreB - scoreA
                : sortKey === 'contradictions'
                  ? (b.audit?.contradictionCount ?? 0) - (a.audit?.contradictionCount ?? 0)
                  : (b.audit?.evidenceCount ?? 0) - (a.audit?.evidenceCount ?? 0);
      return sortDirection === 'asc' ? compare : -compare;
    });
    return sorted;
  }, [rows, sortDirection, sortKey]);

  const isInitialMount = React.useRef(true);

  React.useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      if (qParam) {
        setQuery(qParam);
        setHasSearched(true);
        setStage('complete');
      }
    }
  }, [qParam]);

  const setSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDirection(key === 'rank' || key === 'distance' || key === 'name' ? 'asc' : 'desc');
    }
  };

  const runQuery = (nextQuery = query) => {
    if (!nextQuery.trim()) return;
    setSearchParams({ q: nextQuery });
    setHasSearched(true);
    setStage('parsing');
    window.setTimeout(() => setStage('geocoding'), 250);
    window.setTimeout(() => setStage('searching'), 550);
    window.setTimeout(() => setStage('ranking'), 850);
    window.setTimeout(() => setStage('complete'), 1150);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    runQuery();
  };

  const handleChipClick = (nextQuery: string) => {
    setQuery(nextQuery);
    runQuery(nextQuery);
  };

  const handleRowOpen = (facilityId: string) => {
    navigate(`/facilities/${facilityId}?capability=${capability}&from=planner-query&q=${encodeURIComponent(query)}`);
  };

  const exportCsv = () => {
    const header = [
      'query',
      'query_trace_id',
      'generated_at',
      'parsed_capability',
      'parsed_latitude',
      'parsed_longitude',
      'parsed_pin_code',
      'radius_km',
      'rank',
      'facility_id',
      'facility_name',
      'facility_lat',
      'facility_lng',
      'distance_km',
      'trust_score',
      'confidence_interval_low',
      'confidence_interval_high',
      'contradictions_flagged',
      'evidence_count',
      'facility_pin_code',
      'audit_url',
    ];
    const lines = sortedRows.map(({ facility, audit, rank }) =>
      [
        query,
        APPENDECTOMY_QUERY_RESULT.queryTraceId,
        APPENDECTOMY_QUERY_RESULT.generatedAt,
        capability,
        intent.location === 'Patna' ? APPENDECTOMY_QUERY_RESULT.parsedIntent.lat : '',
        intent.location === 'Patna' ? APPENDECTOMY_QUERY_RESULT.parsedIntent.lng : '',
        intent.pinCode,
        intent.radiusKm,
        rank,
        facility.id,
        facility.name,
        facility.lat,
        facility.lng,
        facility.distanceKm,
        audit?.score,
        audit?.confidenceInterval[0],
        audit?.confidenceInterval[1],
        audit?.contradictionCount,
        audit?.evidenceCount,
        facility.pinCode,
        `/facilities/${facility.id}?capability=${capability}&from=planner-query&q=${encodeURIComponent(query)}`,
      ]
        .map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`)
        .join(','),
    );
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `seahealth-${intent.location.toLowerCase()}-${capability.toLowerCase()}-results.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 200);
  };

  const SortButton = ({ label, value }: { label: string; value: SortKey }) => (
    <button type="button" onClick={() => setSort(value)} className="inline-flex items-center gap-1 hover:text-content-primary group">
      {label}
      <ChevronDown className={`w-3 h-3 transition-all ${sortKey === value ? (sortDirection === 'asc' ? 'rotate-180 text-content-primary' : 'text-content-primary') : 'opacity-0 group-hover:opacity-50'}`} />
    </button>
  );

  return (
    <div className="flex flex-col h-full overflow-hidden bg-surface-canvas">
      <div className="p-6 border-b border-border-subtle bg-white shrink-0">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-heading-l mb-2">Planner Query Console</h1>
            <p className="text-body text-content-secondary">Natural language in, structured ranked facility table out. No chat history.</p>
          </div>
          {hasSearched && (
            <Card variant="glass" className="px-4 py-2 min-w-64">
              <div className="flex items-center gap-2 text-caption text-content-secondary">
                {stage !== 'complete' && <Loader2 className="w-4 h-4 animate-spin" />}
                <span>{STAGE_LABELS[stage]}</span>
              </div>
            </Card>
          )}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 max-w-5xl mt-5">
          <label htmlFor="planner-query-input" className="text-caption text-content-secondary uppercase tracking-wider">
            Planning question
          </label>
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Input
                id="planner-query-input"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask about capabilities, locations, and requirements..."
                className="pl-10 h-12 text-body-l shadow-inner"
              />
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-content-tertiary" />
            </div>
            <Button type="submit" variant="primary" size="lg" disabled={stage !== 'idle' && stage !== 'complete'} className="w-36">
              {stage !== 'idle' && stage !== 'complete' ? 'Running...' : 'Run Query'}
            </Button>
          </div>
          <div className="flex items-center gap-2 text-caption">
            <span className="text-content-secondary">Demo chip:</span>
            <button
              type="button"
              onClick={() => handleChipClick(DEMO_QUERY)}
              className="bg-surface-sunken hover:bg-border-subtle text-content-primary px-3 py-1 rounded-full transition-colors border border-border-default"
            >
              {DEMO_QUERY}
            </button>
          </div>
        </form>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 flex flex-col p-6 min-h-0">
          {!hasSearched ? (
            <div className="flex flex-col items-center justify-center h-full text-content-tertiary">
              <Search className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-body-l">Run the appendectomy demo query to generate a ranked table.</p>
            </div>
          ) : (
            <Card variant="default" className="overflow-hidden bg-white flex flex-col flex-1 min-h-0">
              <div className="px-4 py-3 border-b border-border-subtle text-caption text-content-secondary">
                {sortedRows.length} ranked facilities · sorted by {sortKey}
              </div>
              <div className="flex-1 min-h-0 overflow-auto">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-surface-sunken sticky top-0 z-10 shadow-[0_1px_0_rgba(20,33,38,0.13)]">
                    <tr>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider"><SortButton label="Rank" value="rank" /></th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider"><SortButton label="Facility" value="name" /></th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider">Location</th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider"><SortButton label="Distance" value="distance" /></th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider w-40"><SortButton label="Trust Score" value="score" /></th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider text-center"><SortButton label="Flags" value="contradictions" /></th>
                      <th className="px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider text-center"><SortButton label="Evidence" value="evidence" /></th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.map(({ facility, audit, rank }) => (
                      <tr
                        key={facility.id}
                        tabIndex={0}
                        onClick={() => handleRowOpen(facility.id)}
                        onKeyDown={(event) => event.key === 'Enter' && handleRowOpen(facility.id)}
                        className="border-b border-border-subtle hover:bg-surface-canvas-tint focus:bg-surface-canvas-tint focus:outline-none cursor-pointer transition-colors group"
                      >
                        <td className="px-4 py-4 text-body font-mono text-content-secondary">#{rank}</td>
                        <td className="px-4 py-4 text-body font-medium text-content-primary">{facility.name}</td>
                        <td className="px-4 py-4 text-body text-content-secondary">PIN {facility.pinCode}</td>
                        <td className="px-4 py-4 text-body text-content-secondary">{facility.distanceKm} km</td>
                        <td className="px-4 py-4">{audit && <TrustScore score={audit.score} confidenceInterval={audit.confidenceInterval} showLabel={false} />}</td>
                        <td className="px-4 py-4 text-center">
                          {(audit?.contradictionCount ?? 0) > 0 ? (
                            <div className="inline-flex items-center gap-1 text-semantic-critical bg-semantic-critical-subtle px-2 py-0.5 rounded-sm text-caption font-medium">
                              <ShieldAlert className="w-3.5 h-3.5" />
                              {audit?.contradictionCount}
                            </div>
                          ) : (
                            <span className="text-content-tertiary">-</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-center text-body text-content-secondary">{audit?.evidenceCount}</td>
                        <td className="px-4 py-4 text-right">
                          <ChevronRight className="w-5 h-5 text-content-tertiary group-hover:text-accent-primary transition-colors inline-block" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>

        {hasSearched && (
          <div className="w-80 shrink-0 border-l border-border-subtle bg-surface-canvas p-6 overflow-y-auto">
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-3">
                <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Parsed Intent</h3>
                <Card variant="glass" className="p-4 flex flex-col gap-3">
                  <div>
                    <span className="text-caption text-content-tertiary">Capability</span>
                    <div className="text-body font-mono text-content-primary">{capability}</div>
                    <div className="text-caption text-content-secondary">{getCapabilityLabel(capability)}</div>
                  </div>
                  <div>
                    <span className="text-caption text-content-tertiary">Location</span>
                    <div className="text-body font-mono text-content-primary">{intent.location}</div>
                  </div>
                  <div>
                    <span className="text-caption text-content-tertiary">Radius</span>
                    <div className="text-body font-mono text-content-primary">{intent.radiusKm}km</div>
                  </div>
                  <div className="h-px bg-border-subtle my-1" />
                  <div>
                    <span className="text-caption text-content-tertiary">Candidates Evaluated</span>
                    <div className="text-body font-medium text-content-primary">{APPENDECTOMY_QUERY_RESULT.totalCandidates} facilities</div>
                  </div>
                </Card>
              </div>

              <div className="flex flex-col gap-3">
                <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Agent Trace</h3>
                <TracePanel queryTraceId={APPENDECTOMY_QUERY_RESULT.queryTraceId} spans={APPENDECTOMY_QUERY_RESULT.spans} />
              </div>

              <div className="flex flex-col gap-3 mt-4">
                <Button variant="secondary" className="w-full gap-2" disabled={stage !== 'complete'} onClick={exportCsv}>
                  <Download className="w-4 h-4" />
                  Export CSV
                </Button>
                <span className="text-caption text-content-tertiary text-center">
                  Exports ranked results and query metadata only.
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
