import { Field, type FieldText } from '../internal/Field';
import fieldStyles from '../internal/Field.module.css';
import styles from './TextArea.module.css';

export interface TextAreaProps extends FieldText {
  name: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  required?: boolean;
}

/** Spec 5.5: a labelled multi-line field. */
export function TextArea({
  name,
  value,
  onChange,
  rows = 3,
  required = false,
  ...text
}: TextAreaProps) {
  return (
    <Field {...text}>
      {(ids) => (
        <textarea
          {...ids}
          className={`${fieldStyles.control} ${styles.area}`}
          name={name}
          rows={rows}
          value={value}
          required={required}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}
