import { copy } from '../../copy/en-GB';
import type { CycleNote, CyclePredictionResponse } from '../../lib/api';
import { formatDayMonth } from '../../lib/dates';
import { Card } from '../../ui/Card';
import { Chip } from '../../ui/Chip';
import { Stack } from '../../ui/Stack';
import styles from './PredictionCard.module.css';

export interface PredictionCardProps {
  prediction?: CyclePredictionResponse | null | undefined;
  state?: string | null | undefined;
  notes?: CycleNote[] | undefined;
}

const t = copy.health.cycle;

/**
 * Spec 5.2, CSC-2, CYC-3, CYC-4, CYC-6:
 * Prediction card showing next period range, confidence badge, cycle history count,
 * fertile window with mandatory disclaimer, and irregularity / NHS guidance notes.
 */
export function PredictionCard({ prediction, state, notes }: PredictionCardProps) {
  const isSuppressed = Boolean(
    prediction?.suppressed_reason ||
    state === 'waiting' ||
    state === 'no_data' ||
    prediction?.confidence === 'none',
  );

  const rangeLow = prediction?.range_low;
  const rangeHigh = prediction?.range_high;
  const predictedStart = prediction?.predicted_start;

  let rangeDisplay: string;
  if (isSuppressed || (!rangeLow && !predictedStart)) {
    if (prediction?.suppressed_reason === 'postpartum_waiting' || state === 'waiting') {
      rangeDisplay = t.states.waiting;
    } else {
      rangeDisplay = t.states.no_data;
    }
  } else if (rangeLow && rangeHigh && rangeLow !== rangeHigh) {
    rangeDisplay = t.prediction.nextRange(formatDayMonth(rangeLow), formatDayMonth(rangeHigh));
  } else if (rangeLow) {
    rangeDisplay = formatDayMonth(rangeLow);
  } else if (predictedStart) {
    rangeDisplay = formatDayMonth(predictedStart);
  } else {
    rangeDisplay = t.states.no_data;
  }

  const confidence = prediction?.confidence;
  const showConfidence = !isSuppressed && confidence && confidence !== 'none';
  const confidenceLabel = showConfidence
    ? confidence === 'high'
      ? t.prediction.confidence.high
      : confidence === 'medium'
        ? t.prediction.confidence.medium
        : t.prediction.confidence.low
    : null;

  const nCycles = prediction?.n_cycles ?? 0;
  const basedOnText = nCycles > 0 ? t.prediction.basedOnCycles(nCycles) : t.prediction.basedOnHint;

  // Fertile window (CYC-3)
  const fertileStart = prediction?.fertile_start;
  const fertileEnd = prediction?.fertile_end;
  const ovulationEst = prediction?.ovulation_est;
  const hasFertileWindow = !isSuppressed && Boolean(fertileStart && fertileEnd);

  // Irregular note & long gap NHS link (CYC-6, spec 8.4)
  const isIrregular = state === 'irregular' || notes?.some((n) => n.kind === 'irregular_cycles');
  const isLongGap = state === 'long_gap' || notes?.some((n) => n.kind === 'data_gap');

  return (
    <Card tone="surface">
      <Stack gap={3}>
        <div className={styles.header}>
          <span className={styles.title}>{t.prediction.title}</span>
          {showConfidence && confidenceLabel && (
            <Chip pressed={false} onChange={() => undefined}>
              {confidenceLabel}
            </Chip>
          )}
        </div>

        <div className={styles.rangeText}>{rangeDisplay}</div>

        {showConfidence && (
          <div className={styles.metaRow}>
            <span className={styles.basedOn}>{basedOnText}</span>
            {confidence === 'low' && (
              <span className={styles.lowHelper}>{t.prediction.confidence.lowHelper}</span>
            )}
          </div>
        )}

        {/* Fertile window with mandatory disclaimer (CYC-3) */}
        {hasFertileWindow && fertileStart && fertileEnd && (
          <div className={styles.fertileSection}>
            <span className={styles.fertileTitle}>
              {t.prediction.fertileWindow(formatDayMonth(fertileStart), formatDayMonth(fertileEnd))}
            </span>
            {ovulationEst && (
              <span className={styles.ovulationText}>
                {t.prediction.ovulationEst(formatDayMonth(ovulationEst))}
              </span>
            )}
            <span className={styles.disclaimer}>{t.prediction.disclaimer}</span>
          </div>
        )}

        {/* Irregular note (CYC-6) */}
        {isIrregular && (
          <div className={styles.noteSection}>
            <p>{t.states.irregular}</p>
          </div>
        )}

        {/* Long gap note with NHS guidance link (CYC-6, spec 8.4) */}
        {isLongGap && (
          <div className={styles.noteSection}>
            <p>{t.states.long_gap}</p>
            <a
              href={t.states.nhsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.nhsLink}
            >
              {t.states.nhsGuidance}
            </a>
          </div>
        )}
      </Stack>
    </Card>
  );
}
