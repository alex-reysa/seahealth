/**
 * Choropleth legend that explains the active overlay's count thresholds and
 * surfaces the population-source provenance.
 *
 * The "(population unavailable)" pill is the visible signal that the active
 * `MapRegionAggregate` rows came from PARQUET mode (no Delta-backed Census
 * roster). When that is true the side panel is also responsible for
 * suppressing any "% of population" copy.
 */
import { Info } from 'lucide-react';

import type { PopulationSource } from '@/src/types/api';

export interface LegendStop {
  /** Lower bound of the bucket, in the legend's units (count or score 0–1). */
  threshold: number;
  /** Background color displayed in the swatch. */
  color: string;
  /** Optional human label. Defaults to `≥ threshold`. */
  label?: string;
}

interface MapLegendProps {
  /** Title of the active overlay (e.g. "Verified facilities"). */
  title: string;
  /** Short caption explaining the unit ("from /map/aggregates"). */
  caption?: string;
  /** Color stops for the swatches, ordered low → high. */
  stops: LegendStop[];
  /** Population provenance from `MapRegionAggregate.population_source`. */
  populationSource?: PopulationSource | null;
  /** Number of aggregate rows that did not match a topology feature. */
  unmatchedCount?: number;
  className?: string;
}

export function MapLegend({
  title,
  caption,
  stops,
  populationSource,
  unmatchedCount,
  className = '',
}: MapLegendProps) {
  const showUnavailablePill = populationSource === 'unavailable';
  return (
    <div
      className={`pointer-events-auto w-[174px] rounded-2xl border border-white/55 bg-white/48 p-2.5 text-caption text-content-secondary opacity-85 backdrop-blur-xl transition-opacity hover:opacity-100 ${className}`}
    >
      <div>
        <div className="text-mono-s font-semibold uppercase tracking-wider text-content-secondary">{title}</div>
        {caption && <div className="mt-0.5 text-mono-s text-content-tertiary">{caption}</div>}
      </div>

      <ul className="mt-2 flex flex-col gap-1">
        {stops.map((stop, index) => (
          <li key={`${stop.threshold}-${index}`} className="flex items-center justify-between gap-2 text-mono-s text-content-secondary">
            <span>{stop.label ?? `≥ ${stop.threshold}`}</span>
            <span
              aria-hidden="true"
              className="h-2 w-10 rounded-full"
              style={{ backgroundColor: stop.color }}
            />
          </li>
        ))}
      </ul>

      {showUnavailablePill && (
        <span
          className="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-100/70 px-2 py-0.5 text-mono-s font-medium text-amber-800"
          title="Backend did not return a population denominator for this query."
        >
          <Info className="h-3 w-3" /> population unavailable
        </span>
      )}

      {typeof unmatchedCount === 'number' && unmatchedCount > 0 && (
        <div className="mt-2 text-mono-s text-content-tertiary">
          {unmatchedCount} aggregate row{unmatchedCount === 1 ? '' : 's'} unmatched
        </div>
      )}
    </div>
  );
}
