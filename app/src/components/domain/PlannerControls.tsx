import React from 'react';

import type { CapabilityType } from '@/src/types/api';

export type StaffingQualifier = 'parttime' | 'fulltime' | 'twentyfour_seven' | 'low_volume';

export interface PlannerControlsValue {
  capability: CapabilityType | '';
  regionId: string;
  radiusKm: number;
  staffingQualifier: StaffingQualifier | '';
}

interface RegionOption {
  id: string;
  label: string;
}

interface PlannerControlsProps {
  value: PlannerControlsValue;
  regions: RegionOption[];
  onChange: (next: PlannerControlsValue) => void;
}

const CAPABILITY_OPTIONS: ReadonlyArray<{ value: CapabilityType; label: string }> = [
  { value: 'SURGERY_APPENDECTOMY', label: 'Surgery — Appendectomy' },
  { value: 'SURGERY_GENERAL', label: 'Surgery — General' },
  { value: 'ICU', label: 'ICU' },
  { value: 'TRAUMA', label: 'Trauma' },
  { value: 'NEONATAL', label: 'Neonatal' },
  { value: 'MATERNAL', label: 'Maternal' },
  { value: 'DIALYSIS', label: 'Dialysis' },
  { value: 'ONCOLOGY', label: 'Oncology' },
  { value: 'RADIOLOGY', label: 'Radiology' },
  { value: 'LAB', label: 'Lab' },
  { value: 'PHARMACY', label: 'Pharmacy' },
  { value: 'EMERGENCY_24_7', label: 'Emergency 24/7' },
];

const STAFFING_OPTIONS: ReadonlyArray<{ value: StaffingQualifier; label: string }> = [
  { value: 'parttime', label: 'Part-time doctors' },
  { value: 'fulltime', label: 'Full-time doctors' },
  { value: 'twentyfour_seven', label: '24/7 staffed' },
  { value: 'low_volume', label: 'Low volume' },
];

const RADIUS_MIN = 5;
const RADIUS_MAX = 200;

const SELECT_CLASSES =
  'h-9 w-full rounded-md border border-border-subtle bg-surface-sunken px-2 text-body text-content-primary ' +
  'focus:outline-none focus:ring-2 focus:ring-accent-primary-subtle focus:border-border-strong';

/**
 * Filter / refinement controls for the planner page.
 *
 * All four controls are URL-state driven: changes call `onChange` immediately
 * so the parent page can serialize to query string. Pasting a deep link in a
 * new tab restores the full state.
 */
export function PlannerControls({ value, regions, onChange }: PlannerControlsProps) {
  const update = <K extends keyof PlannerControlsValue>(key: K, v: PlannerControlsValue[K]) => {
    onChange({ ...value, [key]: v });
  };

  const radiusValue = Number.isFinite(value.radiusKm) && value.radiusKm > 0 ? value.radiusKm : 50;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border-subtle bg-white p-4">
      <div className="text-caption font-semibold text-content-secondary uppercase tracking-wider">
        Refine
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="text-caption text-content-tertiary">Capability</span>
          <select
            className={SELECT_CLASSES}
            value={value.capability}
            onChange={(e) => update('capability', (e.target.value as CapabilityType) || '')}
          >
            <option value="">Any</option>
            {CAPABILITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-caption text-content-tertiary">Region</span>
          <select
            className={SELECT_CLASSES}
            value={value.regionId}
            onChange={(e) => update('regionId', e.target.value)}
          >
            <option value="">Any</option>
            {regions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-caption text-content-tertiary">
            Radius
            <span className="ml-1 font-mono text-content-primary">{radiusValue} km</span>
          </span>
          <input
            type="range"
            min={RADIUS_MIN}
            max={RADIUS_MAX}
            step={5}
            value={radiusValue}
            onChange={(e) => update('radiusKm', Number(e.target.value))}
            className="h-9 w-full"
            aria-label="Search radius in kilometers"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-caption text-content-tertiary">Staffing qualifier</span>
          <select
            className={SELECT_CLASSES}
            value={value.staffingQualifier}
            onChange={(e) =>
              update('staffingQualifier', (e.target.value as StaffingQualifier) || '')
            }
          >
            <option value="">Any</option>
            {STAFFING_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
