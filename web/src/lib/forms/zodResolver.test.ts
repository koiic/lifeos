import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { zodResolver } from './zodResolver';

const schema = z.object({
  email: z.string().email({ message: 'Enter an email address' }),
  pin: z.string().regex(/^\d{6}$/, { message: 'Six digits' }),
});

const options = { fields: {}, shouldUseNativeValidation: false } as const;

describe('zodResolver (spec 11.7: React Hook Form with Zod)', () => {
  it('returns the parsed values when valid', async () => {
    const result = await zodResolver(schema)(
      { email: 'zee@example.test', pin: '123456' },
      undefined,
      options,
    );
    expect(result).toEqual({ values: { email: 'zee@example.test', pin: '123456' }, errors: {} });
  });

  it('returns one message per invalid field, keyed by field', async () => {
    const result = await zodResolver(schema)({ email: 'nope', pin: '12' }, undefined, options);
    expect(result.values).toEqual({});
    expect(result.errors).toMatchObject({
      email: { type: 'invalid_format', message: 'Enter an email address' },
      pin: { message: 'Six digits' },
    });
  });
});
