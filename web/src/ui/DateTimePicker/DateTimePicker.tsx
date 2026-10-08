import { Field, type FieldText } from '../internal/Field';
import styles from './DateTimePicker.module.css';

export interface DateTimePickerProps extends FieldText {
  name: string;
  kind: 'date' | 'time' | 'datetime-local';
  /** `YYYY-MM-DD`, `HH:MM` or `YYYY-MM-DDTHH:MM` (spec 9.1 local values). */
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  required?: boolean;
}

/** Spec 5.5: the browser's own date and time inputs, styled (they are accessible everywhere). */
export function DateTimePicker({
  name,
  kind,
  value,
  onChange,
  min,
  max,
  required = false,
  ...text
}: DateTimePickerProps) {
  return (
    <Field {...text}>
      {(ids) => (
        <input
          {...ids}
          className={styles.input}
          name={name}
          type={kind}
          value={value}
          min={min}
          max={max}
          required={required}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}
