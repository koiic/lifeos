import { describe, expect, it, vi } from 'vitest';

import { cityOf, formatDateTime, formatTodayDate } from './dates';

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

describe('[TOD-1] the date on Today (en-GB)', () => {
  it('is the weekday, day and month in her timezone', () => {
    expect(formatTodayDate('2026-10-08T13:05:00Z', 'Europe/London')).toBe('Thursday 8 October');
    // 23:30 UTC is already Friday in Lagos (UTC+1).
    expect(formatTodayDate('2026-10-08T23:30:00Z', 'Africa/Lagos')).toBe('Friday 9 October');
  });
});

describe('cityOf (the "You seem to be in Lagos" prompt, spec 11.7)', () => {
  it.each([
    ['Africa/Lagos', 'Lagos'],
    ['Europe/London', 'London'],
    ['America/Argentina/Buenos_Aires', 'Buenos Aires'],
    ['UTC', 'UTC'],
  ])('%s → %s', (zone, city) => {
    expect(cityOf(zone)).toBe(city);
  });
});
