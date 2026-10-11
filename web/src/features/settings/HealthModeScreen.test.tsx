import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as healthApi from '../../lib/api/health';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { HealthModeScreen } from './HealthModeScreen';

const t = copy.healthMode;

describe('HealthModeScreen (SET-4, MOD-1, MOD-2)', () => {
  const mockMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(healthApi, 'useHealthProfile').mockReturnValue({
      data: {
        mode: 'standard',
        mode_started_on: '2026-10-01',
        usual_cycle_length: 28,
        usual_period_length: 5,
        last_period_hint: '2026-09-15',
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useHealthProfile>);

    vi.spyOn(healthApi, 'useUpdateHealthProfile').mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useUpdateHealthProfile>);
  });

  afterEach(() => {
    cleanup();
  });

  it('[SET-4] renders health modes and displays started_on date', () => {
    renderRoute(<HealthModeScreen />, {
      path: '/settings/mode',
      url: '/settings/mode',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.title })).toBeDefined();
    expect(screen.getByText(t.modes.standard.label)).toBeDefined();
    expect(screen.getByText(t.modes.postpartum.label)).toBeDefined();
    expect(screen.getByText(t.modes.ttc.label)).toBeDefined();
    expect(screen.getByText(t.modes.avoid.label)).toBeDefined();

    // Current mode started_on displayed
    expect(screen.getByText(/Started on 1 Oct 2026/i)).toBeDefined();
  });

  it('[MOD-2] selects postpartum mode, shows recovery note, and triggers update', () => {
    renderRoute(<HealthModeScreen />, {
      path: '/settings/mode',
      url: '/settings/mode',
    });

    // Select postpartum
    const postpartumRadio = screen.getByRole('radio', {
      name: new RegExp(t.modes.postpartum.label, 'i'),
    });
    fireEvent.click(postpartumRadio);

    // Shows 2-cycle waiting note
    expect(screen.getByRole('note')).toBeDefined();
    expect(screen.getByText(t.postpartumNote)).toBeDefined();

    // Click Save
    const saveButton = screen.getByRole('button', { name: t.save });
    fireEvent.click(saveButton);

    expect(mockMutate).toHaveBeenCalledWith({ mode: 'postpartum' }, expect.any(Object));
  });

  it('[MOD-1] saves standard mode', () => {
    vi.spyOn(healthApi, 'useHealthProfile').mockReturnValue({
      data: {
        mode: 'postpartum',
        mode_started_on: '2026-10-01',
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useHealthProfile>);

    renderRoute(<HealthModeScreen />, {
      path: '/settings/mode',
      url: '/settings/mode',
    });

    // Select standard mode
    const standardRadio = screen.getByRole('radio', {
      name: new RegExp(t.modes.standard.label, 'i'),
    });
    fireEvent.click(standardRadio);

    // Save
    const saveButton = screen.getByRole('button', { name: t.save });
    fireEvent.click(saveButton);

    expect(mockMutate).toHaveBeenCalledWith({ mode: 'standard' }, expect.any(Object));
  });

  it('[SET-4] passes axe accessibility checks', async () => {
    const { container } = renderRoute(<HealthModeScreen />, {
      path: '/settings/mode',
      url: '/settings/mode',
    });

    await expectNoAxeViolations(container);
  });
});
