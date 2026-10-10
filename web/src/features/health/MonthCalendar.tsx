import { useMemo, useRef, type TouchEvent } from 'react';

import { copy } from '../../copy/en-GB';
import type { CalendarDay } from '../../lib/api';
import { formatDayAriaLabel, formatMonthHeader, getMonthGrid } from '../../lib/dates';
import { Icon } from '../../ui/icons';
import styles from './MonthCalendar.module.css';

export interface MonthCalendarProps {
  month: string; // YYYY-MM
  days?: CalendarDay[] | undefined;
  selectedDate?: string | undefined;
  todayDate?: string | undefined;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onSelectDate: (date: string) => void;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DATA_TRUE = 'true';
const DATA_FALSE = 'false';

/**
 * Spec 4.8, CSC-3:
 * Month calendar with period days, predicted days (dashed), fertile window (tint),
 * logged check-in dots, and swipe between months.
 */
export function MonthCalendar({
  month,
  days = [],
  selectedDate,
  todayDate,
  onPrevMonth,
  onNextMonth,
  onSelectDate,
}: MonthCalendarProps) {
  const headerTitle = formatMonthHeader(month);
  const touchStartX = useRef<number | null>(null);

  const handleTouchStart = (e: TouchEvent) => {
    touchStartX.current = e.touches[0]?.clientX ?? null;
  };

  const handleTouchEnd = (e: TouchEvent) => {
    if (touchStartX.current === null) return;
    const endX = e.changedTouches[0]?.clientX ?? touchStartX.current;
    const diff = endX - touchStartX.current;
    if (diff > 50) {
      onPrevMonth();
    } else if (diff < -50) {
      onNextMonth();
    }
    touchStartX.current = null;
  };

  const dayMap = useMemo(() => {
    const map = new Map<string, CalendarDay>();
    for (const d of days) {
      map.set(d.date, d);
    }
    return map;
  }, [days]);

  const { daysInMonth, startWeekday } = useMemo(() => getMonthGrid(month), [month]);

  const calendarGrid = useMemo(() => {
    const cells: (number | null)[] = [];
    for (let i = 0; i < startWeekday; i++) {
      cells.push(null);
    }
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push(d);
    }
    return cells;
  }, [startWeekday, daysInMonth]);

  return (
    <section
      className={styles.calendar}
      aria-label={copy.health.calendar.title}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div className={styles.header}>
        <button
          type="button"
          className={styles.navButton}
          onClick={onPrevMonth}
          aria-label={copy.health.calendar.prevMonth}
        >
          <Icon name="chevronLeft" size="sm" />
        </button>
        <h2>{headerTitle}</h2>
        <button
          type="button"
          className={styles.navButton}
          onClick={onNextMonth}
          aria-label={copy.health.calendar.nextMonth}
        >
          <Icon name="chevronRight" size="sm" />
        </button>
      </div>

      <div className={styles.grid}>
        {WEEKDAYS.map((wd) => (
          <div key={wd} className={styles.weekday} aria-hidden="true">
            {wd}
          </div>
        ))}

        {calendarGrid.map((dayNum, idx) => {
          if (dayNum === null) {
            return (
              <div key={`empty-${String(idx)}`} className={styles.emptyCell} aria-hidden="true" />
            );
          }

          const dateStr = `${month}-${String(dayNum).padStart(2, '0')}`;
          const dayData = dayMap.get(dateStr);
          const hasFlow = dayData?.flow && dayData.flow !== 'none' && dayData.flow !== null;
          const isPeriod =
            hasFlow ||
            dayData?.flow === 'medium' ||
            dayData?.flow === 'heavy' ||
            dayData?.flow === 'light' ||
            dayData?.flow === 'spotting';
          const isPredicted = Boolean(dayData?.predicted);
          const isFertile = Boolean(dayData?.fertile);
          const hasLog = Boolean(dayData?.has_log);
          const isToday = todayDate === dateStr;
          const isSelected = selectedDate === dateStr;

          const descriptions: string[] = [];
          if (dayData?.flow && dayData.flow !== 'none') descriptions.push(`${dayData.flow} flow`);
          if (isFertile) descriptions.push('fertile window');
          if (isPredicted) descriptions.push('predicted period');
          if (hasLog) descriptions.push('logged check-in');
          if (isToday) descriptions.push('today');

          const ariaLabel = formatDayAriaLabel(dateStr, descriptions);

          return (
            <button
              key={dateStr}
              type="button"
              className={styles.dayButton}
              onClick={() => onSelectDate(dateStr)}
              aria-label={ariaLabel}
              data-date={dateStr}
              data-today={isToday ? DATA_TRUE : DATA_FALSE}
              data-period={isPeriod ? DATA_TRUE : DATA_FALSE}
              data-predicted={isPredicted ? DATA_TRUE : DATA_FALSE}
              data-fertile={isFertile ? DATA_TRUE : DATA_FALSE}
              data-selected={isSelected ? DATA_TRUE : DATA_FALSE}
            >
              <span>{dayNum}</span>
              {isPeriod && <span className={styles.periodBadge} aria-hidden="true" />}
              {hasLog && <span className={styles.logDot} aria-hidden="true" />}
            </button>
          );
        })}
      </div>

      <div className={styles.legend} aria-label={copy.health.calendar.legend.title}>
        <div className={styles.legendItem}>
          <span className={styles.legendDotPeriod} aria-hidden="true" />
          <span>{copy.health.calendar.legend.period}</span>
        </div>
        <div className={styles.legendItem}>
          <span className={styles.legendDotPredicted} aria-hidden="true" />
          <span>{copy.health.calendar.legend.predicted}</span>
        </div>
        <div className={styles.legendItem}>
          <span className={styles.legendDotFertile} aria-hidden="true" />
          <span>{copy.health.calendar.legend.fertile}</span>
        </div>
        <div className={styles.legendItem}>
          <span className={styles.legendDotLog} aria-hidden="true" />
          <span>{copy.health.calendar.legend.logged}</span>
        </div>
      </div>
    </section>
  );
}
