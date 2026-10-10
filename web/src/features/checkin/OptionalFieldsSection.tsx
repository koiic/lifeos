import { copy } from '../../copy/en-GB';
import type { Settings } from '../../lib/me/me';
import { Chip } from '../../ui/Chip';
import { Select, type SelectOption } from '../../ui/Select';
import { Switch } from '../../ui/Switch';
import { TextField } from '../../ui/TextField';
import styles from './OptionalFieldsSection.module.css';

const t = copy.checkin.optional;

export interface IntimacyValue {
  logged: boolean;
  protected?: boolean | null;
}

export interface OptionalFieldsSectionProps {
  settings?: Settings | undefined;
  bbt: number | null;
  onBbtChange: (val: number | null) => void;
  discharge: string | null;
  onDischargeChange: (val: string | null) => void;
  intimacy: IntimacyValue | null;
  onIntimacyChange: (val: IntimacyValue | null) => void;
  disabled?: boolean;
}

const DISCHARGE_OPTIONS: readonly SelectOption<string>[] = [
  { value: '', label: t.discharge.options.none },
  { value: 'dry', label: t.discharge.options.dry },
  { value: 'sticky', label: t.discharge.options.sticky },
  { value: 'creamy', label: t.discharge.options.creamy },
  { value: 'eggwhite', label: t.discharge.options.eggwhite },
  { value: 'watery', label: t.discharge.options.watery },
] as const;

/** Optional tracking fields (CHK-4) hidden by default unless enabled in Settings. */
export function OptionalFieldsSection({
  settings,
  bbt,
  onBbtChange,
  discharge,
  onDischargeChange,
  intimacy,
  onIntimacyChange,
  disabled,
}: OptionalFieldsSectionProps) {
  const flags = settings?.optional_fields;
  const showBbt = flags?.bbt ?? false;
  const showDischarge = flags?.discharge ?? false;
  const showIntimacy = flags?.intimacy ?? false;

  // CHK-4: Hidden by default if none are enabled in settings
  if (!showBbt && !showDischarge && !showIntimacy) {
    return null;
  }

  const isFahrenheit = settings?.temp_unit === 'F';
  const unitLabel = isFahrenheit ? t.bbt.unitF : t.bbt.unitC;

  const displayBbt =
    bbt === null
      ? ''
      : isFahrenheit
        ? (Math.round(((bbt * 9) / 5 + 32) * 100) / 100).toString()
        : bbt.toString();

  const handleBbtChange = (raw: string) => {
    if (disabled) return;
    if (!raw.trim()) {
      onBbtChange(null);
      return;
    }
    const parsed = parseFloat(raw);
    if (isNaN(parsed)) return;
    if (isFahrenheit) {
      const c = Math.round((((parsed - 32) * 5) / 9) * 100) / 100;
      onBbtChange(c);
    } else {
      onBbtChange(Math.round(parsed * 100) / 100);
    }
  };

  const hadSex = intimacy?.logged ?? false;
  const isProtected = intimacy?.protected ?? true;
  const dischargeValue = discharge ?? '';

  return (
    <section className={styles.section} aria-label={t.title}>
      <h3 className={styles.title}>{t.title}</h3>

      {showBbt && (
        <TextField
          name="bbt"
          label={t.bbt.labelWithUnit(unitLabel)}
          value={displayBbt}
          type="number"
          onChange={handleBbtChange}
        />
      )}

      {showDischarge && (
        <Select<string>
          name="discharge"
          label={t.discharge.label}
          options={DISCHARGE_OPTIONS}
          value={dischargeValue}
          onChange={(val) => !disabled && onDischargeChange(val || null)}
        />
      )}

      {showIntimacy && (
        <div className={styles.intimacyRow}>
          <Switch
            label={t.intimacy.hadSex}
            checked={hadSex}
            onChange={(checked) => {
              if (disabled) return;
              if (checked) {
                onIntimacyChange({ logged: true, protected: true });
              } else {
                onIntimacyChange(null);
              }
            }}
          />
          {hadSex && (
            <div className={styles.intimacyOptions}>
              <Chip
                pressed={isProtected}
                onChange={() => !disabled && onIntimacyChange({ logged: true, protected: true })}
              >
                {t.intimacy.protected}
              </Chip>
              <Chip
                pressed={!isProtected}
                onChange={() => !disabled && onIntimacyChange({ logged: true, protected: false })}
              >
                {t.intimacy.unprotected}
              </Chip>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
