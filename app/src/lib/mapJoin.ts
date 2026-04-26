/**
 * Join `/map/aggregates` rows to topojson features by canonical region_id.
 *
 * Why this lives in its own module: the backend aggregates the parquet store
 * into PIN-prefix synthetic regions (`AUTO-PIN-1xxxxx` … `AUTO-PIN-8xxxxx`),
 * but the committee topology renders `BR_STATE`, `BR_PATNA`, `BR_MADHUBANI`.
 * There is no clean district-level mapping for the other PIN buckets, so the
 * alias map is intentionally sparse. Unmatched aggregate rows are returned
 * separately and the choropleth paints them with a neutral fill.
 *
 * NEVER paint by array index — features and rows are not aligned and the
 * order of either side is not part of any contract.
 */
import type { MapRegionAggregate } from '@/src/types/api';

/**
 * Backend region_id → topology feature id. PIN-8xxxxx is the only bucket that
 * lands in Bihar (Indian PIN range 800000–899999), so we route it to both the
 * district features the demo highlights. The state-background feature picks
 * up the same payload so the choropleth still has a state-level fill.
 */
const ALIAS_MAP: Record<string, string[]> = {
  'AUTO-PIN-8xxxxx': ['BR_STATE', 'BR_PATNA', 'BR_MADHUBANI'],
};

/**
 * Lookup helper for callers that have a canonical id and want the topology
 * feature id (currently they are the same: `BR_PATNA` → `BR_PATNA`). Kept as
 * an exported function so future re-keying of the topology only needs a
 * change here.
 */
export function lookupRegionId(canonicalId: string): string {
  return canonicalId;
}

export interface JoinedRegion {
  feature_region_id: string;
  /** The aggregate that drove this fill, if any. Undefined → render neutral. */
  aggregate?: MapRegionAggregate;
}

export interface JoinResult {
  /** One entry per topology feature, keyed by the feature's `regionId`. */
  byFeatureId: Map<string, JoinedRegion>;
  /** Aggregate rows that did not match any feature in the topology. */
  unmatched: MapRegionAggregate[];
}

/**
 * Join API rows to topology features.
 *
 * - Each topology feature appears in `byFeatureId` exactly once (so the
 *   choropleth always has a deterministic neutral fill for missing data).
 * - Aggregate rows that don't resolve are accumulated in `unmatched`. The
 *   caller (Dashboard) emits a single dev-only `console.warn` so we don't
 *   spam production consoles.
 * - When two aggregate rows resolve to the same feature (PIN-8 fans out to
 *   three Bihar features), the larger `verified_facilities_count` wins so
 *   the legend doesn't keep flipping between rows during dev.
 */
export function joinAggregatesToFeatures(
  aggregates: MapRegionAggregate[],
  topologyFeatureIds: readonly string[],
): JoinResult {
  const byFeatureId = new Map<string, JoinedRegion>();
  for (const fid of topologyFeatureIds) {
    byFeatureId.set(fid, { feature_region_id: fid });
  }

  const unmatched: MapRegionAggregate[] = [];
  for (const row of aggregates) {
    const targets = resolveFeatureIds(row, topologyFeatureIds);
    if (targets.length === 0) {
      unmatched.push(row);
      continue;
    }
    for (const fid of targets) {
      const slot = byFeatureId.get(fid);
      if (!slot) continue;
      const incumbent = slot.aggregate;
      if (!incumbent || row.verified_facilities_count > incumbent.verified_facilities_count) {
        slot.aggregate = row;
      }
    }
  }

  return { byFeatureId, unmatched };
}

/**
 * Resolve a single aggregate row to zero or more topology feature ids.
 * 1. Exact match on the row's `region_id`.
 * 2. Static alias entry (PIN-8 → Bihar set).
 * 3. Otherwise unmatched.
 */
function resolveFeatureIds(row: MapRegionAggregate, topologyFeatureIds: readonly string[]): string[] {
  if (topologyFeatureIds.includes(row.region_id)) {
    return [row.region_id];
  }
  const alias = ALIAS_MAP[row.region_id];
  if (alias && alias.length) {
    return alias.filter((fid) => topologyFeatureIds.includes(fid));
  }
  return [];
}

/**
 * Decorate raw GeoJSON features with the API-derived counts. Used so MapLibre
 * can paint by `verifiedFromApi` / `flaggedFromApi` without the layer paint
 * expression having to do its own join.
 */
export function decorateFeaturesWithJoin<F extends { properties: Record<string, unknown> }>(
  features: F[],
  join: JoinResult,
  featureIdProp = 'regionId',
): F[] {
  return features.map((feature) => {
    const fid = feature.properties[featureIdProp] as string | undefined;
    const slot = fid ? join.byFeatureId.get(fid) : undefined;
    const aggregate = slot?.aggregate;
    return {
      ...feature,
      properties: {
        ...feature.properties,
        verifiedFromApi: aggregate?.verified_facilities_count ?? 0,
        flaggedFromApi: aggregate?.flagged_facilities_count ?? 0,
        gapPopulationFromApi: aggregate?.gap_population ?? 0,
        populationFromApi: aggregate?.population ?? 0,
        populationSourceFromApi: aggregate?.population_source ?? 'unavailable',
        hasApiData: aggregate ? 1 : 0,
      },
    };
  });
}
