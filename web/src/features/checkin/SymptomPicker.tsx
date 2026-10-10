import { useState } from 'react';

import { copy } from '../../copy/en-GB';
import { useCreateSymptom, useSymptoms } from '../../lib/api';
import { Button } from '../../ui/Button';
import { Chip } from '../../ui/Chip';
import { Icon } from '../../ui/icons';
import { Select, type SelectOption } from '../../ui/Select';
import { TextField } from '../../ui/TextField';
import styles from './SymptomPicker.module.css';

const t = copy.checkin.symptoms;

type Category = 'pain' | 'digestion' | 'skin' | 'emotional' | 'energy' | 'other';

const CATEGORY_OPTIONS: readonly SelectOption<Category>[] = [
  { value: 'pain', label: t.categories.pain },
  { value: 'digestion', label: t.categories.digestion },
  { value: 'skin', label: t.categories.skin },
  { value: 'emotional', label: t.categories.emotional },
  { value: 'energy', label: t.categories.energy },
  { value: 'other', label: t.categories.other },
] as const;

export interface SymptomPickerProps {
  selectedIds: readonly string[];
  onChange: (selectedIds: string[]) => void;
  disabled?: boolean;
}

/** Multi-select symptoms chips with custom symptom creation (CHK-1, CHK-3). */
export function SymptomPicker({ selectedIds, onChange, disabled }: SymptomPickerProps) {
  const { data: symptoms = [] } = useSymptoms();
  const createSymptom = useCreateSymptom();

  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState<Category>('other');
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string, pressed: boolean) => {
    if (pressed) {
      if (!selectedIds.includes(id)) {
        onChange([...selectedIds, id]);
      }
    } else {
      onChange(selectedIds.filter((item) => item !== id));
    }
  };

  const handleAdd = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError(t.nameRequired);
      return;
    }
    setError(null);
    try {
      const created = await createSymptom.mutateAsync({ name: trimmed, category, sort_order: 0 });
      onChange([...selectedIds, created.id]);
      setName('');
      setCategory('other');
      setAdding(false);
    } catch {
      setError(t.failed);
    }
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.label}>{t.label}</span>
        {!adding && (
          <button
            type="button"
            className={styles.addButton}
            disabled={disabled}
            onClick={() => setAdding(true)}
          >
            <Icon name="plus" size="sm" />
            <span>{t.addCustom}</span>
          </button>
        )}
      </div>

      {adding && (
        <div className={styles.addForm}>
          <TextField
            name="newSymptomName"
            label={t.nameLabel}
            value={name}
            hint={t.namePlaceholder}
            {...(error !== null ? { error } : {})}
            onChange={setName}
          />
          <Select<Category>
            name="newSymptomCategory"
            label={t.categoryLabel}
            options={CATEGORY_OPTIONS}
            value={category}
            onChange={setCategory}
          />
          <div className={styles.formActions}>
            <Button
              variant="ghost"
              onClick={() => {
                setAdding(false);
                setName('');
                setError(null);
              }}
            >
              {t.cancel}
            </Button>
            <Button busy={createSymptom.isPending} onClick={handleAdd}>
              {t.create}
            </Button>
          </div>
        </div>
      )}

      <div className={styles.chips} role="group" aria-label={t.label}>
        {symptoms.map((symptom) => {
          const isSelected = selectedIds.includes(symptom.id);
          return (
            <Chip
              key={symptom.id}
              pressed={isSelected}
              onChange={(pressed) => toggle(symptom.id, pressed)}
            >
              {symptom.name}
            </Chip>
          );
        })}
      </div>
    </div>
  );
}
