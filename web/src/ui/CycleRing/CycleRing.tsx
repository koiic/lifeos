import { useId } from 'react';

import styles from './CycleRing.module.css';

export interface CycleRingProps {
  cycleLength?: number | null | undefined;
  periodDays?: number | null | undefined;
  fertileStart?: number | null | undefined;
  fertileEnd?: number | null | undefined;
  today?: number | null | undefined;
  phase?: string | null | undefined;
  state?: string | null | undefined;
  size?: 'mini' | 'regular' | undefined;
  ariaLabel?: string | undefined;
  className?: string | undefined;
}

function polarToCartesian(cx: number, cy: number, r: number, angleDegrees: number) {
  // 0 degrees is 12 o'clock, clockwise
  const rad = ((angleDegrees - 90) * Math.PI) / 180.0;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function describeArc(
  cx: number,
  cy: number,
  r: number,
  startAngle: number,
  endAngle: number,
): string {
  const span = endAngle - startAngle;
  if (span <= 0.05) {
    return '';
  }
  if (span >= 359.9) {
    const start = polarToCartesian(cx, cy, r, startAngle);
    const mid = polarToCartesian(cx, cy, r, startAngle + 180);
    const end = polarToCartesian(cx, cy, r, startAngle + 359.9);
    return `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${mid.x} ${mid.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`;
  }
  const start = polarToCartesian(cx, cy, r, startAngle);
  const end = polarToCartesian(cx, cy, r, endAngle);
  const largeArcFlag = span > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
}

const PHASE_LABELS: Record<string, string> = {
  menstrual: 'Menstrual phase',
  follicular: 'Follicular phase',
  fertile_window: 'Fertile window',
  luteal: 'Luteal phase',
};

/**
 * Spec 5.5, CSC-1:
 * CycleRing renders an SVG circle with period arc, fertile window arc, today marker,
 * center day number and phase label.
 */
export function CycleRing({
  cycleLength = 28,
  periodDays,
  fertileStart,
  fertileEnd,
  today,
  phase,
  state,
  size,
  ariaLabel,
  className = '',
}: CycleRingProps) {
  const isMini = size === 'mini';
  const dimension = isMini ? 64 : 280;
  const cx = 140;
  const cy = 140;
  const strokeWidth = isMini ? 18 : 16;
  const r = 140 - strokeWidth / 2 - 4;

  const totalDays = cycleLength && cycleLength > 0 ? cycleLength : 28;
  const effectivePeriod = periodDays && periodDays > 0 ? Math.min(periodDays, totalDays) : 0;

  // Period arc: 0 to (periodDays / totalDays) * 360
  const periodEndAngle = effectivePeriod > 0 ? (effectivePeriod / totalDays) * 360 : 0;
  const periodPath = describeArc(cx, cy, r, 0, periodEndAngle);

  // Fertile window arc: (fertileStart - 1) to fertileEnd
  let fertilePath = '';
  if (
    fertileStart !== null &&
    fertileStart !== undefined &&
    fertileEnd !== null &&
    fertileEnd !== undefined &&
    fertileStart > 0 &&
    fertileEnd >= fertileStart
  ) {
    const fStart = Math.min(fertileStart, totalDays);
    const fEnd = Math.min(fertileEnd, totalDays);
    const fStartAngle = ((fStart - 1) / totalDays) * 360;
    const fEndAngle = (fEnd / totalDays) * 360;
    fertilePath = describeArc(cx, cy, r, fStartAngle, fEndAngle);
  }

  // Today marker: angle at center of today's slot
  let todayCoords: { x: number; y: number } | null = null;
  if (today !== null && today !== undefined && today > 0) {
    const dayFraction = ((today - 0.5) % totalDays) / totalDays;
    const todayAngle = dayFraction * 360;
    todayCoords = polarToCartesian(cx, cy, r, todayAngle);
  }

  // Default accessible aria label
  const phaseName = phase ? (PHASE_LABELS[phase] ?? phase) : undefined;
  let computedAriaLabel = ariaLabel;
  if (!computedAriaLabel) {
    if (state === 'waiting') {
      computedAriaLabel = 'Waiting for cycle to return';
    } else if (state === 'no_data' || (today === null && !periodDays)) {
      computedAriaLabel = 'No cycle data';
    } else if (today !== null && today !== undefined) {
      computedAriaLabel = phaseName
        ? `Day ${String(today)} of ${String(totalDays)}, ${phaseName}`
        : `Day ${String(today)} of ${String(totalDays)}`;
    } else {
      computedAriaLabel = `Cycle ring, ${String(totalDays)} days`;
    }
  }

  const titleId = useId();

  return (
    <div className={`${styles.root} ${isMini ? styles.mini : ''} ${className}`.trim()}>
      <svg
        className={styles.svg}
        viewBox="0 0 280 280"
        width={dimension}
        height={dimension}
        role="img"
        aria-label={computedAriaLabel}
        aria-labelledby={titleId}
      >
        <title id={titleId}>{computedAriaLabel}</title>

        {/* Base Track */}
        <circle className={styles.track} cx={cx} cy={cy} r={r} strokeWidth={strokeWidth} />

        {/* Fertile Window Arc */}
        {fertilePath && (
          <path
            className={styles.fertileArc}
            d={fertilePath}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
        )}

        {/* Period Arc */}
        {periodPath && (
          <path
            className={styles.periodArc}
            d={periodPath}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
        )}

        {/* Today Marker */}
        {todayCoords && (
          <circle
            className={styles.todayMarker}
            cx={todayCoords.x}
            cy={todayCoords.y}
            r={isMini ? 8 : 7}
          />
        )}
      </svg>

      {/* Center content (full ring only) */}
      {!isMini && (
        <div className={styles.centerContent} aria-hidden="true">
          {today !== null && today !== undefined && today > 0 ? (
            <>
              <span className={styles.dayNumber}>{today}</span>
              <span className={styles.dayLabel}>Day</span>
              {phaseName && <span className={styles.phaseLabel}>{phaseName}</span>}
            </>
          ) : state === 'waiting' ? (
            <span className={styles.placeholder}>Waiting</span>
          ) : (
            <span className={styles.placeholder}>—</span>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Mini ring for compact cards (Today screen, spec 5.5).
 */
export function MiniRing(props: Omit<CycleRingProps, 'size'> & { size?: number | undefined }) {
  return <CycleRing {...props} size="mini" />;
}
