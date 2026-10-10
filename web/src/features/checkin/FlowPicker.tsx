import { copy } from '../../copy/en-GB';
import { ChipGroup, type ChipOption } from '../../ui/Chip';

export type FlowLevel = 'none' | 'spotting' | 'light' | 'medium' | 'heavy';

const t = copy.checkin.flow;

const FLOW_OPTIONS: readonly ChipOption<FlowLevel>[] = [
  { value: 'none', label: t.none },
  { value: 'spotting', label: t.spotting },
  { value: 'light', label: t.light },
  { value: 'medium', label: t.medium },
  { value: 'heavy', label: t.heavy },
] as const;

export interface FlowPickerProps {
  value: FlowLevel;
  onChange: (value: FlowLevel) => void;
  disabled?: boolean;
}

/** Bleeding flow level picker (CHK-1, PER-2). */
export function FlowPicker({ value, onChange }: FlowPickerProps) {
  return (
    <ChipGroup<FlowLevel>
      legend={t.label}
      name="flow"
      options={FLOW_OPTIONS}
      value={value}
      onChange={onChange}
    />
  );
}
