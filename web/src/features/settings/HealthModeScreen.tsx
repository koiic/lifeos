import { useState } from 'react';

import { copy } from '../../copy/en-GB';
import {
  useHealthProfile,
  useUpdateHealthProfile,
  type HealthProfileResponse,
} from '../../lib/api';
import { formatDayMonthYear } from '../../lib/dates';
import { Button } from '../../ui/Button';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import styles from './HealthModeScreen.module.css';

type ModeKey = 'standard' | 'postpartum' | 'ttc' | 'avoid';

const t = copy.healthMode;

const MODES: ModeKey[] = ['standard', 'postpartum', 'ttc', 'avoid'];

/**
 * Health mode settings screen (`/settings/mode`, SET-4, MOD-1, MOD-2).
 * Switches cycle tracking mode; changing mode records started_on.
 */
export function HealthModeScreen() {
  const profileQuery = useHealthProfile();
  const updateMutation = useUpdateHealthProfile();

  const [selectedMode, setSelectedMode] = useState<ModeKey | null>(null);
  const [savedFeedback, setSavedFeedback] = useState<string | null>(null);

  if (profileQuery.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'line']} />
      </Stack>
    );
  }

  if (profileQuery.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{ label: copy.common.retry, onClick: () => void profileQuery.refetch() }}
        />
      </Stack>
    );
  }

  const profile: HealthProfileResponse = profileQuery.data ?? { mode: 'standard' };
  const currentMode = (profile.mode as ModeKey) || 'standard';
  const activeMode = selectedMode ?? currentMode;
  const startedOnDate = profile.mode_started_on
    ? formatDayMonthYear(profile.mode_started_on)
    : null;

  const handleSave = () => {
    setSavedFeedback(null);
    updateMutation.mutate(
      { mode: activeMode },
      {
        onSuccess: () => {
          setSavedFeedback(t.saved);
        },
        onError: () => {
          setSavedFeedback(t.failed);
        },
      },
    );
  };

  return (
    <Stack as="main" inset="page" gap={5}>
      <Stack gap={2}>
        <h1>{t.title}</h1>
        <p className={styles.modeDescription}>{t.description}</p>
        {startedOnDate && currentMode === activeMode && (
          <p className={styles.startedOn}>{t.startedOn(startedOnDate)}</p>
        )}
      </Stack>

      <fieldset className={styles.modeList}>
        <legend className="visually-hidden">{t.title}</legend>
        {MODES.map((modeKey) => {
          const modeInfo = t.modes[modeKey];
          const isSelected = activeMode === modeKey;
          const inputId = `mode-${modeKey}`;

          return (
            <label
              key={modeKey}

              className={styles.modeCard}
              data-selected={isSelected}
            >
              <input
                type="radio"
                id={inputId}
                name="health_mode"
                value={modeKey}
                checked={isSelected}
                onChange={() => {
                  setSelectedMode(modeKey);
                  setSavedFeedback(null);
                }}
                className={styles.radioInput}
              />
              <span className={styles.modeLabel}>{modeInfo.label}</span>
              <span className={styles.modeDescription}>{modeInfo.description}</span>
            </label>
          );
        })}
      </fieldset>

      {activeMode === 'postpartum' && (
        <div className={styles.postpartumCallout} role="note">
          {t.postpartumNote}
        </div>
      )}

      {savedFeedback && (
        <div
          role="status"
          className={savedFeedback === t.saved ? styles.feedbackSuccess : styles.feedbackError}
        >
          {savedFeedback}
        </div>
      )}

      <div>
        <Button variant="primary" onClick={handleSave} disabled={updateMutation.isPending}>
          {t.save}
        </Button>
      </div>
    </Stack>
  );
}
