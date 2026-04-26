import type { CapabilityType } from '@/src/types/api';

export const CAPABILITIES: Array<{ id: CapabilityType; label: string }> = [
  { id: 'SURGERY_APPENDECTOMY', label: 'Appendectomy Surgery' },
  { id: 'SURGERY_GENERAL', label: 'General Surgery' },
  { id: 'ICU', label: 'Intensive Care' },
  { id: 'NEONATAL', label: 'Neonatal Care' },
  { id: 'DIALYSIS', label: 'Dialysis' },
  { id: 'ONCOLOGY', label: 'Oncology' },
  { id: 'TRAUMA', label: 'Trauma' },
  { id: 'MATERNAL', label: 'Maternal Care' },
  { id: 'RADIOLOGY', label: 'Radiology' },
  { id: 'LAB', label: 'Laboratory' },
  { id: 'PHARMACY', label: 'Pharmacy' },
  { id: 'EMERGENCY_24_7', label: 'Emergency 24/7' },
];

export const CHALLENGE_QUERY =
  'Find the nearest facility in rural Bihar that can perform an emergency appendectomy and typically leverages part-time doctors.';

export function getCapabilityLabel(capability: CapabilityType | string): string {
  return CAPABILITIES.find((item) => item.id === capability)?.label ?? capability;
}

export function formatNumber(value: number): string {
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return String(value);
}
