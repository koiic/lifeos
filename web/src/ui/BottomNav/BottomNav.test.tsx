import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { BottomNav } from './BottomNav';

afterEach(cleanup);

const items = [
  { to: '/today', label: 'Today', icon: 'home' },
  { to: '/health', label: 'Health', icon: 'droplet' },
  { to: '/calendar', label: 'Calendar', icon: 'calendar' },
  { to: '/more', label: 'More', icon: 'more' },
] as const;

const add = { label: 'Add', onPress: () => undefined };

describe('BottomNav (spec 5.1, 5.5)', () => {
  it('is a labelled navigation landmark of links; the current one is marked', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/health/cycle']}>
        <BottomNav label="Main" items={items} action={add} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole('navigation', { name: 'Main' });
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(4);
    expect(nav.contains(links[0] ?? null)).toBe(true);
    expect(screen.getByRole('link', { name: 'Health' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'Today' }).getAttribute('aria-current')).toBeNull();
    expect(screen.getByRole('link', { name: 'Calendar' }).getAttribute('href')).toBe('/calendar');
    await expectNoAxeViolations(container);
  });

  it('has five slots: the add action in the middle, between Health and Calendar (spec 5.1)', () => {
    const onPress = vi.fn();
    render(
      <MemoryRouter initialEntries={['/today']}>
        <BottomNav label="Main" items={items} action={{ label: 'Add', onPress }} />
      </MemoryRouter>,
    );
    const slots = screen.getAllByRole('listitem');
    expect(slots).toHaveLength(5);
    const action = screen.getByRole('button', { name: 'Add' });
    expect(slots[2]?.contains(action)).toBe(true);
    expect(slots[1]?.textContent).toBe('Health');
    expect(slots[3]?.textContent).toBe('Calendar');
    fireEvent.click(action);
    expect(onPress).toHaveBeenCalledOnce();
  });
});
