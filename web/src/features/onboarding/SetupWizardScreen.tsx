import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { copy } from '../../copy/en-GB';
import {
  useHealthProfile,
  useUpdateHealthProfile,
  type HealthProfileResponse,
} from '../../lib/api';
import { useChangeSettings, useGiveConsent, useMe, type Me } from '../../lib/me/me';
import { Button } from '../../ui/Button';
import { DateTimePicker } from '../../ui/DateTimePicker';
import { ErrorState } from '../../ui/ErrorState';
import { Skeleton } from '../../ui/Skeleton';
import { Stack } from '../../ui/Stack';
import { Switch } from '../../ui/Switch';
import { TextField } from '../../ui/TextField';
import styles from './SetupWizardScreen.module.css';

type ModeKey = 'standard' | 'postpartum' | 'ttc' | 'avoid';

const t = copy.setup;
const tModes = copy.healthMode.modes;

const MODES: ModeKey[] = ['standard', 'postpartum', 'ttc', 'avoid'];

interface SetupWizardFormProps {
  initialProfile: HealthProfileResponse;
  initialMe: Me;
}

function SetupWizardForm({ initialProfile, initialMe }: SetupWizardFormProps) {
  const { step } = useParams<{ step?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const currentStep = Math.min(Math.max(Number(step) || 1, 1), 4);
  const returnToSettings = searchParams.get('return') === 'settings';
  const querySuffix = returnToSettings ? '?return=settings' : '';

  const updateProfileMutation = useUpdateHealthProfile();
  const changeSettingsMutation = useChangeSettings();
  const giveConsentMutation = useGiveConsent();

  // Wizard form state initialized directly from server data
  const [mode, setMode] = useState<ModeKey>((initialProfile.mode as ModeKey) || 'standard');
  const [lastPeriodDate, setLastPeriodDate] = useState<string>(
    initialProfile.last_period_hint || '',
  );
  const [notYetPostpartum, setNotYetPostpartum] = useState<boolean>(false);
  const [cycleLength, setCycleLength] = useState<string>(
    initialProfile.usual_cycle_length ? String(initialProfile.usual_cycle_length) : '28',
  );
  const [periodLength, setPeriodLength] = useState<string>(
    initialProfile.usual_period_length ? String(initialProfile.usual_period_length) : '5',
  );
  const [checkinTime, setCheckinTime] = useState<string>(
    initialMe.settings.checkin_time || '21:00',
  );
  const [periodDueAlert, setPeriodDueAlert] = useState<boolean>(
    initialMe.settings.notif_prefs ? Boolean(initialMe.settings.notif_prefs.period_due) : true,
  );

  const navigateToStep = (targetStep: number) => {
    navigate(`/setup/${String(targetStep)}${querySuffix}`);
  };

  const finishWizard = () => {
    void giveConsentMutation.mutate({ version: '1' });
    if (returnToSettings) {
      navigate('/settings');
    } else {
      navigate('/setup/notifications');
    }
  };

  const handleNext = async () => {
    if (currentStep === 1) {
      await updateProfileMutation.mutateAsync({ mode });
      navigateToStep(2);
    } else if (currentStep === 2) {
      if (notYetPostpartum) {
        await updateProfileMutation.mutateAsync({ last_period_hint: null });
      } else if (lastPeriodDate) {
        await updateProfileMutation.mutateAsync({ last_period_hint: lastPeriodDate });
      }
      navigateToStep(3);
    } else if (currentStep === 3) {
      const cLen = parseInt(cycleLength, 10);
      const pLen = parseInt(periodLength, 10);
      await updateProfileMutation.mutateAsync({
        usual_cycle_length: !isNaN(cLen) && cLen > 0 ? cLen : 28,
        usual_period_length: !isNaN(pLen) && pLen > 0 ? pLen : 5,
      });
      navigateToStep(4);
    } else if (currentStep === 4) {
      await changeSettingsMutation.mutateAsync({
        checkin_time: checkinTime,
        notif_prefs: { period_due: periodDueAlert },
      });
      finishWizard();
    }
  };

  const handleSkip = () => {
    if (currentStep < 4) {
      navigateToStep(currentStep + 1);
    } else {
      finishWizard();
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      navigateToStep(currentStep - 1);
    }
  };

  return (
    <Stack as="main" inset="page" gap={5}>
      <div className={styles.container}>
        <header className={styles.progressContainer}>
          <span className={styles.stepIndicator}>{t.stepCount(currentStep, 4)}</span>
          <div
            className={styles.progressBar}
            role="progressbar"
            aria-valuenow={currentStep}
            aria-valuemin={1}
            aria-valuemax={4}
            aria-label={t.stepCount(currentStep, 4)}
          >
            <div className={styles.progressFill} data-step={currentStep} />
          </div>
        </header>

        {currentStep === 1 && (
          <Stack gap={4}>
            <Stack gap={1}>
              <h1>{t.step1.title}</h1>
              <p className={styles.stepDescription}>{t.step1.description}</p>
            </Stack>

            <fieldset className={styles.modeList}>
              <legend className="visually-hidden">{t.step1.title}</legend>
              {MODES.map((modeKey) => {
                const info = tModes[modeKey];
                const isSelected = mode === modeKey;
                const inputId = `setup-mode-${modeKey}`;

                return (
                  <label
                    key={modeKey}
                    htmlFor={inputId}
                    className={styles.modeCard}
                    data-selected={isSelected}
                  >
                    <input
                      type="radio"
                      id={inputId}
                      name="setup_mode"
                      value={modeKey}
                      checked={isSelected}
                      onChange={() => setMode(modeKey)}
                      className={styles.radioInput}
                    />
                    <span className={styles.modeLabel}>{info.label}</span>
                    <span className={styles.modeDesc}>{info.description}</span>
                  </label>
                );
              })}
            </fieldset>
          </Stack>
        )}

        {currentStep === 2 && (
          <Stack gap={4}>
            <Stack gap={1}>
              <h1>{t.step2.title}</h1>
              <p className={styles.stepDescription}>{t.step2.description}</p>
            </Stack>

            <DateTimePicker
              name="last_period_hint"
              kind="date"
              label={t.step2.dateLabel}
              value={lastPeriodDate}
              onChange={(val) => {
                setLastPeriodDate(val);
                if (val) setNotYetPostpartum(false);
              }}
            />

            {mode === 'postpartum' && (
              <label className={styles.checkboxRow}>
                <input
                  type="checkbox"
                  checked={notYetPostpartum}
                  onChange={(e) => {
                    setNotYetPostpartum(e.target.checked);
                    if (e.target.checked) setLastPeriodDate('');
                  }}
                />
                <span>{t.step2.notYetPostpartum}</span>
              </label>
            )}
          </Stack>
        )}

        {currentStep === 3 && (
          <Stack gap={4}>
            <Stack gap={1}>
              <h1>{t.step3.title}</h1>
              <p className={styles.stepDescription}>{t.step3.description}</p>
            </Stack>

            <TextField
              name="cycle_length"
              type="number"
              inputMode="numeric"
              label={t.step3.cycleLengthLabel}
              hint={t.step3.cycleLengthHint}
              value={cycleLength}
              onChange={setCycleLength}
            />

            <TextField
              name="period_length"
              type="number"
              inputMode="numeric"
              label={t.step3.periodLengthLabel}
              hint={t.step3.periodLengthHint}
              value={periodLength}
              onChange={setPeriodLength}
            />

            <div>
              <Button
                variant="secondary"
                onClick={() => {
                  setCycleLength('28');
                  setPeriodLength('5');
                }}
              >
                {t.step3.useDefaults}
              </Button>
            </div>
          </Stack>
        )}

        {currentStep === 4 && (
          <Stack gap={4}>
            <Stack gap={1}>
              <h1>{t.step4.title}</h1>
              <p className={styles.stepDescription}>{t.step4.description}</p>
            </Stack>

            <DateTimePicker
              name="checkin_time"
              kind="time"
              label={t.step4.checkinTimeLabel}
              value={checkinTime}
              onChange={setCheckinTime}
            />

            <Switch
              label={t.step4.periodDueLabel}
              description={t.step4.periodDueHint}
              checked={periodDueAlert}
              onChange={setPeriodDueAlert}
            />
          </Stack>
        )}

        <footer className={styles.actions}>
          <div>
            {currentStep > 1 && (
              <Button variant="secondary" onClick={handleBack}>
                {t.back}
              </Button>
            )}
          </div>

          <div className={styles.rightActions}>
            <Button variant="secondary" onClick={handleSkip}>
              {t.skip}
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleNext()}
              disabled={updateProfileMutation.isPending || changeSettingsMutation.isPending}
            >
              {currentStep === 4 ? t.finish : t.next}
            </Button>
          </div>
        </footer>
      </div>
    </Stack>
  );
}

/**
 * Setup wizard multi-step screen (`/setup/:step`, spec 3 J1 step 4, ONB-2, MOD-1, MOD-2).
 * 4 steps: Mode, Last period, Typical lengths, Reminder preferences.
 * Each step is skippable and values are saved progressively.
 */
export function SetupWizardScreen() {
  const healthProfileQuery = useHealthProfile();
  const meQuery = useMe();

  if (healthProfileQuery.isPending || meQuery.isPending) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <Skeleton label={copy.common.loading} shapes={['line', 'line']} />
      </Stack>
    );
  }

  if (healthProfileQuery.isError || meQuery.isError) {
    return (
      <Stack as="main" inset="page" gap={5}>
        <ErrorState
          title={copy.errors.title}
          body={copy.common.networkError}
          retry={{
            label: copy.common.retry,
            onClick: () => {
              void healthProfileQuery.refetch();
              void meQuery.refetch();
            },
          }}
        />
      </Stack>
    );
  }

  return <SetupWizardForm initialProfile={healthProfileQuery.data} initialMe={meQuery.data} />;
}
