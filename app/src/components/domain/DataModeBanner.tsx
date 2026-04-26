import { Database, FlaskConical, HardDrive, Radio } from 'lucide-react';

import { useHealthData } from '@/src/hooks/useHealthData';

/**
 * Small status pill showing the active backend mode and retriever.
 *
 * Visible in development; hidden under production CORS posture (the backend
 * already redacts identifiers there). In demo mode it advertises "demo
 * (offline fixtures)" so reviewers know there's no live backend involved.
 */
export function DataModeBanner({ className = '' }: { className?: string }) {
  const { data, mode, loading } = useHealthData();

  if (mode === 'demo') {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 ${className}`}
        title="Frontend is running against bundled fixtures, no backend involved."
      >
        <FlaskConical className="h-3 w-3" /> demo mode (offline fixtures)
      </span>
    );
  }

  if (loading) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 ${className}`}>
        <Radio className="h-3 w-3 animate-pulse" /> checking backend…
      </span>
    );
  }

  if (!data) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-800 ${className}`}>
        <Radio className="h-3 w-3" /> backend unreachable
      </span>
    );
  }

  const iconByMode = {
    delta: <Database className="h-3 w-3" />,
    parquet: <HardDrive className="h-3 w-3" />,
    fixture: <FlaskConical className="h-3 w-3" />,
  } as const;
  const colorByMode = {
    delta: 'bg-emerald-100 text-emerald-800',
    parquet: 'bg-sky-100 text-sky-800',
    fixture: 'bg-amber-100 text-amber-800',
  } as const;

  const retrieverLabel =
    data.retriever_mode === 'vector_search'
      ? 'vector search'
      : data.retriever_mode === 'faiss_local'
        ? 'FAISS local'
        : data.retriever_mode;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${colorByMode[data.mode]} ${className}`}
      title={`mode=${data.mode} · retriever=${data.retriever_mode}`}
    >
      {iconByMode[data.mode]} live · {data.mode} · {retrieverLabel}
    </span>
  );
}
