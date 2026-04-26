import React from 'react';

import { ApiError } from '@/src/api/client';

export type FetchStatus = 'idle' | 'loading' | 'success' | 'empty' | 'unavailable' | 'error';

export interface FetchState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  status: FetchStatus;
  refetch: () => void;
}

interface UseFetchOptions<T> {
  /** A stable key. When it changes, the hook re-fetches. */
  key: string;
  /** Async loader. Receives an AbortSignal so callers can cancel. */
  load: (signal: AbortSignal) => Promise<T>;
  /** Optional: classify a successful response as "empty". */
  isEmpty?: (data: T) => boolean;
  /** Optional: skip the fetch entirely (e.g. param missing). */
  enabled?: boolean;
}

const inflight = new Map<string, Promise<unknown>>();

function dedupe<T>(key: string, runner: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const promise = runner().finally(() => {
    if (inflight.get(key) === promise) inflight.delete(key);
  });
  inflight.set(key, promise);
  return promise;
}

/**
 * Generic data hook with the four explicit states the UI taxonomy requires
 * (loading / empty / unavailable / error / success).
 *
 * - In-flight requests for the same `key` are deduped within a tick.
 * - The fetcher is passed an AbortSignal; the hook cancels on unmount or
 *   when `key` changes.
 * - "unavailable" means the API returned 503 (DataLayerError); the UI shows
 *   a retry path with the data-mode banner inline.
 */
export function useFetch<T>({ key, load, isEmpty, enabled = true }: UseFetchOptions<T>): FetchState<T> {
  const [data, setData] = React.useState<T | undefined>(undefined);
  const [error, setError] = React.useState<ApiError | undefined>(undefined);
  const [status, setStatus] = React.useState<FetchStatus>(enabled ? 'loading' : 'idle');
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    if (!enabled) {
      setStatus('idle');
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setStatus('loading');
    setError(undefined);
    dedupe(key + '#' + tick, () => load(controller.signal))
      .then((value) => {
        if (cancelled || controller.signal.aborted) return;
        setData(value as T);
        if (isEmpty && isEmpty(value as T)) {
          setStatus('empty');
        } else {
          setStatus('success');
        }
      })
      .catch((err: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        if (err instanceof ApiError) {
          setError(err);
          setStatus(err.status === 503 ? 'unavailable' : 'error');
        } else {
          // Unknown thrown value — surface as generic error.
          setError(new ApiError(0, (err as Error)?.message ?? 'unknown error'));
          setStatus('error');
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
    // load is intentionally excluded; consumers should keep the key stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, tick]);

  const refetch = React.useCallback(() => setTick((n) => n + 1), []);
  return { data, error, status, refetch };
}
