import { useState } from 'react';

import { copy } from '../../copy/en-GB';
import { useEndPeriod, useStartPeriod } from '../../lib/api';
import { Button } from '../../ui/Button';
import { Stack } from '../../ui/Stack';

export interface PeriodControlsProps {
  isOngoing?: boolean | undefined;
  ongoingStartDate?: string | undefined;
  currentDate?: string | undefined;
  onStarted?: (() => void) | undefined;
  onEnded?: (() => void) | undefined;
}

/**
 * Spec 4.5, PER-1:
 * Start and end a period in one tap each.
 */
export function PeriodControls({
  isOngoing = false,
  ongoingStartDate,
  currentDate,
  onStarted,
  onEnded,
}: PeriodControlsProps) {
  const startPeriod = useStartPeriod();
  const endPeriod = useEndPeriod();
  const [error, setError] = useState<string | null>(null);

  const handleStart = async () => {
    setError(null);
    try {
      await startPeriod.mutateAsync(currentDate ? { date: currentDate } : {});
      onStarted?.();
    } catch {
      setError(copy.common.networkError);
    }
  };

  const handleEnd = async () => {
    setError(null);
    try {
      await endPeriod.mutateAsync(currentDate ? { date: currentDate } : {});
      onEnded?.();
    } catch {
      setError(copy.common.networkError);
    }
  };

  return (
    <Stack gap={2}>
      {error && <p role="alert">{error}</p>}
      {isOngoing ? (
        <Stack gap={2}>
          {ongoingStartDate && <p>{copy.health.period.ongoing(ongoingStartDate)}</p>}
          <Button variant="secondary" onClick={() => void handleEnd()} busy={endPeriod.isPending}>
            {copy.health.period.ended}
          </Button>
        </Stack>
      ) : (
        <Button variant="primary" onClick={() => void handleStart()} busy={startPeriod.isPending}>
          {copy.health.period.started}
        </Button>
      )}
    </Stack>
  );
}
