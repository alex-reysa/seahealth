import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, Download, Search, ShieldAlert, Star } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { TrustScore } from '@/src/components/domain/TrustScore';
import { TracePanel } from '@/src/components/domain/TracePanel';
import { TraceClassBadge } from '@/src/components/domain/TraceClassBadge';
import { AsyncBoundary } from '@/src/components/domain/AsyncBoundary';
import { DataModeBanner } from '@/src/components/domain/DataModeBanner';
import {
  PlannerControls,
  type PlannerControlsValue,
  type StaffingQualifier,
} from '@/src/components/domain/PlannerControls';
import { ShortlistPanel } from '@/src/components/domain/ShortlistPanel';
import { usePlannerQuery } from '@/src/hooks/usePlannerQuery';
import { useMapAggregates } from '@/src/hooks/useMapAggregates';
import { exportRankedCsv } from '@/src/lib/exportCsv';
import type { CapabilityType, QueryResult, RankedFacility } from '@/src/types/api';

type SortKey = 'rank' | 'name' | 'distance' | 'score' | 'contradictions' | 'evidence';

const LOCKED_DEMO_QUERY =
  'Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages parttime doctors.';
const PATNA_50KM_QUERY = 'Which facilities within 50km of Patna can perform an appendectomy?';
const STAFFING_VALUES: ReadonlyArray<StaffingQualifier> = ['parttime', 'fulltime', 'twentyfour_seven', 'low_volume'];
const TH_CLS =
  'px-4 py-3 text-caption text-content-secondary font-semibold uppercase tracking-wider';

const isStaffing = (v: string | null | undefined): v is StaffingQualifier =>
  !!v && (STAFFING_VALUES as ReadonlyArray<string>).includes(v);
const parseShortlist = (raw: string | null): string[] =>
  raw ? raw.split(',').map((s) => s.trim()).filter(Boolean) : [];
function sortRows(rows: RankedFacility[], k: SortKey, dir: 'asc' | 'desc'): RankedFacility[] {
  const sorted = [...rows].sort((a, b) => {
    const cmp =
      k === 'rank' ? a.rank - b.rank
      : k === 'name' ? a.name.localeCompare(b.name)
      : k === 'distance' ? a.distance_km - b.distance_km
      : k === 'score' ? (b.trust_score?.score ?? 0) - (a.trust_score?.score ?? 0)
      : k === 'contradictions' ? (b.contradictions_flagged ?? 0) - (a.contradictions_flagged ?? 0)
      : (b.evidence_count ?? 0) - (a.evidence_count ?? 0);
    return dir === 'asc' ? cmp : -cmp;
  });
  return sorted;
}
function rankRationale(row: RankedFacility): string {
  const score = row.trust_score?.score ?? 0;
  const flags = row.contradictions_flagged ?? 0;
  const ev = row.evidence_count ?? 0;
  const flagPart = flags > 0 ? `${flags} contradiction${flags === 1 ? '' : 's'}` : 'no contradictions';
  return `Rank #${row.rank} — Trust Score ${score} (${ev} evidence, ${flagPart}). Distance ${row.distance_km}km is the tie-breaker.`;
}

interface RowProps {
  row: RankedFacility;
  expanded: boolean;
  shortlisted: boolean;
  onToggleExpand: (id: string) => void;
  onToggleShortlist: (id: string) => void;
  onOpen: (id: string) => void;
}
const RankedRow: React.FC<RowProps> = (props) => {
  const { row, expanded, shortlisted, onToggleExpand, onToggleShortlist, onOpen } = props;
  return (
    <React.Fragment>
      <tr className="border-b border-border-subtle hover:bg-surface-canvas-tint transition-colors group">
        <td className="px-4 py-4 text-body font-mono text-content-secondary">#{row.rank}</td>
        <td className="px-4 py-4 text-body font-medium text-content-primary">
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-pressed={shortlisted}
              aria-label={shortlisted ? `Remove ${row.name} from shortlist` : `Add ${row.name} to shortlist`}
              onClick={() => onToggleShortlist(row.facility_id)}
              className={shortlisted ? 'text-amber-500 hover:text-amber-600' : 'text-content-tertiary hover:text-amber-500'}
            >
              <Star className="w-4 h-4" fill={shortlisted ? 'currentColor' : 'none'} />
            </button>
            <span>{row.name}</span>
          </div>
        </td>
        <td className="px-4 py-4 text-body text-content-secondary font-mono">
          {row.location?.pin_code ?? '—'}
        </td>
        <td className="px-4 py-4 text-body text-content-secondary">{row.distance_km} km</td>
        <td className="px-4 py-4">
          {row.trust_score && (
            <TrustScore
              score={row.trust_score.score}
              confidenceInterval={row.trust_score.confidence_interval}
              showLabel={false}
            />
          )}
        </td>
        <td className="px-4 py-4 text-center">
          {(row.contradictions_flagged ?? 0) > 0 ? (
            <div className="inline-flex items-center gap-1 text-semantic-critical bg-semantic-critical-subtle px-2 py-0.5 rounded-sm text-caption font-medium">
              <ShieldAlert className="w-3.5 h-3.5" />
              {row.contradictions_flagged}
            </div>
          ) : (
            <span className="text-content-tertiary">-</span>
          )}
        </td>
        <td className="px-4 py-4 text-center text-body text-content-secondary">{row.evidence_count}</td>
        <td className="px-4 py-4 text-right">
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => onToggleExpand(row.facility_id)}
              className="text-caption text-accent-primary hover:text-accent-primary-hover"
              aria-expanded={expanded}
            >
              Why this rank?
            </button>
            <button
              type="button"
              onClick={() => onOpen(row.facility_id)}
              className="inline-flex items-center gap-1 text-caption text-content-secondary hover:text-accent-primary"
            >
              Open audit
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border-subtle bg-surface-canvas-tint">
          <td colSpan={8} className="px-4 py-4">
            <div className="grid grid-cols-[1fr_auto] gap-4 rounded-lg border border-border-subtle bg-white p-4">
              <div>
                <div className="text-caption font-semibold uppercase tracking-wider text-content-secondary">
                  Ranking rationale
                </div>
                <p className="mt-2 text-body text-content-primary">{rankRationale(row)}</p>
                {row.trust_score?.reasoning && (
                  <p className="mt-2 text-caption text-content-secondary">{row.trust_score.reasoning}</p>
                )}
              </div>
              {row.trust_score && (
                <TrustScore
                  score={row.trust_score.score}
                  confidenceInterval={row.trust_score.confidence_interval}
                />
              )}
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
};

export function PlannerQuery() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const planner = usePlannerQuery();

  const qParam = searchParams.get('q') ?? '';
  const capabilityParam = (searchParams.get('capability') as CapabilityType | null) ?? '';
  const regionIdParam = searchParams.get('region_id') ?? '';
  const radiusParam = Number(searchParams.get('radius_km'));
  const staffingParam = searchParams.get('staffing');
  const shortlistParam = searchParams.get('shortlist');

  const [query, setQuery] = React.useState(qParam);
  const [sortKey, setSortKey] = React.useState<SortKey>('rank');
  const [sortDir, setSortDir] = React.useState<'asc' | 'desc'>('asc');
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const controlsValue: PlannerControlsValue = {
    capability: capabilityParam || '',
    regionId: regionIdParam,
    radiusKm: Number.isFinite(radiusParam) && radiusParam > 0 ? radiusParam : 50,
    staffingQualifier: isStaffing(staffingParam) ? staffingParam : '',
  };
  const shortlist = React.useMemo(() => parseShortlist(shortlistParam), [shortlistParam]);

  const mapAggregates = useMapAggregates();
  const regionOptions = React.useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of mapAggregates.data ?? []) {
      if (!seen.has(row.region_id)) {
        seen.set(row.region_id, `${row.region_name}${row.state ? ` · ${row.state}` : ''}`);
      }
    }
    return Array.from(seen, ([id, label]) => ({ id, label })).sort((a, b) =>
      a.label.localeCompare(b.label),
    );
  }, [mapAggregates.data]);

  // Auto-run when the URL carries a query (deep-link / paste case).
  const lastRunRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (qParam && qParam !== lastRunRef.current) {
      lastRunRef.current = qParam;
      planner.run(qParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qParam]);

  const updateParams = (mutator: (p: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams);
    mutator(next);
    setSearchParams(next, { replace: false });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    updateParams((p) => p.set('q', query));
    lastRunRef.current = query;
    planner.run(query);
  };
  const handleChip = (q: string) => {
    setQuery(q);
    updateParams((p) => p.set('q', q));
    lastRunRef.current = q;
    planner.run(q);
  };
  const handleControls = (next: PlannerControlsValue) =>
    updateParams((p) => {
      next.capability ? p.set('capability', next.capability) : p.delete('capability');
      next.regionId ? p.set('region_id', next.regionId) : p.delete('region_id');
      next.radiusKm ? p.set('radius_km', String(next.radiusKm)) : p.delete('radius_km');
      next.staffingQualifier ? p.set('staffing', next.staffingQualifier) : p.delete('staffing');
    });
  const toggleShortlist = (id: string) => {
    const next = new Set(shortlist);
    next.has(id) ? next.delete(id) : next.add(id);
    const arr = Array.from(next);
    updateParams((p) => (arr.length ? p.set('shortlist', arr.join(',')) : p.delete('shortlist')));
  };
  const clearShortlist = () => updateParams((p) => p.delete('shortlist'));
  const openAudit = (facilityId: string) => {
    const cap = controlsValue.capability || planner.data?.parsed_intent?.capability_type || '';
    const params = new URLSearchParams();
    if (cap) params.set('capability', cap);
    params.set('from', 'planner-query');
    if (qParam) params.set('q', qParam);
    navigate(`/facilities/${facilityId}?${params.toString()}`);
  };
  const onSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(k);
      setSortDir(k === 'rank' || k === 'distance' || k === 'name' ? 'asc' : 'desc');
    }
  };
  const toggleExpand = (id: string) =>
    setExpanded((cur) => {
      const n = new Set(cur);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const SortBtn = ({ label, value }: { label: string; value: SortKey }) => (
    <button
      type="button"
      onClick={() => onSort(value)}
      className="inline-flex items-center gap-1 hover:text-content-primary group"
    >
      {label}
      <ChevronDown
        className={`w-3 h-3 transition-all ${
          sortKey === value
            ? sortDir === 'asc'
              ? 'rotate-180 text-content-primary'
              : 'text-content-primary'
            : 'opacity-0 group-hover:opacity-50'
        }`}
      />
    </button>
  );

  const renderResult = (result: QueryResult) => {
    const baseRows = result.ranked_facilities ?? [];
    const filtered = controlsValue.capability
      ? baseRows.filter((r) => r.trust_score?.capability_type === controlsValue.capability)
      : baseRows;
    const sorted = sortRows(filtered, sortKey, sortDir);
    const stem = (controlsValue.capability || result.parsed_intent?.capability_type || 'planner')
      .toString()
      .toLowerCase();
    return (
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-col flex-1 p-6 min-h-0 gap-4">
          <PlannerControls value={controlsValue} regions={regionOptions} onChange={handleControls} />
          <Card variant="default" className="overflow-hidden bg-white flex flex-col flex-1 min-h-0">
            <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between text-caption text-content-secondary">
              <span>
                {sorted.length} ranked facilit{sorted.length === 1 ? 'y' : 'ies'}
                {filtered.length !== baseRows.length && <> · filtered from {baseRows.length}</>} ·
                sorted by {sortKey}
              </span>
              <span className="font-mono">
                retriever={result.retriever_mode} · used_llm={String(result.used_llm)}
              </span>
            </div>
            <div className="flex-1 min-h-0 overflow-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-surface-sunken sticky top-0 z-10 shadow-[0_1px_0_rgba(20,33,38,0.13)]">
                  <tr>
                    <th className={TH_CLS}><SortBtn label="Rank" value="rank" /></th>
                    <th className={TH_CLS}><SortBtn label="Facility" value="name" /></th>
                    <th className={TH_CLS}>Location</th>
                    <th className={TH_CLS}><SortBtn label="Distance" value="distance" /></th>
                    <th className={`${TH_CLS} w-40`}><SortBtn label="Trust Score" value="score" /></th>
                    <th className={`${TH_CLS} text-center`}><SortBtn label="Flags" value="contradictions" /></th>
                    <th className={`${TH_CLS} text-center`}><SortBtn label="Evidence" value="evidence" /></th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {sorted.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center text-content-tertiary">
                        No results match the active filter.
                      </td>
                    </tr>
                  )}
                  {sorted.map((row) => (
                    <RankedRow
                      key={row.facility_id}
                      row={row}
                      expanded={expanded.has(row.facility_id)}
                      shortlisted={shortlist.includes(row.facility_id)}
                      onToggleExpand={toggleExpand}
                      onToggleShortlist={toggleShortlist}
                      onOpen={openAudit}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <aside className="w-80 shrink-0 border-l border-border-subtle bg-surface-canvas p-6 overflow-y-auto">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-3">
              <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Parsed Intent</h3>
              <Card variant="glass" className="p-4 flex flex-col gap-3">
                <div>
                  <span className="text-caption text-content-tertiary">Capability</span>
                  <div className="text-body font-mono text-content-primary">{result.parsed_intent.capability_type}</div>
                </div>
                <div>
                  <span className="text-caption text-content-tertiary">Location</span>
                  <div className="text-body font-mono text-content-primary">
                    {result.parsed_intent.location.lat.toFixed(2)}, {result.parsed_intent.location.lng.toFixed(2)}
                    {result.parsed_intent.location.pin_code && ` · PIN ${result.parsed_intent.location.pin_code}`}
                  </div>
                </div>
                <div>
                  <span className="text-caption text-content-tertiary">Radius</span>
                  <div className="text-body font-mono text-content-primary">{result.parsed_intent.radius_km}km</div>
                </div>
                {result.parsed_intent.staffing_qualifier && (
                  <div>
                    <span className="text-caption text-content-tertiary">Staffing qualifier</span>
                    <div className="text-body font-mono text-content-primary">{result.parsed_intent.staffing_qualifier}</div>
                  </div>
                )}
                <div className="h-px bg-border-subtle my-1" />
                <div>
                  <span className="text-caption text-content-tertiary">Candidates evaluated</span>
                  <div className="text-body font-medium text-content-primary">{result.total_candidates} facilities</div>
                </div>
              </Card>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Trace</h3>
                <TraceClassBadge mlflowTraceId={result.mlflow_trace_id} queryTraceId={result.query_trace_id} />
              </div>
              <TracePanel
                mlflowTraceId={result.mlflow_trace_id}
                queryTraceId={result.query_trace_id}
                executionSteps={result.execution_steps}
              />
            </div>

            <div className="flex flex-col gap-3">
              <h3 className="text-caption font-semibold text-content-secondary uppercase tracking-wider">Shortlist</h3>
              <ShortlistPanel
                shortlist={shortlist}
                ranked={result.ranked_facilities}
                onRemove={toggleShortlist}
                onClear={clearShortlist}
                onOpen={openAudit}
              />
              {/* TODO(phase-6-compare): side-by-side region comparison panel. */}
            </div>

            <div className="flex flex-col gap-3 mt-2">
              <Button
                variant="secondary"
                className="w-full gap-2"
                onClick={() => exportRankedCsv(result.ranked_facilities, shortlist, stem)}
                disabled={(result.ranked_facilities?.length ?? 0) === 0}
              >
                <Download className="w-4 h-4" />
                Export CSV
              </Button>
              <span className="text-caption text-content-tertiary text-center">
                CSV is built from the live ranked list and shortlist flags.
              </span>
            </div>
          </div>
        </aside>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-surface-canvas">
      <DataModeBanner />
      <div className="p-6 border-b border-border-subtle bg-white shrink-0">
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-heading-l mb-2">Planner Query Console</h1>
            <p className="text-body text-content-secondary">
              Natural language in, structured ranked facility table out — sourced live from the SeaHealth API.
            </p>
          </div>
          {planner.data && (
            <TraceClassBadge
              mlflowTraceId={planner.data.mlflow_trace_id}
              queryTraceId={planner.data.query_trace_id}
            />
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
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask about capabilities, locations, and requirements..."
                className="pl-10 h-12 text-body-l shadow-inner"
              />
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-content-tertiary" />
            </div>
            <Button type="submit" variant="primary" size="lg" disabled={planner.status === 'loading'} className="w-36">
              {planner.status === 'loading' ? 'Running…' : 'Run Query'}
            </Button>
          </div>
          <div className="flex items-center gap-2 text-caption flex-wrap">
            <span className="text-content-secondary">Demo chips:</span>
            <button
              type="button"
              onClick={() => handleChip(LOCKED_DEMO_QUERY)}
              className="bg-surface-sunken hover:bg-border-subtle text-content-primary px-3 py-1 rounded-full transition-colors border border-border-default"
            >
              Rural Bihar appendectomy + part-time
            </button>
            <button
              type="button"
              onClick={() => handleChip(PATNA_50KM_QUERY)}
              className="bg-surface-sunken hover:bg-border-subtle text-content-primary px-3 py-1 rounded-full transition-colors border border-border-default"
            >
              Patna 50km appendectomy
            </button>
          </div>
        </form>
      </div>

      {planner.status === 'idle' ? (
        <div className="flex-1 flex flex-col items-center justify-center text-content-tertiary">
          <Search className="w-12 h-12 mb-4 opacity-20" />
          <p className="text-body-l">Submit a planning question to get a ranked facility table.</p>
        </div>
      ) : (
        <AsyncBoundary
          status={planner.status}
          data={planner.data}
          error={planner.error}
          onRetry={() => planner.run(qParam || query)}
          context="planner results"
        >
          {(result) => renderResult(result)}
        </AsyncBoundary>
      )}
    </div>
  );
}
