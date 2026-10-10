import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { meBody } from '../../lib/testing/me';
import { OptionalFieldsSection } from './OptionalFieldsSection';

afterEach(cleanup);

describe('OptionalFieldsSection (CHK-4)', () => {
  const baseSettings = meBody().settings;

  it('renders nothing when all optional fields are disabled', () => {
    const { container } = render(
      <OptionalFieldsSection
        settings={baseSettings}
        bbt={null}
        onBbtChange={() => {}}
        discharge={null}
        onDischargeChange={() => {}}
        intimacy={null}
        onIntimacyChange={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders BBT input when bbt is enabled in settings', () => {
    const onBbtChange = vi.fn();
    render(
      <OptionalFieldsSection
        settings={{
          ...baseSettings,
          optional_fields: { bbt: true, discharge: false, intimacy: false },
        }}
        bbt={36.5}
        onBbtChange={onBbtChange}
        discharge={null}
        onDischargeChange={() => {}}
        intimacy={null}
        onIntimacyChange={() => {}}
      />,
    );

    const input = screen.getByLabelText(/basal body temperature/i);
    expect(input).toBeDefined();
    expect((input as HTMLInputElement).value).toBe('36.5');

    fireEvent.change(input, { target: { value: '36.8' } });
    expect(onBbtChange).toHaveBeenCalledWith(36.8);
  });

  it('renders discharge select when discharge is enabled', () => {
    const onDischargeChange = vi.fn();
    render(
      <OptionalFieldsSection
        settings={{
          ...baseSettings,
          optional_fields: { bbt: false, discharge: true, intimacy: false },
        }}
        bbt={null}
        onBbtChange={() => {}}
        discharge="eggwhite"
        onDischargeChange={onDischargeChange}
        intimacy={null}
        onIntimacyChange={() => {}}
      />,
    );

    const select = screen.getByLabelText(/cervical discharge/i);
    expect(select).toBeDefined();
    expect((select as HTMLSelectElement).value).toBe('eggwhite');

    fireEvent.change(select, { target: { value: 'creamy' } });
    expect(onDischargeChange).toHaveBeenCalledWith('creamy');
  });

  it('renders intimacy switch and chips when intimacy is enabled', () => {
    const onIntimacyChange = vi.fn();
    const { rerender } = render(
      <OptionalFieldsSection
        settings={{
          ...baseSettings,
          optional_fields: { bbt: false, discharge: false, intimacy: true },
        }}
        bbt={null}
        onBbtChange={() => {}}
        discharge={null}
        onDischargeChange={() => {}}
        intimacy={null}
        onIntimacyChange={onIntimacyChange}
      />,
    );

    const switchBtn = screen.getByRole('switch', { name: /had sex/i });
    expect(switchBtn.getAttribute('aria-checked')).toBe('false');

    // Toggle switch on
    fireEvent.click(switchBtn);
    expect(onIntimacyChange).toHaveBeenCalledWith({ logged: true, protected: true });

    // Rerender with intimacy logged
    rerender(
      <OptionalFieldsSection
        settings={{
          ...baseSettings,
          optional_fields: { bbt: false, discharge: false, intimacy: true },
        }}
        bbt={null}
        onBbtChange={() => {}}
        discharge={null}
        onDischargeChange={() => {}}
        intimacy={{ logged: true, protected: true }}
        onIntimacyChange={onIntimacyChange}
      />,
    );

    const protectedChip = screen.getByRole('button', { name: /^protected$/i });
    expect(protectedChip.getAttribute('aria-pressed')).toBe('true');

    const unprotectedChip = screen.getByRole('button', { name: /^unprotected$/i });
    expect(unprotectedChip.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(unprotectedChip);
    expect(onIntimacyChange).toHaveBeenCalledWith({ logged: true, protected: false });
  });
});
