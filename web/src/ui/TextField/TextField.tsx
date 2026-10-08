import { Field, type FieldText } from '../internal/Field';
import styles from './TextField.module.css';

export interface TextFieldProps extends FieldText {
  name: string;
  value: string;
  onChange: (value: string) => void;
  type?: 'text' | 'email' | 'password' | 'tel' | 'number';
  required?: boolean;
  autoComplete?: string;
}

/** Spec 5.5: a labelled single-line field with an optional hint and error. */
export function TextField({
  name,
  value,
  onChange,
  type = 'text',
  required = false,
  autoComplete,
  ...text
}: TextFieldProps) {
  return (
    <Field {...text}>
      {(ids) => (
        <input
          {...ids}
          className={styles.input}
          name={name}
          type={type}
          value={value}
          required={required}
          autoComplete={autoComplete}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}
