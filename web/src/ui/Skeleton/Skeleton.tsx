import hidden from '../internal/visuallyHidden.module.css';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  /** Announced once while loading, e.g. "Loading today". */
  label: string;
  shapes: readonly ('line' | 'block' | 'circle')[];
}

/** Spec 5.5; plan 5.5 loading state. Static placeholders: nothing animates or loops (5.6). */
export function Skeleton({ label, shapes }: SkeletonProps) {
  return (
    <div className={styles.skeleton} role="status" aria-label={label}>
      {/* Announced as text too: some screen readers ignore a status region's aria-label. */}
      <span className={hidden.visuallyHidden}>{label}</span>
      {shapes.map((shape, index) => (
        <span key={index} className={styles.shape} data-shape={shape} aria-hidden="true" />
      ))}
    </div>
  );
}
