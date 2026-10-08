import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoAxeViolations } from '../testing/axe';
import { CodeList } from './CodeList';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const codes = Array.from({ length: 10 }, (_, i) => `code-${String(i).padStart(2, '0')}-xyz`);

describe('[AUTH-4] CodeList: recovery codes shown once', () => {
  it('lists every code in order, in a labelled list', async () => {
    const { container } = render(
      <CodeList
        label="Recovery codes"
        codes={codes}
        copyLabel="Copy"
        copiedLabel="Copied"
        copyFailedLabel="Couldn't copy"
      />,
    );
    const list = screen.getByRole('list', { name: 'Recovery codes' });
    const items = screen.getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual(codes);
    expect(list.getAttribute('translate')).toBe('no');
    await expectNoAxeViolations(container);
  });

  it('copies all codes, one per line, and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(
      <CodeList
        label="Recovery codes"
        codes={codes}
        copyLabel="Copy"
        copiedLabel="Copied"
        copyFailedLabel="Couldn't copy"
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
      await Promise.resolve();
    });
    expect(writeText).toHaveBeenCalledWith(codes.join('\n'));
    expect(screen.getByRole('status').textContent).toBe('Copied');
  });

  it('without a clipboard, there is no copy button', () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
    render(
      <CodeList
        label="Recovery codes"
        codes={codes}
        copyLabel="Copy"
        copiedLabel="Copied"
        copyFailedLabel="Couldn't copy"
      />,
    );
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('says so when the codes could not be copied', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('not allowed'));
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(
      <CodeList
        label="Recovery codes"
        codes={codes}
        copyLabel="Copy"
        copiedLabel="Copied"
        copyFailedLabel="Couldn't copy"
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
      await Promise.resolve();
    });
    expect(screen.getByRole('status').textContent).toBe("Couldn't copy");
  });
});
