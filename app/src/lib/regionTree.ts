/**
 * Region hierarchy module — single source of truth for "what is the parent of
 * region X / what are the bounds I should fly to / what is the human readable
 * name?".
 *
 * The committed topojson at `app/src/data/mockIndiaRegions.topojson` only
 * carries flat per-feature properties (regionId, centroid, committee scores).
 * The sidecar `regionHierarchy.json` adds the parent/child wiring and the
 * synthetic `IN` (India) root that the breadcrumbs use.
 *
 * This module is a pure read of those static assets — there is no runtime
 * fetch and no mutation API. Loaded once at module import.
 */
import hierarchyJson from '@/src/data/regionHierarchy.json';

export type RegionId = string;

export interface RegionNode {
  region_id: RegionId;
  parent: RegionId | null;
  level: number;
  name: string;
  children: RegionId[];
  bounds?: [[number, number], [number, number]];
  centroid?: [number, number];
  /**
   * Optional pointer that says "treat me like the canonical id". Used so the
   * topojson `BR_STATE` feature can resolve to the synthetic `BR` row when the
   * UI walks the tree.
   */
  alias_of?: RegionId;
}

interface RawHierarchyEntry {
  parent: RegionId | null;
  level: number;
  name: string;
  children?: RegionId[];
  bounds?: [[number, number], [number, number]];
  centroid?: [number, number];
  alias_of?: RegionId;
}

const raw = hierarchyJson as unknown as Record<RegionId, RawHierarchyEntry>;

/** Canonical map keyed by region_id. Frozen so consumers cannot mutate. */
export const regionTree: ReadonlyMap<RegionId, RegionNode> = (() => {
  const map = new globalThis.Map<RegionId, RegionNode>();
  for (const [region_id, entry] of Object.entries(raw)) {
    map.set(region_id, {
      region_id,
      parent: entry.parent,
      level: entry.level,
      name: entry.name,
      children: entry.children ?? [],
      bounds: entry.bounds,
      centroid: entry.centroid,
      alias_of: entry.alias_of,
    });
  }
  return map;
})();

/**
 * Resolve aliases (e.g. `BR_STATE` → `BR`). Returns the canonical node or
 * `undefined` if the id is unknown.
 */
export function getRegion(regionId: RegionId | null | undefined): RegionNode | undefined {
  if (!regionId) return undefined;
  const node = regionTree.get(regionId);
  if (!node) return undefined;
  if (node.alias_of) return regionTree.get(node.alias_of);
  return node;
}

/**
 * Walk from a region up to (and including) the synthetic root. Returns
 * ancestors in tree order: `[root, …, self]`. Stops if a parent reference is
 * dangling so a malformed sidecar cannot infinite-loop.
 */
export function walkUpFrom(regionId: RegionId): RegionNode[] {
  const trail: RegionNode[] = [];
  const seen = new Set<RegionId>();
  let cursor: RegionNode | undefined = getRegion(regionId);
  while (cursor && !seen.has(cursor.region_id)) {
    trail.push(cursor);
    seen.add(cursor.region_id);
    cursor = cursor.parent ? getRegion(cursor.parent) : undefined;
  }
  return trail.reverse();
}

/**
 * Bounding box for a region in `[[minLng, minLat], [maxLng, maxLat]]`. Falls
 * back to the centroid as a degenerate box when explicit bounds are missing,
 * which keeps `flyTo({bounds})` from throwing on malformed data.
 */
export function getBounds(regionId: RegionId): [[number, number], [number, number]] | undefined {
  const node = getRegion(regionId);
  if (!node) return undefined;
  if (node.bounds) return node.bounds;
  if (node.centroid) {
    const [lng, lat] = node.centroid;
    return [[lng, lat], [lng, lat]];
  }
  return undefined;
}

/** Centroid of a region, or undefined if neither sidecar nor topology has one. */
export function getCentroid(regionId: RegionId): [number, number] | undefined {
  const node = getRegion(regionId);
  return node?.centroid;
}

/**
 * Convenience: ordered crumb labels from root → self, suitable for direct
 * rendering. Returns `[]` if `regionId` is unknown.
 */
export function getBreadcrumbTrail(regionId: RegionId): Array<{ region_id: RegionId; name: string }> {
  return walkUpFrom(regionId).map((node) => ({ region_id: node.region_id, name: node.name }));
}
