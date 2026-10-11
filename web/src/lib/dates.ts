// Date display for features (plan 4.3: dates through date-fns / date-fns-tz here only; features
// never use Date directly). UK English, 24-hour time (CLAUDE.md project facts). Dates display in
// her profile timezone (spec 11.7, from `GET /me`); the device's is only the fallback.
import { enGB } from 'date-fns/locale';
import { formatInTimeZone } from 'date-fns-tz';

function deviceTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** "8 Oct 2026, 14:05" for an ISO timestamp, in `timeZone` (default: the device's). */
export function formatDateTime(iso: string, timeZone: string = deviceTimeZone()): string {
  return formatInTimeZone(iso, timeZone, 'd MMM yyyy, HH:mm', { locale: enGB });
}

/** Today's date line, "Thursday 8 October", in `timeZone` (TOD-1). */
export function formatTodayDate(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'EEEE d MMMM', { locale: enGB });
}

/** "2026-10-08" for an ISO timestamp, in `timeZone` (default: the device's). */
export function formatIsoDate(iso: string, timeZone: string = deviceTimeZone()): string {
  return formatInTimeZone(iso, timeZone, 'yyyy-MM-dd');
}

/** The current instant as an ISO string (features never use `Date` directly, plan 4.3). */
export function nowIso(): string {
  return new Date().toISOString();
}

/** The city of an IANA zone, for "You seem to be in Lagos" (spec 11.7). */
export function cityOf(timeZone: string): string {
  return (timeZone.split('/').pop() ?? timeZone).replace(/_/g, ' ');
}

/** Step a month string "YYYY-MM" by delta months (CSC-3). */
export function stepMonth(month: string, delta: number): string {
  const [yearStr, monthStr] = month.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const date = new Date(Date.UTC(year, monthNum - 1 + delta, 1));
  const nextYear = date.getUTCFullYear();
  const nextMonthNum = date.getUTCMonth() + 1;
  return `${String(nextYear)}-${String(nextMonthNum).padStart(2, '0')}`;
}

/** Format month header "October 2026" (CSC-3). */
export function formatMonthHeader(month: string): string {
  const [yearStr, monthStr] = month.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const date = new Date(Date.UTC(year, monthNum - 1, 1));
  return formatInTimeZone(date, 'UTC', 'MMMM yyyy', { locale: enGB });
}

/** Get calendar grid info: number of days in month and starting weekday (Mon = 0 ... Sun = 6) (CSC-3). */
export function getMonthGrid(month: string): { daysInMonth: number; startWeekday: number } {
  const [yearStr, monthStr] = month.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const firstDay = new Date(Date.UTC(year, monthNum - 1, 1));
  const lastDay = new Date(Date.UTC(year, monthNum, 0));
  const startWeekday = (firstDay.getUTCDay() + 6) % 7;
  return {
    daysInMonth: lastDay.getUTCDate(),
    startWeekday,
  };
}

/** Format accessible button label for calendar day (CSC-3). */
export function formatDayAriaLabel(dateIso: string, descriptions: string[] = []): string {
  const [yearStr, monthStr, dayStr] = dateIso.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const day = parseInt(dayStr ?? '1', 10);
  const date = new Date(Date.UTC(year, monthNum - 1, day));
  const base = formatInTimeZone(date, 'UTC', 'd MMMM yyyy', { locale: enGB });
  return descriptions.length > 0 ? `${base}, ${descriptions.join(', ')}` : base;
}

/** "8 Oct" for an ISO date YYYY-MM-DD. */
export function formatDayMonth(dateIso: string): string {
  const [yearStr, monthStr, dayStr] = dateIso.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const day = parseInt(dayStr ?? '1', 10);
  const date = new Date(Date.UTC(year, monthNum - 1, day));
  return formatInTimeZone(date, 'UTC', 'd MMM', { locale: enGB });
}

/** "8 Oct 2026" for an ISO date YYYY-MM-DD. */
export function formatDayMonthYear(dateIso: string): string {
  const [yearStr, monthStr, dayStr] = dateIso.split('-');
  const year = parseInt(yearStr ?? '2026', 10);
  const monthNum = parseInt(monthStr ?? '10', 10);
  const day = parseInt(dayStr ?? '1', 10);
  const date = new Date(Date.UTC(year, monthNum - 1, day));
  return formatInTimeZone(date, 'UTC', 'd MMM yyyy', { locale: enGB });
}

/** Calculate the difference in calendar days between two ISO dates (b - a). */
export function differenceInCalendarDays(startIso: string, endIso: string): number {
  const [y1, m1, d1] = startIso.split('-');
  const [y2, m2, d2] = endIso.split('-');
  const dStart = new Date(
    Date.UTC(parseInt(y1 ?? '2026', 10), parseInt(m1 ?? '10', 10) - 1, parseInt(d1 ?? '1', 10)),
  );
  const dEnd = new Date(
    Date.UTC(parseInt(y2 ?? '2026', 10), parseInt(m2 ?? '10', 10) - 1, parseInt(d2 ?? '1', 10)),
  );
  return Math.round((dEnd.getTime() - dStart.getTime()) / 86400000);
}
