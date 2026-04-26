import React from 'react';
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react';

import type { ApiError } from '@/src/api/client';
import { Button } from '@/src/components/ui/Button';
import { Card } from '@/src/components/ui/Card';
import type { FetchStatus } from '@/src/hooks/useFetch';

interface AsyncBoundaryProps<T> {
  status: FetchStatus;
  data: T | undefined;
  error: ApiError | undefined;
  /** Re-trigger the fetch (or the mutation). */
  onRetry?: () => void;
  /** Optional custom skeleton; defaults to a centered spinner. */
  loading?: React.ReactNode;
  /** Optional custom empty state. */
  empty?: React.ReactNode;
  /** A short, page-specific noun used in default state copy ("results", "audit"). */
  context?: string;
  children: (data: T) => React.ReactNode;
}

/**
 * Renders one of five mutually exclusive states for an async data dependency:
 *
 * - `loading` — fetch in flight. Shows a spinner skeleton.
 * - `empty` — 200 OK with a zero-length / "no rows" payload.
 * - `unavailable` — 503 from the backend (DataLayerError). Shows the
 *   data-mode hint inline and a retry button.
 * - `error` — network / 4xx / unexpected shape. Surfaces the error detail.
 * - `success` / `idle` — delegates to `children(data)`.
 */
export function AsyncBoundary<T>({
  status,
  data,
  error,
  onRetry,
  loading,
  empty,
  context,
  children,
}: AsyncBoundaryProps<T>): React.ReactElement | null {
  if (status === 'idle') return null;

  if (status === 'loading') {
    return (
      <>{loading ?? (
        <div className="flex h-full items-center justify-center p-8">
          <div className="flex items-center gap-2 text-content-secondary">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-caption">Loading{context ? ` ${context}` : ''}…</span>
          </div>
        </div>
      )}</>
    );
  }

  if (status === 'empty') {
    return (
      <>{empty ?? (
        <Card variant="default" className="m-6 p-6 text-center">
          <Inbox className="mx-auto mb-2 h-6 w-6 text-content-tertiary" />
          <div className="text-body font-medium text-content-primary">No {context ?? 'results'}</div>
          <div className="text-caption text-content-secondary">
            The backend returned successfully but there is nothing to show for the active filter.
          </div>
        </Card>
      )}</>
    );
  }

  if (status === 'unavailable') {
    return (
      <Card variant="default" className="m-6 p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 shrink-0 text-semantic-flagged" />
          <div className="flex-1">
            <div className="text-body font-medium text-content-primary">Data unavailable</div>
            <p className="text-caption text-content-secondary">
              The backend reported the data layer cannot satisfy this request{error ? `: ${error.detail}` : ''}.
              Run the API in PARQUET or FIXTURE mode and retry.
            </p>
            {onRetry && (
              <Button variant="secondary" size="sm" className="mt-3 gap-2" onClick={onRetry}>
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </Button>
            )}
          </div>
        </div>
      </Card>
    );
  }

  if (status === 'error') {
    return (
      <Card variant="default" className="m-6 p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 shrink-0 text-semantic-critical" />
          <div className="flex-1">
            <div className="text-body font-medium text-content-primary">
              Couldn't load {context ?? 'this view'}
            </div>
            <p className="text-caption text-content-secondary">
              {error?.detail ?? 'Unexpected error'}
              {error?.status ? ` (HTTP ${error.status})` : ''}
            </p>
            {onRetry && (
              <Button variant="secondary" size="sm" className="mt-3 gap-2" onClick={onRetry}>
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </Button>
            )}
          </div>
        </div>
      </Card>
    );
  }

  // status === 'success' — defensive: data may be undefined briefly during transitions.
  if (data === undefined) return null;
  return <>{children(data)}</>;
}
