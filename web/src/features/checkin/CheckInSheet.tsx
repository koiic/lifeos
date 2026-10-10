import { useEffect, useRef, useState } from 'react';

import { copy } from '../../copy/en-GB';
import { type DailyLog, useDailyLog, useSaveDailyLog } from '../../lib/api';
import { nowIso } from '../../lib/dates';
import { type Settings, useMe } from '../../lib/me/me';
import { Button } from '../../ui/Button';
import { Sheet } from '../../ui/Sheet';
import { Skeleton } from '../../ui/Skeleton';
import { TextArea } from '../../ui/TextArea';
import styles from './CheckInSheet.module.css';
import { EnergySlider } from './EnergySlider';
import { FlowPicker, type FlowLevel } from './FlowPicker';
import { MoodPicker } from './MoodPicker';
import { OptionalFieldsSection, type IntimacyValue } from './OptionalFieldsSection';
import { SleepStepper } from './SleepStepper';
import { SymptomPicker } from './SymptomPicker';

export interface CheckInSheetProps {
  open: boolean;
  date: string;
  initialMood?: number | undefined;
  onClose: () => void;
  onSaved?: () => void;
}

const MAX_NOTE_LENGTH = 2000;

interface CheckInFormProps {
  date: string;
  initialLog: DailyLog | null;
  initialMood?: number | undefined;
  settings?: Settings | undefined;
  onClose: () => void;
  onSaved?: (() => void) | undefined;
}

function CheckInForm({
  date,
  initialLog,
  initialMood,
  settings,
  onClose,
  onSaved,
}: CheckInFormProps) {
  const saveDailyLog = useSaveDailyLog();

  const [mood, setMood] = useState<number | null>(initialLog?.mood ?? initialMood ?? null);
  const [energy, setEnergy] = useState<number | null>(initialLog?.energy ?? null);
  const [sleep, setSleep] = useState<number | null>(initialLog?.sleep_hours ?? null);
  const [flow, setFlow] = useState<FlowLevel>(initialLog?.flow ?? 'none');
  const [symptomIds, setSymptomIds] = useState<string[]>(initialLog?.symptom_ids ?? []);
  const [note, setNote] = useState<string>(initialLog?.note ?? '');
  const [bbt, setBbt] = useState<number | null>(initialLog?.bbt_c ?? null);
  const [discharge, setDischarge] = useState<string | null>(initialLog?.discharge ?? null);
  const [intimacy, setIntimacy] = useState<IntimacyValue | null>(
    initialLog?.intimacy
      ? { logged: initialLog.intimacy.logged, protected: initialLog.intimacy.protected ?? null }
      : null,
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    startTimeRef.current = performance.now();
  }, []);

  const handleNoteChange = (val: string) => {
    if (val.length <= MAX_NOTE_LENGTH) {
      setNote(val);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    const checkinMs =
      startTimeRef.current !== null ? Math.round(performance.now() - startTimeRef.current) : 0;

    const trimmedNote = note.trim();

    try {
      await saveDailyLog.mutateAsync({
        date,
        data: {
          client_updated_at: nowIso(),
          checkin_ms: checkinMs,
          mood,
          energy,
          sleep_hours: sleep,
          flow,
          symptom_ids: symptomIds,
          note: trimmedNote.length > 0 ? trimmedNote : null,
          bbt_c: bbt,
          discharge,
          intimacy,
        },
      });
      onSaved?.();
      onClose();
    } catch {
      setSaveError(copy.common.networkError);
    }
  };

  const remainingChars = MAX_NOTE_LENGTH - note.length;

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      {saveError && (
        <p role="alert" className={styles.error}>
          {saveError}
        </p>
      )}

      <MoodPicker value={mood} onChange={setMood} disabled={saveDailyLog.isPending} />

      <EnergySlider value={energy} onChange={setEnergy} disabled={saveDailyLog.isPending} />

      <SleepStepper value={sleep} onChange={setSleep} disabled={saveDailyLog.isPending} />

      <FlowPicker value={flow} onChange={setFlow} disabled={saveDailyLog.isPending} />

      <SymptomPicker
        selectedIds={symptomIds}
        onChange={setSymptomIds}
        disabled={saveDailyLog.isPending}
      />

      <OptionalFieldsSection
        settings={settings}
        bbt={bbt}
        onBbtChange={setBbt}
        discharge={discharge}
        onDischargeChange={setDischarge}
        intimacy={intimacy}
        onIntimacyChange={setIntimacy}
        disabled={saveDailyLog.isPending}
      />

      <div className={styles.noteField}>
        <TextArea
          name="note"
          label={copy.checkin.note.label}
          value={note}
          onChange={handleNoteChange}
          hint={copy.checkin.note.charsRemaining(remainingChars)}
        />
      </div>

      <div className={styles.actions}>
        <Button type="submit" variant="primary" busy={saveDailyLog.isPending}>
          {copy.checkin.save}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose} disabled={saveDailyLog.isPending}>
          {copy.checkin.close}
        </Button>
      </div>
    </form>
  );
}

/**
 * Spec 4.4, 5.2, CHK-1, CHK-3, CHK-4, PER-2:
 * Check-in bottom sheet with mood, energy, sleep, flow, symptoms, note, optional fields.
 */
export function CheckInSheet({ open, date, initialMood, onClose, onSaved }: CheckInSheetProps) {
  const me = useMe();
  const dailyLogQuery = useDailyLog(date);

  const formKey = `${date}-${dailyLogQuery.data ? 1 : 0}-${initialMood ?? 0}`;

  return (
    <Sheet open={open} title={copy.checkin.title} closeLabel={copy.checkin.close} onClose={onClose}>
      {dailyLogQuery.isPending && dailyLogQuery.fetchStatus === 'fetching' ? (
        <Skeleton label={copy.common.loading} shapes={['line', 'block']} />
      ) : (
        <CheckInForm
          key={formKey}
          date={date}
          initialLog={dailyLogQuery.data ?? null}
          initialMood={initialMood}
          settings={me.data?.settings}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </Sheet>
  );
}
