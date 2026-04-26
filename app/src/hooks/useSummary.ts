import { fetchSummary } from '@/src/api/client';
import type { CapabilityType, SummaryMetrics } from '@/src/types/api';

import { useFetch, type FetchState } from './useFetch';

export function useSummary(capabilityType?: CapabilityType | null): FetchState<SummaryMetrics> {
  return useFetch<SummaryMetrics>({
    key: `summary?cap=${capabilityType ?? ''}`,
    load: () => fetchSummary(undefined, capabilityType ?? undefined),
    isEmpty: (m) => m.audited_count === 0,
  });
}
