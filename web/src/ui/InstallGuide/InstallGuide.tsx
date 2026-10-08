import { Button } from '../Button';
import { Icon, type IconName } from '../icons';
import styles from './InstallGuide.module.css';

export interface InstallStep {
  /** The illustration: the button or screen she looks for. */
  icon: IconName;
  text: string;
}

export interface InstallGuideProps {
  /** Names the list of steps for assistive technology. */
  label: string;
  steps: readonly InstallStep[];
  note?: string;
  continueLabel: string;
  onContinue: () => void;
}

/** Spec 5.5, ONB-1: the numbered steps to add the app to the Home Screen; dismissible. */
export function InstallGuide({ label, steps, note, continueLabel, onContinue }: InstallGuideProps) {
  return (
    <div className={styles.guide}>
      {/* role="list": Safari drops a list's semantics when its markers are hidden. */}
      {/* eslint-disable-next-line jsx-a11y/no-redundant-roles -- see above (WebKit) */}
      <ol className={styles.steps} aria-label={label} role="list">
        {steps.map((step) => (
          <li key={step.text} className={styles.step}>
            <span className={styles.illustration}>
              <Icon name={step.icon} />
            </span>
            <span className={styles.text}>{step.text}</span>
          </li>
        ))}
      </ol>
      {note !== undefined && <p className={styles.note}>{note}</p>}
      <Button variant="ghost" onClick={onContinue}>
        {continueLabel}
      </Button>
    </div>
  );
}
