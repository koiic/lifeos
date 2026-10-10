// Test helper: a `GET /me` body (T09, CR-030) with her defaults, for screens that read it.
import type { components } from '../api';

type Me = components['schemas']['Me'];

export function meBody(
  overrides: {
    profile?: Partial<Me['profile']>;
    settings?: Partial<Me['settings']>;
    device_timezone?: string | null;
    timezone_differs?: boolean;
  } = {},
): Me {
  return {
    profile: {
      id: '0192f2aa-0000-7000-8000-000000000001',
      email: 'zee@example.test',
      display_name: 'Zee',
      role: 'user',
      timezone: 'Europe/London',
      locale: 'en-GB',
      version: 'p1',
      ...overrides.profile,
    },
    settings: {
      theme: 'system',
      week_start: 1,
      time_format: '24h',
      temp_unit: 'C',
      checkin_time: '20:00',
      quiet_start: '22:00',
      quiet_end: '07:00',
      notif_prefs: {
        checkin: true,
        period_due: true,
        late_period: true,
        medication: true,
        appointment: true,
        task: true,
      },
      discreet_notifications: false,
      optional_fields: { bbt: false, discharge: false, intimacy: false },
      app_lock_enabled: false,
      app_lock_timeout_s: 300,
      appointment_reminder_defaults: [],
      onboarding_completed_at: null,
      version: 's1',
      ...overrides.settings,
    },
    consent: { current_version: '1', version: null, given_at: null },
    health_mode: 'standard',
    device_timezone: overrides.device_timezone ?? null,
    timezone_differs: overrides.timezone_differs ?? false,
  };
}
