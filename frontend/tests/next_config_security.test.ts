import { afterEach, describe, expect, it, vi } from 'vitest';

const originalNodeEnv = process.env.NODE_ENV;
const originalHttpsOnly = process.env.HTTPS_ONLY;

async function loadHeaders(httpsOnly: boolean) {
  vi.resetModules();
  process.env.NODE_ENV = 'production';
  process.env.HTTPS_ONLY = String(httpsOnly);
  const config = (await import('../next.config.js')).default;
  const rules = await config.headers();
  return rules[0].headers as Array<{ key: string; value: string }>;
}

afterEach(() => {
  vi.resetModules();
  process.env.NODE_ENV = originalNodeEnv;
  if (originalHttpsOnly === undefined) delete process.env.HTTPS_ONLY;
  else process.env.HTTPS_ONLY = originalHttpsOnly;
});

describe('frontend transport security headers', () => {
  it('does not force HTTPS for the local production Docker build', async () => {
    const headers = await loadHeaders(false);
    const csp = headers.find(({ key }) => key === 'Content-Security-Policy')?.value;

    expect(csp).not.toContain('upgrade-insecure-requests');
    expect(headers.some(({ key }) => key === 'Strict-Transport-Security')).toBe(false);
  });

  it('retains HTTPS-only directives for HTTPS deployments', async () => {
    const headers = await loadHeaders(true);
    const csp = headers.find(({ key }) => key === 'Content-Security-Policy')?.value;

    expect(csp).toContain('upgrade-insecure-requests');
    expect(headers).toContainEqual({
      key: 'Strict-Transport-Security',
      value: 'max-age=63072000; includeSubDomains; preload',
    });
  });
});
