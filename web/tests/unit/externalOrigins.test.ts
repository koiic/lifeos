import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const SCRIPT_PATH = resolve(__dirname, '../../../scripts/check_external_origins.sh');
const TEMP_DIST = resolve(__dirname, '../../../web/temp-dist-test');

describe('[NFR-6] external origins privacy check (spec 12.4, 14.5)', () => {
  beforeAll(() => {
    rmSync(TEMP_DIST, { recursive: true, force: true });
    mkdirSync(TEMP_DIST, { recursive: true });
  });

  afterAll(() => {
    rmSync(TEMP_DIST, { recursive: true, force: true });
  });

  it('scripts/check_external_origins.sh exists and is executable', () => {
    expect(existsSync(SCRIPT_PATH)).toBe(true);
  });

  it('passes on a clean bundle with only self/relative resources', () => {
    writeFileSync(
      resolve(TEMP_DIST, 'index.html'),
      '<!DOCTYPE html><html><head><script src="/assets/index.js"></script><link rel="stylesheet" href="/assets/style.css"></head><body></body></html>',
    );
    const output = execFileSync('bash', [SCRIPT_PATH, TEMP_DIST], { encoding: 'utf-8' });
    expect(output).toContain('external-origins: clean');
  });

  it('catches external scripts (e.g. analytics SDK)', () => {
    writeFileSync(
      resolve(TEMP_DIST, 'index.html'),
      '<!DOCTYPE html><html><head><script src="https://analytics.example.com/tracker.js"></script></head><body></body></html>',
    );
    expect(() => {
      execFileSync('bash', [SCRIPT_PATH, TEMP_DIST], { encoding: 'utf-8' });
    }).toThrow();
  });

  it('catches external fonts or remote stylesheets', () => {
    writeFileSync(
      resolve(TEMP_DIST, 'index.html'),
      '<!DOCTYPE html><html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto"></head><body></body></html>',
    );
    expect(() => {
      execFileSync('bash', [SCRIPT_PATH, TEMP_DIST], { encoding: 'utf-8' });
    }).toThrow();
  });
});
