import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import * as healthApi from '../../lib/api/health';
import * as meLib from '../../lib/me/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { SetupWizardScreen } from './SetupWizardScreen';

const t = copy.setup;
const tModes = copy.healthMode.modes;

describe('SetupWizardScreen (ONB-2, MOD-1, MOD-2)', () => {
  const mockUpdateProfile = vi.fn().mockResolvedValue({});
  const mockChangeSettings = vi.fn().mockResolvedValue({});
  const mockGiveConsent = vi.fn().mockResolvedValue({});

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(healthApi, 'useHealthProfile').mockReturnValue({
      data: {
        mode: 'standard',
        mode_started_on: null,
        usual_cycle_length: null,
        usual_period_length: null,
        last_period_hint: null,
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useHealthProfile>);

    vi.spyOn(healthApi, 'useUpdateHealthProfile').mockReturnValue({
      mutateAsync: mockUpdateProfile,
      isPending: false,
    } as unknown as ReturnType<typeof healthApi.useUpdateHealthProfile>);

    vi.spyOn(meLib, 'useMe').mockReturnValue({
      data: {
        settings: {
          checkin_time: '21:00',
          notif_prefs: { period_due: true },
        },
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof meLib.useMe>);

    vi.spyOn(meLib, 'useChangeSettings').mockReturnValue({
      mutateAsync: mockChangeSettings,
      isPending: false,
    } as unknown as ReturnType<typeof meLib.useChangeSettings>);

    vi.spyOn(meLib, 'useGiveConsent').mockReturnValue({
      mutate: mockGiveConsent,
      mutateAsync: mockGiveConsent,
      isPending: false,
    } as unknown as ReturnType<typeof meLib.useGiveConsent>);
  });

  afterEach(() => {
    cleanup();
  });

  it('[ONB-2][MOD-1] Step 1 renders health modes, updates mode and advances to step 2', async () => {
    renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/1',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.step1.title })).toBeDefined();
    expect(screen.getByText(tModes.standard.label)).toBeDefined();
    expect(screen.getByText(tModes.postpartum.label)).toBeDefined();

    // Select standard mode and click Next
    const standardRadio = screen.getByRole('radio', {
      name: new RegExp(tModes.standard.label, 'i'),
    });
    fireEvent.click(standardRadio);

    const nextBtn = screen.getByRole('button', { name: t.next });
    fireEvent.click(nextBtn);

    expect(mockUpdateProfile).toHaveBeenCalledWith({ mode: 'standard' });
  });

  it('[ONB-2][MOD-2] Step 2 handles last period date or postpartum checkbox', async () => {
    vi.spyOn(healthApi, 'useHealthProfile').mockReturnValue({
      data: {
        mode: 'postpartum',
        last_period_hint: null,
      },
      isSuccess: true,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof healthApi.useHealthProfile>);

    renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/2',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.step2.title })).toBeDefined();
    expect(screen.getByText(t.step2.notYetPostpartum)).toBeDefined();

    // Check "haven't had period yet" checkbox
    const checkbox = screen.getByLabelText(t.step2.notYetPostpartum);
    fireEvent.click(checkbox);

    const nextBtn = screen.getByRole('button', { name: t.next });
    fireEvent.click(nextBtn);

    expect(mockUpdateProfile).toHaveBeenCalledWith({ last_period_hint: null });
  });

  it('[ONB-2] Step 3 sets typical cycle and period length with defaults button', async () => {
    renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/3',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.step3.title })).toBeDefined();

    // Click "Use standard averages"
    const defaultsBtn = screen.getByRole('button', { name: t.step3.useDefaults });
    fireEvent.click(defaultsBtn);

    const nextBtn = screen.getByRole('button', { name: t.next });
    fireEvent.click(nextBtn);

    expect(mockUpdateProfile).toHaveBeenCalledWith({
      usual_cycle_length: 28,
      usual_period_length: 5,
    });
  });

  it('[ONB-2] Step 4 finishes wizard, saves reminders and records consent', async () => {
    renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/4',
    });

    expect(screen.getByRole('heading', { level: 1, name: t.step4.title })).toBeDefined();

    const finishBtn = screen.getByRole('button', { name: t.finish });
    fireEvent.click(finishBtn);

    await vi.waitFor(() => {
      expect(mockChangeSettings).toHaveBeenCalledWith({
        checkin_time: '21:00',
        notif_prefs: { period_due: true },
      });
      expect(mockGiveConsent).toHaveBeenCalledWith({ version: '1' });
    });
  });

  it('[ONB-2] allows skipping any step without failing', () => {
    renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/1',
    });

    const skipBtn = screen.getByRole('button', { name: t.skip });
    fireEvent.click(skipBtn);

    // Profile mutation should not have been called on skip
    expect(mockUpdateProfile).not.toHaveBeenCalled();
  });

  it('[ONB-2] passes axe accessibility audits', async () => {
    const { container } = renderRoute(<SetupWizardScreen />, {
      path: '/setup/:step',
      url: '/setup/1',
    });

    await expectNoAxeViolations(container);
  });
});
