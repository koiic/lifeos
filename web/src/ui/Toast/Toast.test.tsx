import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { Toast } from './Toast';

afterEach(cleanup);

describe('Toast (spec 5.5)', () => {
  it('announces politely and can be dismissed', async () => {
    const onDismiss = vi.fn();
    const { container } = render(
      <Toast message="Saved" dismissLabel="Dismiss" onDismiss={onDismiss} />,
    );
    const toast = screen.getByRole('status');
    expect(toast.textContent).toContain('Saved');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismiss).toHaveBeenCalledOnce();
    await expectNoAxeViolations(container);
  });

  it('an error toast is an alert', () => {
    render(
      <Toast
        tone="danger"
        message="Couldn't save"
        dismissLabel="Dismiss"
        onDismiss={() => undefined}
      />,
    );
    expect(screen.getByRole('alert').textContent).toContain("Couldn't save");
  });

  it('can offer one action', () => {
    const onAction = vi.fn();
    render(
      <Toast
        message="Update ready"
        action={{ label: 'Reload', onClick: onAction }}
        dismissLabel="Dismiss"
        onDismiss={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it('never dismisses itself (spec 5.6: nothing autoplays)', () => {
    vi.useFakeTimers();
    try {
      const onDismiss = vi.fn();
      render(<Toast message="Saved" dismissLabel="Dismiss" onDismiss={onDismiss} />);
      vi.advanceTimersByTime(60_000);
      expect(screen.getByRole('status').textContent).toContain('Saved');
      expect(onDismiss).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('can float above the page (app-wide messages), or sit in the flow (default)', () => {
    const { rerender } = render(
      <Toast message="Saved" dismissLabel="Dismiss" onDismiss={() => undefined} />,
    );
    expect((screen.getByRole('status') as HTMLElement).dataset.placement).toBe('inline');
    rerender(
      <Toast
        message="Saved"
        placement="floating"
        dismissLabel="Dismiss"
        onDismiss={() => undefined}
      />,
    );
    expect((screen.getByRole('status') as HTMLElement).dataset.placement).toBe('floating');
  });
});
