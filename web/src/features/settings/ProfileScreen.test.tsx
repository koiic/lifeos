import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copy } from '../../copy/en-GB';
import { fakeApi, problem } from '../../lib/testing/fakeApi';
import { meBody } from '../../lib/testing/me';
import { renderRoute } from '../../lib/testing/renderRoute';
import { expectNoAxeViolations } from '../../ui/testing/axe';
import { ProfileScreen } from './ProfileScreen';

const t = copy.profile;
const ME = 'GET /api/v1/me';
const PROFILE = 'PATCH /api/v1/me';
const SETTINGS = 'PATCH /api/v1/me/settings';

function open() {
  return renderRoute(<ProfileScreen />, { path: '/settings/profile', url: '/settings/profile' });
}

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('[SET-1] profile: name, timezone, week start, temperature', () => {
  it('shows her saved values, Monday and °C by default', async () => {
    fakeApi({ [ME]: { body: meBody() } });
    const { container } = open();
    expect((await screen.findByLabelText(t.name)) as HTMLInputElement).toHaveProperty(
      'value',
      'Zee',
    );
    expect(field(t.timezone).value).toBe('Europe/London');
    expect(field(t.weekStart).value).toBe('1');
    expect(field(t.temperature).value).toBe('C');
    await expectNoAxeViolations(container);
  });

  it('saves only what changed, each to its own endpoint, with its version', async () => {
    const api = fakeApi({
      [ME]: { body: meBody() },
      [PROFILE]: {
        body: {
          ...meBody().profile,
          display_name: 'Zainab',
          timezone: 'Africa/Lagos',
          version: 'p2',
        },
      },
      [SETTINGS]: { body: { ...meBody().settings, week_start: 7, temp_unit: 'F', version: 's2' } },
    });
    open();
    fireEvent.change(await screen.findByLabelText(t.name), { target: { value: 'Zainab' } });
    fireEvent.change(field(t.timezone), { target: { value: 'Africa/Lagos' } });
    fireEvent.change(field(t.weekStart), { target: { value: '7' } });
    fireEvent.change(field(t.temperature), { target: { value: 'F' } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.saved)).toBeDefined();
    expect(api.bodies(PROFILE)).toEqual([{ display_name: 'Zainab', timezone: 'Africa/Lagos' }]);
    expect(api.headers(PROFILE)[0]?.get('If-Match')).toBe('"p1"');
    expect(api.bodies(SETTINGS)).toEqual([{ week_start: 7, temp_unit: 'F' }]);
    expect(api.headers(SETTINGS)[0]?.get('If-Match')).toBe('"s1"');
  });

  it('only a settings change: the profile is not sent', async () => {
    const api = fakeApi({
      [ME]: { body: meBody() },
      [SETTINGS]: { body: { ...meBody().settings, temp_unit: 'F', version: 's2' } },
    });
    open();
    fireEvent.change(await screen.findByLabelText(t.temperature), { target: { value: 'F' } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.saved)).toBeDefined();
    expect(api.count(PROFILE)).toBe(0);
  });

  it('a name is required and at most 100 characters (inline, nothing sent)', async () => {
    const api = fakeApi({ [ME]: { body: meBody() } });
    open();
    const name = await screen.findByLabelText(t.name);
    fireEvent.change(name, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.nameRequired)).toBeDefined();
    fireEvent.change(name, { target: { value: 'x'.repeat(101) } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.nameTooLong)).toBeDefined();
    expect(api.count(PROFILE)).toBe(0);
  });

  it('changed on another device (409): the latest values load and she is told', async () => {
    const current = { ...meBody().profile, display_name: 'Zee from the laptop', version: 'p9' };
    fakeApi({
      [ME]: { body: meBody() },
      [PROFILE]: {
        status: 409,
        body: { type: 'about:blank', title: 'Conflict', status: 409, detail: 'x', current },
        headers: { 'Content-Type': 'application/problem+json' },
      },
    });
    open();
    fireEvent.change(await screen.findByLabelText(t.name), { target: { value: 'Zainab' } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.conflict)).toBeDefined();
    await waitFor(() => expect(field(t.name).value).toBe('Zee from the laptop'));
  });

  it('offline or failing: says so and keeps her input', async () => {
    fakeApi({ [ME]: { body: meBody() }, [PROFILE]: problem(503, 'down') });
    open();
    fireEvent.change(await screen.findByLabelText(t.name), { target: { value: 'Zainab' } });
    fireEvent.click(screen.getByRole('button', { name: t.save }));
    expect(await screen.findByText(t.failed)).toBeDefined();
    expect(field(t.name).value).toBe('Zainab');
  });
});
