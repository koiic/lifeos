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

/** The current instant as an ISO string (features never use `Date` directly, plan 4.3). */
export function nowIso(): string {
  return new Date().toISOString();
}

/** The city of an IANA zone, for "You seem to be in Lagos" (spec 11.7). */
export function cityOf(timeZone: string): string {
  return (timeZone.split('/').pop() ?? timeZone).replace(/_/g, ' ');
}
