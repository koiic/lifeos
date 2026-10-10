// TOD-1: "Morning/afternoon/evening/night by local time" — her profile timezone (spec 11.7).
import { formatInTimeZone } from 'date-fns-tz';

export type Greeting = 'morning' | 'afternoon' | 'evening' | 'night';

/**
 * The salutation for `iso` in `timeZone`. The spec names the four parts of the day but not their
 * hours: morning 05:00–11:59, afternoon 12:00–16:59, evening 17:00–21:59, night 22:00–04:59.
 */
export function greetingFor(iso: string, timeZone: string): Greeting {
  const hour = Number(formatInTimeZone(iso, timeZone, 'H'));
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 17) return 'afternoon';
  if (hour >= 17 && hour < 22) return 'evening';
  return 'night';
}
