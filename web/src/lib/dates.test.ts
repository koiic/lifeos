import { describe, expect, it, vi } from 'vitest';

import { formatDateTime } from './dates';

describe('formatDateTime (UK English, 24-hour)', () => {
  it('formats in the given timezone, day month year and 24-hour time', () => {
    expect(formatDateTime('2026-10-08T13:05:00Z', 'Europe/London')).toBe('8 Oct 2026, 14:05');
    expect(formatDateTime('2026-01-08T13:05:00Z', 'Europe/London')).toBe('8 Jan 2026, 13:05');
  });

  it('defaults to the device timezone', () => {
    const resolved = Intl.DateTimeFormat().resolvedOptions();
    const spy = vi
      .spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions')
      .mockReturnValue({ ...resolved, timeZone: 'Asia/Tokyo' });
    try {
      expect(formatDateTime('2026-10-08T13:05:00Z')).toBe('8 Oct 2026, 22:05');
    } finally {
      spy.mockRestore();
    }
  });
});
