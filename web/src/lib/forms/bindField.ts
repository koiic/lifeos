import type { FieldPath, FieldValues, PathValue, UseFormReturn } from 'react-hook-form';

export interface BoundField {
  name: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

/**
 * Props for a controlled `src/ui` text control (TextField) from a React Hook Form form: its value,
 * its change handler (re-validating once the form has been submitted) and its first error.
 */
export function bindField<T extends FieldValues>(
  form: UseFormReturn<T>,
  name: FieldPath<T>,
): BoundField {
  const message = form.formState.errors[name]?.message;
  const value: unknown = form.watch(name);
  return {
    name,
    value: typeof value === 'string' ? value : '',
    onChange: (next) =>
      form.setValue(name, next as PathValue<T, FieldPath<T>>, {
        shouldValidate: form.formState.isSubmitted,
        shouldDirty: true,
      }),
    ...(typeof message === 'string' ? { error: message } : {}),
  };
}
