import { fetchMapAggregates } from '@/src/api/client';
import type { CapabilityType, MapRegionAggregate } from '@/src/types/api';

import { useFetch, type FetchState } from './useFetch';

export function useMapAggregates(capabilityType?: CapabilityType | null): FetchState<MapRegionAggregate[]> {
  return useFetch<MapRegionAggregate[]>({
    key: `map?cap=${capabilityType ?? ''}`,
    load: () => fetchMapAggregates(undefined, capabilityType ?? undefined),
    isEmpty: (rows) => rows.length === 0,
  });
}
