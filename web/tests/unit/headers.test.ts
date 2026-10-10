import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const HEADERS_PATH = resolve(__dirname, '../../public/_headers');

function parseHeaders(content: string): Map<string, Map<string, string>> {
  const sections = new Map<string, Map<string, string>>();
  let currentPath: string | null = null;

  for (const rawLine of content.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;

    if (!rawLine.startsWith(' ') && !rawLine.startsWith('\t')) {
      currentPath = line;
      sections.set(currentPath, new Map());
    } else if (currentPath) {
      const colonIndex = line.indexOf(':');
      if (colonIndex !== -1) {
        const key = line.slice(0, colonIndex).trim().toLowerCase();
        const value = line.slice(colonIndex + 1).trim();
        sections.get(currentPath)?.set(key, value);
      }
    }
  }

  return sections;
}

describe('security headers for Cloudflare Pages (spec 12.4)', () => {
  it('public/_headers exists', () => {
    expect(existsSync(HEADERS_PATH)).toBe(true);
  });

  it('defines the strict security headers for all paths /*', () => {
    const content = readFileSync(HEADERS_PATH, 'utf-8');
    const sections = parseHeaders(content);
    const globalHeaders = sections.get('/*');
    expect(globalHeaders).toBeDefined();

    expect(globalHeaders?.get('strict-transport-security')).toBe(
      'max-age=31536000; includeSubDomains',
    );
    expect(globalHeaders?.get('x-content-type-options')).toBe('nosniff');
    expect(globalHeaders?.get('referrer-policy')).toBe('no-referrer');
    expect(globalHeaders?.get('cross-origin-opener-policy')).toBe('same-origin');
    expect(globalHeaders?.get('permissions-policy')).toBe(
      'camera=(), microphone=(), geolocation=(), interest-cohort=()',
    );

    const csp = globalHeaders?.get('content-security-policy');
    expect(csp).toBeDefined();
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("style-src 'self'");
    expect(csp).toContain("img-src 'self' data: blob:");
    expect(csp).toContain("font-src 'self'");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("worker-src 'self'");
    expect(csp).toContain("manifest-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'none'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain('upgrade-insecure-requests');
  });
});
