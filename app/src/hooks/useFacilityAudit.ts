import { fetchFacility } from '@/src/api/client';
import type { FacilityAudit } from '@/src/types/api';

import { useFetch, type FetchState } from './useFetch';

export function useFacilityAudit(facilityId: string | undefined): FetchState<FacilityAudit> {
  return useFetch<FacilityAudit>({
    key: `facility?id=${facilityId ?? ''}`,
    enabled: Boolean(facilityId),
    load: () => fetchFacility(facilityId as string),
  });
}
