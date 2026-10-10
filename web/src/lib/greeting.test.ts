import { describe, expect, it } from 'vitest';

import { greetingFor } from './greeting';

describe('[TOD-1] the salutation by her local time', () => {
  it.each([
    ['2026-10-08T04:59:00Z', 'night'],
    ['2026-10-08T05:00:00Z', 'morning'],
    ['2026-10-08T11:59:00Z', 'morning'],
    ['2026-10-08T12:00:00Z', 'afternoon'],
    ['2026-10-08T16:59:00Z', 'afternoon'],
    ['2026-10-08T17:00:00Z', 'evening'],
    ['2026-10-08T21:59:00Z', 'evening'],
    ['2026-10-08T22:00:00Z', 'night'],
    ['2026-10-08T00:30:00Z', 'night'],
  ])('%s in UTC is %s', (iso, expected) => {
    expect(greetingFor(iso, 'UTC')).toBe(expected);
  });

  it('uses her timezone, not the device clock (BST is UTC+1 in October)', () => {
    expect(greetingFor('2026-10-08T11:30:00Z', 'Europe/London')).toBe('afternoon');
    expect(greetingFor('2026-10-08T04:30:00Z', 'Europe/London')).toBe('morning');
    expect(greetingFor('2026-10-08T04:30:00Z', 'Asia/Tokyo')).toBe('afternoon');
  });
});
