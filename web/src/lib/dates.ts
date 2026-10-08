// Date display for features (plan 4.3: dates through date-fns / date-fns-tz here only; features
// never use Date directly). UK English, 24-hour time (CLAUDE.md project facts). The profile
// timezone arrives with `GET /me` (T09); until then the device's timezone is used.
import { enGB } from 'date-fns/locale';
import { formatInTimeZone } from 'date-fns-tz';

function deviceTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** "8 Oct 2026, 14:05" for an ISO timestamp, in `timeZone` (default: the device's). */
export function formatDateTime(iso: string, timeZone: string = deviceTimeZone()): string {
  return formatInTimeZone(iso, timeZone, 'd MMM yyyy, HH:mm', { locale: enGB });
}
