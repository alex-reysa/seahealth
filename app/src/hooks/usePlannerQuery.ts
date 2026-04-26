import React from 'react';

import { ApiError, fetchQuery } from '@/src/api/client';
import type { QueryResult } from '@/src/types/api';

import type { FetchStatus } from './useFetch';

export interface PlannerQueryState {
  data: QueryResult | undefined;
  error: ApiError | undefined;
  status: FetchStatus;
  /** Submit a new query. Cancels any in-flight call. */
  run: (q: string) => Promise<void>;
  /** Reset to idle (clears data + error). */
  reset: () => void;
}

/**
 * Mutation-style hook for `POST /query` — the planner waits for an explicit
 * user submit, then renders the result. Because this is not a passive load,
 * we don't share state across components: each consumer owns its own run.
 */
export function usePlannerQuery(initial?: QueryResult): PlannerQueryState {
  const [data, setData] = React.useState<QueryResult | undefined>(initial);
  const [error, setError] = React.useState<ApiError | undefined>(undefined);
  const [status, setStatus] = React.useState<FetchStatus>(initial ? 'success' : 'idle');
  const controllerRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  const run = React.useCallback(async (q: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus('loading');
    setError(undefined);
    try {
      const result = await fetchQuery(q);
      if (controller.signal.aborted) return;
      setData(result);
      setStatus(result.ranked_facilities.length === 0 ? 'empty' : 'success');
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError) {
        setError(err);
        setStatus(err.status === 503 ? 'unavailable' : 'error');
      } else {
        setError(new ApiError(0, (err as Error)?.message ?? 'unknown error'));
        setStatus('error');
      }
    }
  }, []);

  const reset = React.useCallback(() => {
    controllerRef.current?.abort();
    setData(undefined);
    setError(undefined);
    setStatus('idle');
  }, []);

  return { data, error, status, run, reset };
}
