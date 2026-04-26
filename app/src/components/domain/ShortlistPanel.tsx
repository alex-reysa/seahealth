import React from 'react';
import { Star, X } from 'lucide-react';

import { Card } from '@/src/components/ui/Card';
import { Button } from '@/src/components/ui/Button';
import type { RankedFacility } from '@/src/types/api';

interface ShortlistPanelProps {
  /** Facility ids serialized to URL `?shortlist=a,b,c`. */
  shortlist: ReadonlyArray<string>;
  /** Live ranked rows; lookup happens by `facility_id`. */
  ranked: ReadonlyArray<RankedFacility>;
  /** Remove a single id from the shortlist. */
  onRemove: (facilityId: string) => void;
  /** Optional: clear all. */
  onClear?: () => void;
  /** Optional: open the audit page for an id. */
  onOpen?: (facilityId: string) => void;
}

/**
 * Renders the active shortlist as compact cards. The shortlist is owned by
 * the page via URL state; this component is purely presentational +
 * dispatches mutation callbacks back up.
 */
export function ShortlistPanel({
  shortlist,
  ranked,
  onRemove,
  onClear,
  onOpen,
}: ShortlistPanelProps) {
  const byId = React.useMemo(() => {
    const m = new Map<string, RankedFacility>();
    for (const r of ranked) m.set(r.facility_id, r);
    return m;
  }, [ranked]);

  if (shortlist.length === 0) {
    return (
      <Card variant="glass" className="p-4 text-caption text-content-secondary">
        <div className="flex items-center gap-2 mb-1 text-content-primary">
          <Star className="w-3.5 h-3.5" />
          <span className="font-semibold uppercase tracking-wider">Shortlist</span>
        </div>
        <p>Star ranked rows to compare them. URL stays in sync.</p>
      </Card>
    );
  }

  return (
    <Card variant="glass" className="flex flex-col gap-2 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-content-primary">
          <Star className="w-3.5 h-3.5" />
          <span className="text-caption font-semibold uppercase tracking-wider">
            Shortlist · {shortlist.length}
          </span>
        </div>
        {onClear && shortlist.length > 0 && (
          <Button variant="ghost" size="sm" className="h-6 px-2 text-caption" onClick={onClear}>
            Clear
          </Button>
        )}
      </div>
      <ul className="flex flex-col gap-1.5">
        {shortlist.map((id) => {
          const row = byId.get(id);
          return (
            <li
              key={id}
              className="flex items-center gap-2 rounded border border-border-subtle bg-white px-2 py-1.5"
            >
              <button
                type="button"
                onClick={() => onOpen?.(id)}
                disabled={!onOpen}
                className="flex-1 text-left disabled:cursor-default"
              >
                <div className="text-caption font-medium text-content-primary truncate">
                  {row?.name ?? id}
                </div>
                <div className="text-[11px] text-content-tertiary font-mono">
                  {row ? (
                    <>
                      score {row.trust_score?.score ?? '—'} · {row.distance_km}km
                    </>
                  ) : (
                    <>not in current ranked list</>
                  )}
                </div>
              </button>
              <button
                type="button"
                aria-label={`Remove ${row?.name ?? id} from shortlist`}
                onClick={() => onRemove(id)}
                className="text-content-tertiary hover:text-semantic-critical"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
