import { act, renderHook } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { bindField } from './bindField';
import { zodResolver } from './zodResolver';

const schema = z.object({ pin: z.string().regex(/^\d{6}$/, 'Six digits') });

function useTestForm() {
  return useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { pin: '' },
  });
}

describe('bindField', () => {
  it('gives a TextField its value and change handler', () => {
    const { result } = renderHook(() => {
      const form = useTestForm();
      return { form, field: bindField(form, 'pin') };
    });
    expect(result.current.field).toMatchObject({ name: 'pin', value: '' });
    expect(result.current.field.error).toBeUndefined();
    act(() => result.current.field.onChange('123456'));
    expect(result.current.field.value).toBe('123456');
  });

  it('shows the first error after submitting, and clears it once fixed', async () => {
    const { result } = renderHook(() => {
      const form = useTestForm();
      return { form, field: bindField(form, 'pin') };
    });
    await act(() => result.current.form.handleSubmit(() => undefined)());
    expect(result.current.field.error).toBe('Six digits');
    await act(async () => {
      result.current.field.onChange('123456');
      await Promise.resolve();
    });
    expect(result.current.field.error).toBeUndefined();
  });
});
