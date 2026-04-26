import React from 'react';

import { fetchHealthData, resolveApiMode } from '@/src/api/client';
import type { HealthData } from '@/src/types/api';

interface HealthState {
  data: HealthData | null;
  mode: 'live' | 'demo';
  loading: boolean;
}

const CACHE_TTL_MS = 30_000;
let cache: { fetchedAt: number; data: HealthData | null } | null = null;
let inflight: Promise<HealthData | null> | null = null;

async function loadCached(): Promise<HealthData | null> {
  const now = Date.now();
  if (cache && now - cache.fetchedAt < CACHE_TTL_MS) return cache.data;
  if (inflight) return inflight;
  inflight = fetchHealthData()
    .then((data) => {
      cache = { fetchedAt: Date.now(), data };
      return data;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/**
 * Polls /health/data with a 30s in-memory cache so multiple components can
 * read the snapshot without amplifying request traffic.
 *
 * In demo mode (`VITE_SEAHEALTH_API_MODE=demo`) the loader resolves to null
 * — components should treat that as "running offline against bundled fixtures".
 */
export function useHealthData(): HealthState {
  const apiMode = resolveApiMode();
  const [data, setData] = React.useState<HealthData | null>(cache?.data ?? null);
  const [loading, setLoading] = React.useState<boolean>(!cache && apiMode === 'live');

  React.useEffect(() => {
    let cancelled = false;
    if (apiMode !== 'live') {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(!cache);
    loadCached()
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiMode]);

  return { data, mode: apiMode, loading };
}

export function resetHealthDataCache(): void {
  cache = null;
}
