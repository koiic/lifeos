import { useState } from 'react';

import { Button } from '../Button';
import styles from './CodeList.module.css';

export interface CodeListProps {
  /** Names the list for assistive technology. */
  label: string;
  codes: readonly string[];
  copyLabel: string;
  /** Announced once the codes are on the clipboard. */
  copiedLabel: string;
  /** Announced when the browser refused to copy (e.g. no permission). */
  copyFailedLabel: string;
}

function canCopy(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.clipboard?.writeText === 'function';
}

/** AUTH-4: one-time codes, shown once, in order, copyable. Never translated by the browser. */
export function CodeList({ label, codes, copyLabel, copiedLabel, copyFailedLabel }: CodeListProps) {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join('\n'));
      setStatus('copied');
    } catch {
      setStatus('failed');
    }
  };

  return (
    <div className={styles.wrap}>
      <ol className={styles.list} aria-label={label} translate="no">
        {codes.map((code) => (
          <li key={code} className={styles.code}>
            {code}
          </li>
        ))}
      </ol>
      {canCopy() && (
        <Button variant="secondary" icon="copy" onClick={() => void copy()}>
          {copyLabel}
        </Button>
      )}
      <p className={styles.status} role="status">
        {status === 'copied' ? copiedLabel : status === 'failed' ? copyFailedLabel : ''}
      </p>
    </div>
  );
}
