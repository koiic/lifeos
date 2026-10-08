import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Chip, ChipGroup } from './Chip';

afterEach(cleanup);

describe('Chip (spec 5.5: toggle, choice)', () => {
  it('a toggle chip is a pressed/unpressed button', async () => {
    const onChange = vi.fn();
    const { container, rerender } = render(
      <Chip pressed={false} onChange={onChange}>
        Cramps
      </Chip>,
    );
    const chip = screen.getByRole('button', { name: 'Cramps' });
    expect(chip.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(chip);
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(
      <Chip pressed onChange={onChange}>
        Cramps
      </Chip>,
    );
    expect(chip.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith(false);
    await expectNoAxeViolations(container);
  });

  it('choice chips are a labelled radio group with one value', async () => {
    const onChange = vi.fn();
    const options = [
      { value: 'light', label: 'Light' },
      { value: 'medium', label: 'Medium' },
      { value: 'heavy', label: 'Heavy' },
    ];
    const { container } = render(
      <ChipGroup legend="Flow" name="flow" options={options} value="medium" onChange={onChange} />,
    );
    const group = screen.getByRole('radiogroup', { name: 'Flow' });
    expect(group).toBeDefined();
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect((screen.getByRole('radio', { name: 'Medium' }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole('radio', { name: 'Heavy' }));
    expect(onChange).toHaveBeenCalledWith('heavy');
    await expectNoAxeViolations(container);
  });

  it('choice chips share one radio name, so the browser makes them one group', () => {
    render(
      <ChipGroup
        legend="Flow"
        name="flow"
        options={[
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ]}
        value="a"
        onChange={() => undefined}
      />,
    );
    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    expect(radios.every((radio) => radio.name === 'flow')).toBe(true);
    radios[0]?.focus();
    expect(document.activeElement).toBe(radios[0]);
  });

  it('marks the selected state with a check mark, not by colour alone (spec 5.8)', () => {
    const { container, rerender } = render(
      <Chip pressed={false} onChange={() => undefined}>
        Cramps
      </Chip>,
    );
    expect(container.querySelector('svg')).toBeNull();
    rerender(
      <Chip pressed onChange={() => undefined}>
        Cramps
      </Chip>,
    );
    expect(container.querySelectorAll('svg')).toHaveLength(1);
    cleanup();
    const group = render(
      <ChipGroup
        legend="Flow"
        name="flow"
        value="light"
        onChange={() => undefined}
        options={[
          { value: 'light', label: 'Light' },
          { value: 'heavy', label: 'Heavy' },
        ]}
      />,
    );
    const labels = group.container.querySelectorAll('label');
    expect(labels[0]?.querySelector('svg')).not.toBeNull();
    expect(labels[1]?.querySelector('svg')).toBeNull();
  });

  it('the choice group is named once, by its legend', () => {
    render(
      <ChipGroup
        legend="Flow"
        name="flow"
        value="light"
        onChange={() => undefined}
        options={[{ value: 'light', label: 'Light' }]}
      />,
    );
    const group = screen.getByRole('radiogroup', { name: 'Flow' });
    expect(group.hasAttribute('aria-label')).toBe(false);
  });
});
