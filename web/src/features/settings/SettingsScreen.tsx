import { copy } from '../../copy/en-GB';
import { Button } from '../../ui/Button';
import { Stack } from '../../ui/Stack';

const t = copy.settingsHome;

const ENTRIES = [
  { href: '/settings/profile', label: t.profile },
  { href: '/settings/theme', label: t.theme },
  { href: '/settings/security', label: t.security },
  { href: '/setup/notifications', label: t.notifications },
] as const;

/** Spec 5.2 Settings (`/settings/*`); health mode, symptoms, optional fields, your data and
 * about join as their tasks arrive. */
export function SettingsScreen() {
  return (
    <Stack as="main" inset="page" gap={5}>
      <h1>{t.title}</h1>
      <Stack as="ul" gap={2}>
        {ENTRIES.map((entry) => (
          <li key={entry.href}>
            <Button href={entry.href} variant="secondary">
              {entry.label}
            </Button>
          </li>
        ))}
      </Stack>
    </Stack>
  );
}
