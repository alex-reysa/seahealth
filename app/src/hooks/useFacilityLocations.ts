import { fetchFacilityLocations } from '@/src/api/client';
import type { FacilityLocation } from '@/src/types/api';

import { useFetch, type FetchState } from './useFetch';

export function useFacilityLocations(): FetchState<FacilityLocation[]> {
  return useFetch<FacilityLocation[]>({
    key: 'facilities-geo',
    load: () => fetchFacilityLocations(),
    isEmpty: (rows) => rows.length === 0,
  });
}
