import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { copy } from '../../copy/en-GB';
import type { CyclePredictionResponse } from '../../lib/api/health';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { PredictionCard } from './PredictionCard';

const t = copy.health.cycle;

const standardPrediction: CyclePredictionResponse = {
  predicted_start: '2026-10-23',
  range_low: '2026-10-22',
  range_high: '2026-10-24',
  confidence: 'medium',
  ovulation_est: '2026-10-09',
  fertile_start: '2026-10-04',
  fertile_end: '2026-10-10',
  n_cycles: 4,
  mean_len: 28.75,
  sd_len: 0.5,
  mean_period_len: 5,
  algorithm_version: 'calendar-1.0',
  suppressed_reason: null,
};

describe('PredictionCard (CSC-2, CYC-3, CYC-4, CYC-6)', () => {
  afterEach(() => {
    cleanup();
  });

  it('[CSC-2] renders predicted range and cycle count context', () => {
    render(<PredictionCard prediction={standardPrediction} state="upcoming" />);

    expect(screen.getByText('22 Oct – 24 Oct')).toBeDefined();
    expect(screen.getByText('Based on 4 cycles')).toBeDefined();
    expect(screen.getByText(t.prediction.confidence.medium)).toBeDefined();
  });

  it('[CYC-3] renders fertile window with mandatory disclaimer', () => {
    render(<PredictionCard prediction={standardPrediction} state="upcoming" />);

    expect(screen.getByText('Estimated fertile window: 4 Oct – 10 Oct')).toBeDefined();
    expect(screen.getByText('Estimated ovulation: 9 Oct')).toBeDefined();
    expect(screen.getByText('Estimate, not contraception')).toBeDefined();
  });

  it('[CYC-4] shows helper text for low confidence', () => {
    const lowPred: CyclePredictionResponse = {
      ...standardPrediction,
      confidence: 'low',
      n_cycles: 1,
    };
    render(<PredictionCard prediction={lowPred} state="upcoming" />);

    expect(screen.getByText(t.prediction.confidence.low)).toBeDefined();
    expect(screen.getByText(t.prediction.confidence.lowHelper)).toBeDefined();
  });

  it('[CYC-6] renders irregularity note when cycles vary by > 7 days', () => {
    render(
      <PredictionCard
        prediction={{ ...standardPrediction, confidence: 'low' }}
        state="irregular"
        notes={[{ kind: 'irregular_cycles', text: 'Cycles vary' }]}
      />,
    );

    expect(screen.getByText(t.states.irregular)).toBeDefined();
  });

  it('[CYC-6] renders NHS guidance link when long gap is detected', () => {
    render(
      <PredictionCard
        prediction={{ ...standardPrediction, confidence: 'none', suppressed_reason: 'no_data' }}
        state="long_gap"
        notes={[{ kind: 'data_gap', text: 'Long gap' }]}
      />,
    );

    expect(screen.getByText(t.states.long_gap)).toBeDefined();
    const link = screen.getByRole('link', { name: t.states.nhsGuidance });
    expect(link.getAttribute('href')).toBe(
      'https://www.nhs.uk/conditions/stopped-or-missed-periods/',
    );
  });

  it('[CSC-2] renders waiting state when postpartum mode is active', () => {
    const waitingPred: CyclePredictionResponse = {
      ...standardPrediction,
      confidence: 'none',
      suppressed_reason: 'postpartum_waiting',
    };
    render(<PredictionCard prediction={waitingPred} state="waiting" />);

    expect(screen.getByText(t.states.waiting)).toBeDefined();
    expect(screen.queryByText('Based on 4 cycles')).toBeNull();
  });

  it('[CSC-2] passes axe accessibility checks', async () => {
    const { container } = render(
      <PredictionCard prediction={standardPrediction} state="upcoming" />,
    );

    await expectNoAxeViolations(container);
  });
});
