import { Field, type FieldText } from '../internal/Field';
import styles from './Select.module.css';

export interface SelectOption<V extends string> {
  value: V;
  label: string;
}

export interface SelectProps<V extends string> extends FieldText {
  name: string;
  options: readonly SelectOption<V>[];
  value: V;
  onChange: (value: V) => void;
}

/** Spec 5.5: a labelled native select. */
export function Select<V extends string>({
  name,
  options,
  value,
  onChange,
  ...text
}: SelectProps<V>) {
  return (
    <Field {...text}>
      {(ids) => (
        <select
          {...ids}
          className={styles.select}
          name={name}
          value={value}
          onChange={(event) => {
            const chosen = options.find((option) => option.value === event.target.value);
            if (chosen !== undefined) onChange(chosen.value);
          }}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}
