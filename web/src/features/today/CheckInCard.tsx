import { useId } from 'react';

import { copy } from '../../copy/en-GB';
import type { CheckinState } from '../../lib/api';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import styles from './CheckInCard.module.css';

const t = copy.today.checkinCard;
const tm = copy.checkin.mood;
const tf = copy.checkin.flow;
const CHECKMARK = '✓';

export interface CheckInCardProps {
  checkin: CheckinState;
  onSelectMood: (mood: number) => void;
  onOpenCheckIn: () => void;
}

interface MoodItem {
  value: number;
  label: string;
  emoji: string;
}

const MOODS: readonly MoodItem[] = [
  { value: 5, label: tm.bright, emoji: '☀️' },
  { value: 4, label: tm.good, emoji: '😊' },
  { value: 3, label: tm.okay, emoji: '😐' },
  { value: 2, label: tm.tired, emoji: '🥱' },
  { value: 1, label: tm.low, emoji: '🌧️' },
] as const;

function moodFor(value: number | null | undefined): MoodItem | undefined {
  return MOODS.find((m) => m.value === value);
}

function flowText(flow: string | null | undefined): string | null {
  if (!flow || flow === 'none') return null;
  switch (flow) {
    case 'spotting':
      return tf.spotting;
    case 'light':
      return tf.light;
    case 'medium':
      return tf.medium;
    case 'heavy':
      return tf.heavy;
    default:
      return flow;
  }
}

/**
 * Spec 4.3 TOD-3: "Shows mood buttons if not done today; completed state with summary and edit link if done".
 * Spec 5.6: "Saving a check-in drops a Sticker Book 'sticker' on the card".
 */
export function CheckInCard({ checkin, onSelectMood, onOpenCheckIn }: CheckInCardProps) {
  const headingId = useId();

  if (checkin.done && checkin.log) {
    const { log } = checkin;
    const moodItem = moodFor(log.mood);
    const flowName = flowText(log.flow);

    return (
      <Card as="section" labelledBy={headingId} sticker={true}>
        <div className={styles.cardContent}>
          <div className={styles.header}>
            <h2 id={headingId} className={styles.title}>
              {t.doneTitle}
            </h2>
            <span className={styles.stickerDrop} data-testid="completed-sticker">
              <span aria-hidden="true">{CHECKMARK}</span>
              <span>{t.completedSticker}</span>
            </span>
          </div>

          <div className={styles.summaryList}>
            {moodItem && (
              <span className={styles.summaryChip} data-testid="summary-mood">
                <span aria-hidden="true">{moodItem.emoji}</span>
                <span>{moodItem.label}</span>
              </span>
            )}
            {log.energy !== null && log.energy !== undefined && (
              <span className={styles.summaryChip} data-testid="summary-energy">
                {t.energyLabel(log.energy)}
              </span>
            )}
            {log.sleep_hours !== null && log.sleep_hours !== undefined && (
              <span className={styles.summaryChip} data-testid="summary-sleep">
                {t.sleepLabel(log.sleep_hours)}
              </span>
            )}
            {flowName && (
              <span className={styles.summaryChip} data-testid="summary-flow">
                {t.flowLabel(flowName)}
              </span>
            )}
            {Boolean(log.symptom_ids && log.symptom_ids.length > 0) && (
              <span className={styles.summaryChip} data-testid="summary-symptoms">
                {t.symptomsCount(log.symptom_ids?.length ?? 0)}
              </span>
            )}
          </div>

          <div className={styles.actions}>
            <Button variant="secondary" onClick={onOpenCheckIn}>
              {t.edit}
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card as="section" labelledBy={headingId}>
      <div className={styles.cardContent}>
        <h2 id={headingId} className={styles.title}>
          {t.title}
        </h2>
        <p className={styles.prompt}>{t.prompt}</p>

        <div role="group" aria-label={t.moodLabel} className={styles.moodGroup}>
          {MOODS.map((m) => (
            <button
              key={m.value}
              type="button"
              className={styles.moodButton}
              onClick={() => onSelectMood(m.value)}
              aria-label={m.label}
              data-testid={`mood-button-${m.value}`}
            >
              <span className={styles.moodEmoji} aria-hidden="true">
                {m.emoji}
              </span>
              <span className={styles.moodLabel}>{m.label}</span>
            </button>
          ))}
        </div>

        <div className={styles.actions}>
          <Button variant="primary" onClick={onOpenCheckIn}>
            {t.checkIn}
          </Button>
        </div>
      </div>
    </Card>
  );
}
