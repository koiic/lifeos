import { useEffect, useRef, useState } from 'react';

import { copy } from '../../copy/en-GB';
import { useChangeSettings, useMe } from '../../lib/me/me';
import { applyTheme, type ThemeSetting } from '../../lib/theme/theme';
import { rememberTheme } from '../../lib/theme/ThemeSync';
import { ChipGroup } from '../../ui/Chip';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';

const t = copy.theme;

const OPTIONS = [
  { value: 'system', label: t.system },
  { value: 'light', label: t.light },
  { value: 'dark', label: t.dark },
] as const;

/** SET-2: Light (Sorbet), Dark (Night Garden), System (default); applied as soon as she picks. */
export function ThemeScreen() {
  const me = useMe();
  const change = useChangeSettings();
  const heading = useRef<HTMLHeadingElement>(null);
  const [chosen, setChosen] = useState<ThemeSetting | null>(null);
  const [failed, setFailed] = useState(false);
  const stop = useRef<() => void>(() => undefined);

  useEffect(() => {
    heading.current?.focus();
    return () => stop.current();
  }, []);

  if (me.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'line']} />
      </Stack>
    );
  }
  if (me.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void me.refetch() }}
        />
      </Stack>
    );
  }

  const saved = me.data.settings.theme;
  const show = (setting: ThemeSetting) => {
    stop.current();
    stop.current = applyTheme(setting);
    rememberTheme(setting);
  };
  const pick = (setting: ThemeSetting) => {
    setFailed(false);
    setChosen(setting);
    show(setting);
    change.mutate(
      { theme: setting },
      {
        onError: () => {
          setChosen(null);
          show(saved);
          setFailed(true);
        },
      },
    );
  };

  return (
    <Stack as="main" inset="page" gap={5}>
      <h1 ref={heading} tabIndex={-1}>
        {t.title}
      </h1>
      <ChipGroup
        legend={t.legend}
        name="theme"
        options={OPTIONS}
        value={chosen ?? saved}
        onChange={pick}
      />
      <p>{t.systemHint}</p>
      <p role="alert">{failed ? t.failed : null}</p>
    </Stack>
  );
}
