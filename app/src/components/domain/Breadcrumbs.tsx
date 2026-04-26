/**
 * URL-driven region breadcrumbs (`India › Bihar › Patna`).
 *
 * - Reads `?region_id=…` from the current URL — that param is the source of
 *   truth for selection across the workbench.
 * - Walks `regionTree` upward; renders click-to-zoom buttons that mutate the
 *   URL. The actual map fly-to is wired by Dashboard via `onSelect`.
 * - When `region_id` is missing or unknown the component hides itself.
 */
import { ChevronRight } from 'lucide-react';

import { walkUpFrom } from '@/src/lib/regionTree';

interface BreadcrumbsProps {
  regionId: string | null | undefined;
  /** Called with the new region_id when a crumb is clicked. */
  onSelect: (regionId: string) => void;
  className?: string;
}

export function Breadcrumbs({ regionId, onSelect, className = '' }: BreadcrumbsProps) {
  if (!regionId) return null;
  const trail = walkUpFrom(regionId);
  if (trail.length === 0) return null;

  return (
    <nav
      aria-label="Region breadcrumb"
      className={`pointer-events-auto inline-flex flex-wrap items-center gap-1 rounded-full border border-border-subtle bg-white/82 px-3 py-1 shadow-elevation-1 backdrop-blur-xl ${className}`}
    >
      {trail.map((node, index) => {
        const isLast = index === trail.length - 1;
        return (
          <div key={node.region_id} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onSelect(node.region_id)}
              disabled={isLast}
              className={`rounded-full px-2 py-0.5 text-caption transition-colors ${
                isLast
                  ? 'cursor-default font-semibold text-content-primary'
                  : 'text-content-secondary hover:bg-surface-sunken hover:text-content-primary'
              }`}
              aria-current={isLast ? 'page' : undefined}
            >
              {node.name}
            </button>
            {!isLast && <ChevronRight className="h-3 w-3 shrink-0 text-content-tertiary" />}
          </div>
        );
      })}
    </nav>
  );
}
