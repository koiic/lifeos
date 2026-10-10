import { copy } from '../../copy/en-GB';
import { Button } from '../../ui/Button';
import { Stack } from '../../ui/Stack';

const t = copy.more;

/**
 * The More tab (spec 5.1): Tasks, Notes, People, Reminder inbox, Settings. Each entry appears
 * with its screen; Settings is the first.
 */
export function MoreScreen() {
  return (
    <Stack as="main" inset="page" gap={5}>
      <h1>{t.title}</h1>
      <Stack as="ul" gap={2}>
        <li>
          <Button href="/settings" variant="secondary" icon="settings">
            {t.settings}
          </Button>
        </li>
      </Stack>
    </Stack>
  );
}
