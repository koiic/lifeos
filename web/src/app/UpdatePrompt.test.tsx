import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRegisterSW } from 'virtual:pwa-register/react';

import { copy } from '../copy/en-GB';
import { UpdatePrompt } from './UpdatePrompt';

vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: vi.fn() }));

const updateServiceWorker = vi.fn();
const setNeedRefresh = vi.fn();

function waiting(needRefresh: boolean) {
  vi.mocked(useRegisterSW).mockReturnValue({
    needRefresh: [needRefresh, setNeedRefresh],
    offlineReady: [false, vi.fn()],
    updateServiceWorker,
  });
}

beforeEach(() => {
  updateServiceWorker.mockReset();
  setNeedRefresh.mockReset();
});

afterEach(cleanup);

describe('update prompt (spec 11.3: registerType prompt)', () => {
  it('registers the service worker without updating by itself', () => {
    waiting(false);
    render(<UpdatePrompt />);
    expect(useRegisterSW).toHaveBeenCalled();
    expect(updateServiceWorker).not.toHaveBeenCalled();
  });

  it('nothing to show while no new version is waiting', () => {
    waiting(false);
    render(<UpdatePrompt />);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('a waiting version: "New version ready — Refresh"; Refresh activates it and reloads', () => {
    waiting(true);
    render(<UpdatePrompt />);
    const toast = screen.getByRole('status');
    expect(toast.textContent).toContain(copy.update.ready);
    fireEvent.click(screen.getByRole('button', { name: copy.update.refresh }));
    expect(updateServiceWorker).toHaveBeenCalledWith(true);
  });

  it('dismissing keeps the current version until the next cold start', () => {
    waiting(true);
    render(<UpdatePrompt />);
    fireEvent.click(screen.getByRole('button', { name: copy.common.dismiss }));
    expect(setNeedRefresh).toHaveBeenCalledWith(false);
    expect(updateServiceWorker).not.toHaveBeenCalled();
  });

  it('floats above the page so it is seen wherever she is', () => {
    waiting(true);
    render(<UpdatePrompt />);
    expect((screen.getByRole('status') as HTMLElement).dataset.placement).toBe('floating');
  });
});
