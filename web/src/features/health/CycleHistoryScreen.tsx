import { useState } from 'react';
import { Link } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import { useCyclesHistory, useSetCycleExclusion, type CycleHistoryItem } from '../../lib/api';
import { formatDayMonthYear } from '../../lib/dates';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Dialog } from '../../ui/Dialog';
import { EmptyState } from '../../ui/EmptyState';
import { ErrorState } from '../../ui/ErrorState';
import { Icon } from '../../ui/icons';
import { Select } from '../../ui/Select';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import styles from './CycleHistoryScreen.module.css';

const t = copy.health.history;

/**
 * Spec 5.2, CSC-4, CSC-5, CYC-5:
 * Cycle history screen displaying summary averages and the list of past cycles
 * with include/exclude toggle and reason annotation.
 */
export function CycleHistoryScreen() {
  const cyclesQuery = useCyclesHistory();
  const setExclusion = useSetCycleExclusion();

  const [excludeTarget, setExcludeTarget] = useState<CycleHistoryItem | null>(null);
  const [selectedReason, setSelectedReason] = useState<string>('illness');

  if (cyclesQuery.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'block', 'block']} />
      </Stack>
    );
  }

  if (cyclesQuery.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void cyclesQuery.refetch() }}
        />
      </Stack>
    );
  }

  const cycles = cyclesQuery.data ?? [];

  if (cycles.length === 0) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <div className={styles.headerRow}>
          <Link to="/health/cycle" className={styles.backLink}>
            <Icon name="chevronLeft" />
            <span>{t.back}</span>
          </Link>
        </div>
        <h1>{t.title}</h1>
        <EmptyState title={t.empty} body={t.emptyBody} icon="droplet" />
      </Stack>
    );
  }

  // Calculate averages from completed, non-excluded cycles (CSC-5)
  const includedCycles = cycles.filter(
    (c) => !c.excluded && c.is_complete && typeof c.length_days === 'number',
  );

  let avgCycleLength: number | null = null;
  let minCycleLength: number | null = null;
  let maxCycleLength: number | null = null;
  let avgPeriodLength: number | null = null;

  if (includedCycles.length > 0) {
    const totalCycleDays = includedCycles.reduce((sum, c) => sum + (c.length_days ?? 0), 0);
    const totalPeriodDays = includedCycles.reduce((sum, c) => sum + c.period_length_days, 0);
    avgCycleLength = Math.round(totalCycleDays / includedCycles.length);
    avgPeriodLength = Math.round(totalPeriodDays / includedCycles.length);
    const lengths = includedCycles.map((c) => c.length_days as number);
    minCycleLength = Math.min(...lengths);
    maxCycleLength = Math.max(...lengths);
  }

  const handleToggleExclude = (cycle: CycleHistoryItem) => {
    if (cycle.excluded) {
      // Re-include cycle
      setExclusion.mutate({
        start_date: cycle.start_date,
        excluded: false,
      });
    } else {
      // Prompt for exclusion
      setExcludeTarget(cycle);
      setSelectedReason('illness');
    }
  };

  const handleConfirmExclude = () => {
    if (!excludeTarget) return;
    setExclusion.mutate(
      {
        start_date: excludeTarget.start_date,
        excluded: true,
        reason: selectedReason,
      },
      {
        onSettled: () => setExcludeTarget(null),
      },
    );
  };

  return (
    <Stack as="main" inset="page" gap={5}>
      <div className={styles.headerRow}>
        <Link to="/health/cycle" className={styles.backLink}>
          <Icon name="chevronLeft" />
          <span>{t.back}</span>
        </Link>
      </div>

      <h1>{t.title}</h1>

      {/* Summary Averages Card (CSC-5) */}
      {avgCycleLength !== null && avgPeriodLength !== null && (
        <Card tone="surface">
          <Stack gap={2}>
            <h2>{t.averages.title}</h2>
            <div className={styles.averagesGrid}>
              <div className={styles.statItem}>
                <span className={styles.statValue}>{t.averages.cycleLength(avgCycleLength)}</span>
                <span className={styles.statLabel}>{t.averages.cycleLabel}</span>
              </div>
              {minCycleLength !== null &&
                maxCycleLength !== null &&
                minCycleLength !== maxCycleLength && (
                  <div className={styles.statItem}>
                    <span className={styles.statValue}>
                      {t.averages.cycleRange(minCycleLength, maxCycleLength)}
                    </span>
                    <span className={styles.statLabel}>{t.averages.rangeLabel}</span>
                  </div>
                )}
              <div className={styles.statItem}>
                <span className={styles.statValue}>{t.averages.periodLength(avgPeriodLength)}</span>
                <span className={styles.statLabel}>{t.averages.periodLabel}</span>
              </div>
            </div>
          </Stack>
        </Card>
      )}

      {/* Cycles List (CSC-4, CYC-5) */}
      <Stack gap={3}>
        {cycles.map((cycle) => {
          const isOngoing = !cycle.is_complete;
          const lengthDisplay = cycle.length_days
            ? t.cycleItem.length(cycle.length_days)
            : t.cycleItem.ongoing;
          let cardClass = styles.cycleCard;
          if (cycle.excluded) {
            cardClass = [styles.cycleCard, styles.cycleCardExcluded].join(' ');
          }

          return (
            <Card key={cycle.start_date} tone="surface" className={cardClass}>
              <Stack gap={2}>
                <div className={styles.cycleHeader}>
                  <span className={styles.cycleTitle}>{t.cycleItem.cycleNum(cycle.seq)}</span>
                  <span className={styles.dateRange}>
                    {t.cycleItem.dates(
                      formatDayMonthYear(cycle.start_date),
                      cycle.end_date ? formatDayMonthYear(cycle.end_date) : undefined,
                    )}
                  </span>
                </div>

                <div className={styles.statsRow}>
                  <span>{lengthDisplay}</span>
                  <span aria-hidden="true">{t.cycleItem.separator}</span>
                  <span>{t.cycleItem.periodLength(cycle.period_length_days)}</span>
                </div>

                <div className={styles.badgesRow}>
                  {isOngoing && <span>{t.cycleItem.ongoing}</span>}
                  {cycle.excluded && (
                    <>
                      <span className={styles.excludedBadge}>{t.cycleItem.excludedBadge}</span>
                      {cycle.exclusion_reason && (
                        <span className={styles.reasonBadge}>
                          {t.cycleItem.reasonTag(cycle.exclusion_reason)}
                        </span>
                      )}
                    </>
                  )}
                </div>

                <div className={styles.actionsRow}>
                  <Button
                    variant="ghost"
                    onClick={() => handleToggleExclude(cycle)}
                    disabled={setExclusion.isPending}
                  >
                    {cycle.excluded ? t.cycleItem.includeAction : t.cycleItem.excludeAction}
                  </Button>
                </div>
              </Stack>
            </Card>
          );
        })}
      </Stack>

      {/* Exclude confirmation dialog */}
      <Dialog
        open={Boolean(excludeTarget)}
        onClose={() => setExcludeTarget(null)}
        title={t.cycleItem.excludeTitle}
        description={t.cycleItem.excludeBody}
        actions={
          <>
            <Button variant="ghost" onClick={() => setExcludeTarget(null)}>
              {copy.common.cancel}
            </Button>
            <Button
              variant="danger"
              onClick={handleConfirmExclude}
              disabled={setExclusion.isPending}
            >
              {t.cycleItem.excludeAction}
            </Button>
          </>
        }
      >
        <Select
          name="reason"
          label={t.cycleItem.reasonLabel}
          value={selectedReason}
          onChange={(val) => setSelectedReason(val)}
          options={[
            { value: 'illness', label: t.cycleItem.reasons.illness },
            { value: 'travel', label: t.cycleItem.reasons.travel },
            { value: 'medication', label: t.cycleItem.reasons.medication },
            { value: 'stress', label: t.cycleItem.reasons.stress },
            { value: 'other', label: t.cycleItem.reasons.other },
          ]}
        />
      </Dialog>
    </Stack>
  );
}
