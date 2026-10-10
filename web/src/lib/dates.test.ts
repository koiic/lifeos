import { describe, expect, it, vi } from 'vitest';

import {
  cityOf,
  formatDateTime,
  formatDayAriaLabel,
  formatIsoDate,
  formatMonthHeader,
  formatTodayDate,
  getMonthGrid,
  stepMonth,
} from './dates';

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

describe('formatIsoDate (YYYY-MM-DD)', () => {
  it('formats timestamp to YYYY-MM-DD in the given timezone', () => {
    expect(formatIsoDate('2026-10-08T13:05:00Z', 'Europe/London')).toBe('2026-10-08');
    expect(formatIsoDate('2026-10-08T23:30:00Z', 'Africa/Lagos')).toBe('2026-10-09');
  });
});

describe('calendar month helpers (CSC-3)', () => {
  it('stepMonth steps forwards and backwards across month and year boundaries', () => {
    expect(stepMonth('2026-10', 1)).toBe('2026-11');
    expect(stepMonth('2026-10', -1)).toBe('2026-09');
    expect(stepMonth('2026-12', 1)).toBe('2027-01');
    expect(stepMonth('2026-01', -1)).toBe('2025-12');
  });

  it('formatMonthHeader formats month and year in en-GB', () => {
    expect(formatMonthHeader('2026-10')).toBe('October 2026');
    expect(formatMonthHeader('2026-05')).toBe('May 2026');
  });

  it('getMonthGrid calculates correct days and starting weekday', () => {
    // 1 Oct 2026 is Thursday -> startWeekday 3 (Mon=0, Tue=1, Wed=2, Thu=3)
    const oct = getMonthGrid('2026-10');
    expect(oct.daysInMonth).toBe(31);
    expect(oct.startWeekday).toBe(3);
  });

  it('formatDayAriaLabel formats accessible date with optional descriptions', () => {
    expect(formatDayAriaLabel('2026-10-05')).toBe('5 October 2026');
    expect(formatDayAriaLabel('2026-10-05', ['medium flow', 'today'])).toBe(
      '5 October 2026, medium flow, today',
    );
  });
});
