/**
 * Single typed API client for SeaHealth.
 *
 * Routes between two modes controlled by the build-time env var
 * `VITE_SEAHEALTH_API_MODE`:
 *
 *   - `live` (default when `VITE_SEAHEALTH_API_BASE` is set): fetches the
 *     real FastAPI surface at `${VITE_SEAHEALTH_API_BASE}` (default
 *     `http://localhost:8000`).
 *   - `demo`: returns the bundled API-shape fixtures from
 *     `app/src/data/fixtures/*.json` so the UI can run without a backend
 *     (judges, offline review).
 *
 * Each fetcher returns `Promise<T>` and throws an `ApiError` on non-2xx.
 * Callers should pair this with their own loading / error states.
 *
 * Validation note: there is no runtime validation. The Pydantic backend
 * is the source of truth; the TypeScript types in `@/src/types/api` are
 * a compile-time mirror that callers are responsible for updating
 * alongside the openapi yaml. JSON responses are cast `as T`. Treat
 * unexpected shapes as bugs in the contract sync, not silent recoveries.
 */

import type {
  CapabilityType,
  FacilityAudit,
  FacilityLocation,
  HealthData,
  MapRegionAggregate,
  QueryResult,
  SummaryMetrics,
} from '@/src/types/api';

export type ApiMode = 'live' | 'demo';

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`API ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

interface ImportMetaEnvShape {
  VITE_SEAHEALTH_API_BASE?: string;
  VITE_SEAHEALTH_API_MODE?: string;
}

function readEnv(): ImportMetaEnvShape {
  // Vite only replaces *static* `import.meta.env.VITE_FOO` references at
  // build time. A dynamic `(import.meta as any).env` access stays in the
  // bundle as a runtime read — and `import.meta.env` is undefined in a
  // plain browser, so every var silently resolved to undefined and the UI
  // stayed in demo mode no matter what was set in Vercel project env.
  return {
    VITE_SEAHEALTH_API_BASE: import.meta.env.VITE_SEAHEALTH_API_BASE,
    VITE_SEAHEALTH_API_MODE: import.meta.env.VITE_SEAHEALTH_API_MODE,
  };
}

export function resolveApiMode(): ApiMode {
  const env = readEnv();
  const explicit = env.VITE_SEAHEALTH_API_MODE?.toLowerCase();
  if (explicit === 'live' || explicit === 'demo') return explicit;
  // Default: if a base URL is configured, run live; otherwise demo.
  return env.VITE_SEAHEALTH_API_BASE ? 'live' : 'demo';
}

export function getApiBase(): string {
  const env = readEnv();
  return env.VITE_SEAHEALTH_API_BASE?.replace(/\/+$/, '') ?? 'http://localhost:8000';
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${getApiBase()}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (err) {
    throw new ApiError(0, `network error: ${(err as Error).message}`);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      // ignore — keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

// Demo fallback fixtures mirror the canonical API responses. The JSON
// imports are statically resolved by Vite, so the live build does not pay
// for them at runtime.
import demoFacilityAudit from '@/src/data/fixtures/facility_audit_demo.json';
import demoFacilityLocations from '@/src/data/fixtures/facility_locations_demo.json';
import demoMapAggregates from '@/src/data/fixtures/map_aggregates_demo.json';
import demoQueryResult from '@/src/data/fixtures/demo_query_appendectomy.json';
import demoSummary from '@/src/data/fixtures/summary_demo.json';

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function fetchSummary(
  mode: ApiMode = resolveApiMode(),
  capabilityType?: CapabilityType,
): Promise<SummaryMetrics> {
  if (mode === 'live') {
    const qs = capabilityType ? `?capability_type=${encodeURIComponent(capabilityType)}` : '';
    return jsonFetch<SummaryMetrics>(`/summary${qs}`);
  }
  const summary = demoSummary as unknown as SummaryMetrics;
  if (capabilityType) {
    return { ...summary, capability_type: capabilityType };
  }
  return summary;
}

export async function fetchQuery(
  query: string,
  mode: ApiMode = resolveApiMode(),
  signal?: AbortSignal,
): Promise<QueryResult> {
  if (mode === 'live') {
    return jsonFetch<QueryResult>('/query', {
      method: 'POST',
      body: JSON.stringify({ query }),
      signal,
    });
  }
  return { ...(demoQueryResult as unknown as QueryResult), query };
}

export async function fetchFacility(
  facilityId: string,
  mode: ApiMode = resolveApiMode(),
): Promise<FacilityAudit> {
  if (mode === 'live') {
    return jsonFetch<FacilityAudit>(`/facilities/${encodeURIComponent(facilityId)}`);
  }
  return demoFacilityAudit as unknown as FacilityAudit;
}

export async function fetchFacilityLocations(
  mode: ApiMode = resolveApiMode(),
): Promise<FacilityLocation[]> {
  if (mode === 'live') return jsonFetch<FacilityLocation[]>('/facilities/geo');
  return demoFacilityLocations as unknown as FacilityLocation[];
}

export async function fetchMapAggregates(
  mode: ApiMode = resolveApiMode(),
  capabilityType?: CapabilityType,
): Promise<MapRegionAggregate[]> {
  if (mode === 'live') {
    const qs = capabilityType ? `?capability_type=${encodeURIComponent(capabilityType)}` : '';
    return jsonFetch<MapRegionAggregate[]>(`/map/aggregates${qs}`);
  }
  const all = demoMapAggregates as unknown as MapRegionAggregate[];
  return capabilityType ? all.filter((row) => row.capability_type === capabilityType) : all;
}

export async function fetchHealthData(): Promise<HealthData | null> {
  // Health is only meaningful in live mode; demo mode reports null so the
  // UI can render a "demo mode" banner.
  if (resolveApiMode() !== 'live') return null;
  try {
    return await jsonFetch<HealthData>('/health/data');
  } catch {
    return null;
  }
}
