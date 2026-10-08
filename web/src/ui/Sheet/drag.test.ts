import { describe, expect, it } from 'vitest';

import { dragOffset, shouldClose } from './drag';

describe('Sheet drag (spec 5.5 drag handle, CR-024)', () => {
  it('only a downward drag moves the sheet', () => {
    expect(dragOffset(100, 160)).toBe(60);
    expect(dragOffset(100, 40)).toBe(0);
  });

  it('closes past a quarter of the sheet height, never for a small drag', () => {
    expect(shouldClose(101, 400)).toBe(true);
    expect(shouldClose(100, 400)).toBe(false);
    // A short sheet still needs a deliberate drag (at least 48 px).
    expect(shouldClose(40, 80)).toBe(false);
    expect(shouldClose(49, 80)).toBe(true);
    expect(shouldClose(0, 0)).toBe(false);
  });
});
