import { copy } from '../../copy/en-GB';
import { EmptyState } from '../../ui/EmptyState';
import { Stack } from '../../ui/Stack';

const t = copy.health;

/** The Health tab (spec 5.1); its screens arrive with their tasks. */
export function HealthScreen() {
  return (
    <Stack as="main" inset="page" gap={5}>
      <h1>{t.title}</h1>
      <EmptyState title={t.empty} body={t.emptyBody} icon="droplet" />
    </Stack>
  );
}
