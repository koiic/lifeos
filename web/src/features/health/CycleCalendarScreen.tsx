import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import { useCalendarMonth } from '../../lib/api';
import { formatIsoDate, nowIso, stepMonth } from '../../lib/dates';
import { useMe } from '../../lib/me/me';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import { MonthCalendar } from './MonthCalendar';
import { PeriodControls } from './PeriodControls';

export interface CycleCalendarScreenProps {
  initialMonth?: string | undefined;
  onSelectDate?: ((date: string) => void) | undefined;
}

/**
 * Spec 5.2, CSC-3, PER-1, PER-3:
 * Cycle calendar screen with month grid, period start/end controls, and day tap-through editing.
 */
export function CycleCalendarScreen({ initialMonth, onSelectDate }: CycleCalendarScreenProps) {
  const navigate = useNavigate();
  const me = useMe();
  const timezone = me.data?.profile.timezone;
  const todayIso = formatIsoDate(nowIso(), timezone);
  const currentMonthStr = todayIso.slice(0, 7);

  const [month, setMonth] = useState<string>(initialMonth ?? currentMonthStr);
  const [endedDate, setEndedDate] = useState<string | null>(() => {
    try {
      return localStorage.getItem('lifeos:period-ended-date');
    } catch {
      return null;
    }
  });

  const calendarQuery = useCalendarMonth(month);

  const handleStarted = () => {
    setEndedDate(null);
    try {
      localStorage.removeItem('lifeos:period-ended-date');
    } catch {
      // ignore
    }
  };

  const handleEnded = () => {
    setEndedDate(todayIso);
    try {
      localStorage.setItem('lifeos:period-ended-date', todayIso);
    } catch {
      // ignore
    }
  };

  const handleSelectDate =
    onSelectDate ??
    ((date: string) => {
      navigate(`/checkin?date=${date}`);
    });

  if (calendarQuery.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'block']} />
      </Stack>
    );
  }

  if (calendarQuery.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void calendarQuery.refetch() }}
        />
      </Stack>
    );
  }

  const days = calendarQuery.data.days;
  const todayDay = days.find((d) => d.date === todayIso);
  const isPeriodOngoing = Boolean(
    todayDay && todayDay.flow && todayDay.flow !== 'none' && endedDate !== todayIso,
  );

  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={2}>
        <h1>{copy.health.calendar.title}</h1>
        <PeriodControls
          isOngoing={isPeriodOngoing}
          currentDate={todayIso}
          ongoingStartDate={isPeriodOngoing ? todayIso : undefined}
          onStarted={handleStarted}
          onEnded={handleEnded}
        />
      </Stack>

      <MonthCalendar
        month={month}
        days={days}
        todayDate={todayIso}
        onPrevMonth={() => setMonth((prev) => stepMonth(prev, -1))}
        onNextMonth={() => setMonth((prev) => stepMonth(prev, 1))}
        onSelectDate={handleSelectDate}
      />
    </Stack>
  );
}
