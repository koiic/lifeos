import { Link } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import { useConfirmPeriodStart, useCycleState, type CycleStateResponse } from '../../lib/api';
import {
  differenceInCalendarDays,
  formatDayMonthYear,
  formatIsoDate,
  nowIso,
} from '../../lib/dates';
import { useMe } from '../../lib/me/me';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { CycleRing } from '../../ui/CycleRing';
import { ErrorState } from '../../ui/ErrorState';
import { Icon } from '../../ui/icons';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import styles from './HealthScreen.module.css';
import { PeriodControls } from './PeriodControls';
import { PredictionCard } from './PredictionCard';

const t = copy.health;

function deriveStateMessage(data: CycleStateResponse, todayIso: string): string {
  const state = data.state;
  const cycleDay = data.cycle_day;
  const pred = data.prediction;

  switch (state) {
    case 'on_period':
      return t.cycle.states.on_period(cycleDay ?? undefined);
    case 'upcoming': {
      let days = 1;
      if (pred?.predicted_start) {
        days = Math.max(1, differenceInCalendarDays(todayIso, pred.predicted_start));
      }
      return t.cycle.states.upcoming(days);
    }
    case 'window':
      return t.cycle.states.window;
    case 'late': {
      let days = 1;
      if (pred?.range_high) {
        days = Math.max(1, differenceInCalendarDays(pred.range_high, todayIso));
      }
      return t.cycle.states.late(days);
    }
    case 'long_gap':
      return t.cycle.states.long_gap;
    case 'irregular':
      return t.cycle.states.irregular;
    case 'waiting':
      return t.cycle.states.waiting;
    case 'no_data':
    default:
      return t.cycle.states.no_data;
  }
}

/**
 * Spec 5.2, CSC-1, CSC-2, 8.4:
 * The Cycle Screen: CycleRing, PeriodControls, 8.4 derived state, intra-cycle prompt,
 * prediction card, and navigation to calendar and history.
 */
export function HealthScreen() {
  const me = useMe();
  const timezone = me.data?.profile.timezone;
  const todayIso = formatIsoDate(nowIso(), timezone);

  const cycleQuery = useCycleState();
  const confirmPrompt = useConfirmPeriodStart();

  if (cycleQuery.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Stack gap={2}>
          <h1>{t.title}</h1>
          <nav className={styles.navTabs} aria-label={t.navLabel}>
            <Link to="/health/cycle" className={`${styles.tabLink} ${styles.activeTab}`}>
              {t.cycleTab}
            </Link>
            <Link to="/health/calendar" className={styles.tabLink}>
              {t.calendarTab}
            </Link>
            <Link to="/health/history" className={styles.tabLink}>
              {t.historyTab}
            </Link>
          </nav>
        </Stack>
        <Skeleton label={copy.common.loading} shapes={['line', 'block', 'block']} />
      </Stack>
    );
  }

  if (cycleQuery.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Stack gap={2}>
          <h1>{t.title}</h1>
          <nav className={styles.navTabs} aria-label={t.navLabel}>
            <Link to="/health/cycle" className={`${styles.tabLink} ${styles.activeTab}`}>
              {t.cycleTab}
            </Link>
            <Link to="/health/calendar" className={styles.tabLink}>
              {t.calendarTab}
            </Link>
            <Link to="/health/history" className={styles.tabLink}>
              {t.historyTab}
            </Link>
          </nav>
        </Stack>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void cycleQuery.refetch() }}
        />
      </Stack>
    );
  }

  const data = cycleQuery.data;
  const pred = data.prediction;
  const latestStart = data.latest_start;

  // CycleRing arcs
  const cycleLength = pred?.mean_len ? Math.round(pred.mean_len) : 28;
  const periodDays = pred?.mean_period_len ? Math.round(pred.mean_period_len) : 5;

  let fertileStart: number | undefined;
  let fertileEnd: number | undefined;
  if (latestStart && pred?.fertile_start && pred?.fertile_end) {
    fertileStart = Math.max(1, differenceInCalendarDays(latestStart, pred.fertile_start) + 1);
    fertileEnd = Math.max(
      fertileStart,
      differenceInCalendarDays(latestStart, pred.fertile_end) + 1,
    );
  }

  const isPeriodOngoing = data.state === 'on_period';
  const stateMessage = deriveStateMessage(data, todayIso);
  const prompt =
    data.pending_prompt && data.pending_prompt.kind === 'new_period' ? data.pending_prompt : null;

  return (
    <Stack as="main" inset="page" gap={5}>
      {/* Top Header & Navigation Tabs */}
      <Stack gap={2}>
        <h1>{t.title}</h1>
        <nav className={styles.navTabs} aria-label={t.navLabel}>
          <Link to="/health/cycle" className={`${styles.tabLink} ${styles.activeTab}`}>
            {t.cycleTab}
          </Link>
          <Link to="/health/calendar" className={styles.tabLink}>
            {t.calendarTab}
          </Link>
          <Link to="/health/history" className={styles.tabLink}>
            {t.historyTab}
          </Link>
        </nav>
      </Stack>

      {/* Period Controls (started/ended) */}
      <PeriodControls
        isOngoing={isPeriodOngoing}
        currentDate={todayIso}
        ongoingStartDate={isPeriodOngoing ? (latestStart ?? todayIso) : undefined}
      />

      {/* Pending prompt (e.g. intra-cycle bleed new period confirmation, spec 8.1, 9.2) */}
      {prompt && (
        <Card tone="accent" className={styles.promptCard}>
          <Stack gap={2}>
            <h3>{t.cycle.pendingPrompt.title}</h3>
            <p>{t.cycle.pendingPrompt.body(formatDayMonthYear(prompt.date))}</p>
            <div className={styles.promptActions}>
              <Button
                variant="primary"
                onClick={() =>
                  confirmPrompt.mutate({
                    date: prompt.date,
                    is_new_period: true,
                  })
                }
                disabled={confirmPrompt.isPending}
              >
                {t.cycle.pendingPrompt.confirmYes}
              </Button>
              <Button
                variant="ghost"
                onClick={() =>
                  confirmPrompt.mutate({
                    date: prompt.date,
                    is_new_period: false,
                  })
                }
                disabled={confirmPrompt.isPending}
              >
                {t.cycle.pendingPrompt.confirmNo}
              </Button>
            </div>
          </Stack>
        </Card>
      )}

      {/* Derived UI State Banner (spec 8.4) */}
      <Card tone="surface" className={styles.stateCard}>
        <p className={styles.stateMessage}>{stateMessage}</p>
      </Card>

      {/* CycleRing & Legend (CSC-1) */}
      <div className={styles.ringContainer}>
        <CycleRing
          cycleLength={cycleLength}
          periodDays={periodDays}
          fertileStart={fertileStart}
          fertileEnd={fertileEnd}
          today={data.cycle_day}
          phase={data.phase}
          state={data.state}
        />
        <div className={styles.legendRow} aria-hidden="true">
          <div className={styles.legendItem}>
            <span className={styles.dotPeriod} />
            <span>{t.cycle.legend.period}</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.dotFertile} />
            <span>{t.cycle.legend.fertile}</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.dotToday} />
            <span>{t.cycle.legend.today}</span>
          </div>
        </div>
      </div>

      {/* Prediction Card (CSC-2, CYC-3, CYC-4, CYC-6) */}
      <PredictionCard prediction={data.prediction} state={data.state} notes={data.notes} />

      {/* Quick Navigation Links */}
      <div className={styles.linksSection}>
        <Link to={`/checkin?date=${todayIso}`} className={styles.navButton}>
          <span>{t.cycle.checkInLink}</span>
          <Icon name="chevronRight" />
        </Link>
        <Link to="/health/calendar" className={styles.navButton}>
          <span>{t.cycle.calendarLink}</span>
          <Icon name="chevronRight" />
        </Link>
        <Link to="/health/history" className={styles.navButton}>
          <span>{t.cycle.historyLink}</span>
          <Icon name="chevronRight" />
        </Link>
      </div>
    </Stack>
  );
}
