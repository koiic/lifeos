import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { copy } from '../../copy/en-GB';
import { ApiError } from '../../lib/api';
import { bindField } from '../../lib/forms/bindField';
import { zodResolver } from '../../lib/forms/zodResolver';
import {
  ME_KEY,
  type Me,
  type ProfileChange,
  type SettingsChange,
  useChangeProfile,
  useChangeSettings,
  useMe,
} from '../../lib/me/me';
import { Button } from '../../ui/Button';
import { ErrorState } from '../../ui/ErrorState';
import { Select } from '../../ui/Select';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import { TextField } from '../../ui/TextField';

const t = copy.profile;
const NAME_MAX = 100; // spec 9.4 via T09: 1–100 characters once trimmed

const schema = z.object({
  display_name: z
    .string()
    .trim()
    .min(1, { message: t.nameRequired })
    .max(NAME_MAX, { message: t.nameTooLong }),
  timezone: z.string().min(1),
  week_start: z.enum(['1', '2', '3', '4', '5', '6', '7']),
  temp_unit: z.enum(['C', 'F']),
});
type Values = z.infer<typeof schema>;

const WEEK_DAYS = t.days.map((label, index) => ({
  value: String(index + 1) as Values['week_start'],
  label,
}));
const UNITS = [
  { value: 'C', label: t.celsius },
  { value: 'F', label: t.fahrenheit },
] as const;

/** IANA zones the browser knows, with hers always among them. */
function timezones(current: string): { value: string; label: string }[] {
  const known = Intl.supportedValuesOf('timeZone');
  const zones = known.includes(current) ? known : [current, ...known];
  return zones.map((zone) => ({ value: zone, label: zone.replace(/_/g, ' ') }));
}

function valuesOf(me: Me): Values {
  return {
    display_name: me.profile.display_name,
    timezone: me.profile.timezone,
    week_start: String(me.settings.week_start) as Values['week_start'],
    temp_unit: me.settings.temp_unit,
  };
}

/** SET-1: her name, timezone (auto-detected, editable), week start and temperature unit. */
export function ProfileScreen() {
  const me = useMe();
  const queryClient = useQueryClient();
  const changeProfile = useChangeProfile();
  const changeSettings = useChangeSettings();
  const heading = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState<{ text: string; tone: 'ok' | 'error' } | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: '', timezone: '', week_start: '1', temp_unit: 'C' },
  });
  const loaded = me.data;
  const [timezone, weekStart, tempUnit] = useWatch({
    control: form.control,
    name: ['timezone', 'week_start', 'temp_unit'],
  });
  const saved = status?.tone === 'ok' ? status.text : null;
  const problem = status?.tone === 'error' ? status.text : null;

  useEffect(() => {
    if (loaded !== undefined && !form.formState.isDirty) form.reset(valuesOf(loaded));
  }, [loaded, form]);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  if (me.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'line', 'line']} />
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

  const save = form.handleSubmit(async (values) => {
    setStatus(null);
    const saved = me.data;
    const profile: ProfileChange = {};
    if (values.display_name !== saved.profile.display_name)
      profile.display_name = values.display_name;
    if (values.timezone !== saved.profile.timezone) profile.timezone = values.timezone;
    const settings: SettingsChange = {};
    const weekStart = Number(values.week_start);
    if (weekStart !== saved.settings.week_start) settings.week_start = weekStart;
    if (values.temp_unit !== saved.settings.temp_unit) settings.temp_unit = values.temp_unit;
    try {
      if (Object.keys(profile).length > 0) await changeProfile.mutateAsync(profile);
      if (Object.keys(settings).length > 0) await changeSettings.mutateAsync(settings);
      setStatus({ text: t.saved, tone: 'ok' });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setStatus({ text: t.conflict, tone: 'error' });
        // The conflict put the server's current values in the cache (lib/me).
        const latest = queryClient.getQueryData<Me>(ME_KEY);
        if (latest !== undefined) form.reset(valuesOf(latest));
      } else {
        setStatus({ text: t.failed, tone: 'error' });
      }
    }
  });

  return (
    <Stack as="main" inset="page" gap={5}>
      <h1 ref={heading} tabIndex={-1}>
        {t.title}
      </h1>
      <Stack as="form" gap={4}>
        <TextField
          label={t.name}
          hint={t.nameHint}
          autoComplete="name"
          {...bindField(form, 'display_name')}
        />
        <Select
          name="timezone"
          label={t.timezone}
          hint={t.timezoneHint}
          options={timezones(timezone || me.data.profile.timezone)}
          value={timezone}
          onChange={(value) => form.setValue('timezone', value, { shouldDirty: true })}
        />
        <Select
          name="week_start"
          label={t.weekStart}
          options={WEEK_DAYS}
          value={weekStart}
          onChange={(value) => form.setValue('week_start', value, { shouldDirty: true })}
        />
        <Select
          name="temp_unit"
          label={t.temperature}
          options={UNITS}
          value={tempUnit}
          onChange={(value) => form.setValue('temp_unit', value, { shouldDirty: true })}
        />
        <p role="status">{saved}</p>
        <p role="alert">{problem}</p>
        <Button busy={form.formState.isSubmitting} onClick={() => void save()}>
          {t.save}
        </Button>
      </Stack>
    </Stack>
  );
}
