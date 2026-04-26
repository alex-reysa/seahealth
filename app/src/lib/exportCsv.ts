/**
 * Browser-side CSV export for the planner ranked + shortlist tables.
 *
 * No backend round-trip: the rows are formed from the same `RankedFacility[]`
 * the page already rendered. This keeps the export honest — what you see is
 * what you save.
 */

import type { RankedFacility } from '@/src/types/api';

export interface ExportRow {
  id: string;
  name: string;
  capability: string;
  distance_km: number;
  score: number;
  contradictions: number;
  evidence_count: number;
  top_evidence_snippet: string;
  shortlisted: boolean;
}

/** Columns in display order. Keep aligned with `ExportRow`. */
const HEADERS: Array<keyof ExportRow> = [
  'id',
  'name',
  'capability',
  'distance_km',
  'score',
  'contradictions',
  'evidence_count',
  'top_evidence_snippet',
  'shortlisted',
];

function csvEscape(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  // RFC 4180: wrap in quotes, double internal quotes.
  if (/[",\n\r]/.test(s)) {
    return `"${s.replaceAll('"', '""')}"`;
  }
  return s;
}

export function rankedToExportRows(
  ranked: RankedFacility[],
  shortlist: ReadonlyArray<string> = [],
): ExportRow[] {
  const shortlistSet = new Set(shortlist);
  return ranked.map((r) => {
    const top = r.trust_score?.evidence?.[0]?.snippet ?? '';
    return {
      id: r.facility_id,
      name: r.name,
      capability: r.trust_score?.capability_type ?? '',
      distance_km: r.distance_km,
      score: r.trust_score?.score ?? 0,
      contradictions: r.contradictions_flagged ?? 0,
      evidence_count: r.evidence_count ?? 0,
      top_evidence_snippet: top,
      shortlisted: shortlistSet.has(r.facility_id),
    };
  });
}

export function rowsToCsv(rows: ExportRow[]): string {
  const lines = [HEADERS.join(',')];
  for (const row of rows) {
    lines.push(HEADERS.map((h) => csvEscape(row[h])).join(','));
  }
  return lines.join('\n');
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  // Defer cleanup so Safari has time to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 200);
}

export function exportRankedCsv(
  ranked: RankedFacility[],
  shortlist: ReadonlyArray<string>,
  filenameStem: string,
): void {
  const rows = rankedToExportRows(ranked, shortlist);
  const csv = rowsToCsv(rows);
  const safeStem = filenameStem.replace(/[^a-z0-9_-]+/gi, '-').toLowerCase() || 'planner';
  downloadCsv(`seahealth-${safeStem}.csv`, csv);
}
