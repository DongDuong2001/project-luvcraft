import { describe, it, expect } from 'vitest';
import { sanitizeReturnUrl } from '../utils/url';

describe('sanitizeReturnUrl', () => {
  it('allows safe, relative path destinations', () => {
    expect(sanitizeReturnUrl('/dashboard?tab=trend')).toBe('/dashboard?tab=trend');
    expect(sanitizeReturnUrl('/dashboard')).toBe('/dashboard');
    expect(sanitizeReturnUrl('/reports/123#section')).toBe('/reports/123#section');
    expect(sanitizeReturnUrl('/search?q=kpop+trends&page=2')).toBe('/search?q=kpop+trends&page=2');
  });

  it('rejects absolute URLs with external origins', () => {
    expect(sanitizeReturnUrl('https://evil.com')).toBe('/');
    expect(sanitizeReturnUrl('http://evil.com/dashboard')).toBe('/');
    expect(sanitizeReturnUrl('https://evil.com/login?returnUrl=/dashboard')).toBe('/');
    expect(sanitizeReturnUrl('http://localhost:3000/')).toBe('/');
  });

  it('rejects protocol-relative URLs', () => {
    expect(sanitizeReturnUrl('//evil.com')).toBe('/');
    expect(sanitizeReturnUrl('//evil.com/path')).toBe('/');
    expect(sanitizeReturnUrl('///evil.com')).toBe('/');
  });

  it('rejects backslash-based normalization bypasses', () => {
    expect(sanitizeReturnUrl('/\\evil.com')).toBe('/');
    expect(sanitizeReturnUrl('\\evil.com')).toBe('/');
    expect(sanitizeReturnUrl('/\\/evil.com')).toBe('/');
    expect(sanitizeReturnUrl('/dashboard\\evil.com')).toBe('/');
    expect(sanitizeReturnUrl('/path\\..\\evil.com')).toBe('/');
  });

  it('rejects non-http dangerous protocols', () => {
    expect(sanitizeReturnUrl('javascript:alert(1)')).toBe('/');
    expect(sanitizeReturnUrl('data:text/html,<script>alert(1)</script>')).toBe('/');
    expect(sanitizeReturnUrl('vbscript:msgbox(1)')).toBe('/');
  });

  it('rejects non-string and malformed inputs with default or custom fallback', () => {
    expect(sanitizeReturnUrl(null)).toBe('/');
    expect(sanitizeReturnUrl(undefined)).toBe('/');
    expect(sanitizeReturnUrl(123)).toBe('/');
    expect(sanitizeReturnUrl({})).toBe('/');
    expect(sanitizeReturnUrl(['/dashboard'])).toBe('/');
    expect(sanitizeReturnUrl('')).toBe('/');
    expect(sanitizeReturnUrl('   ')).toBe('/');
    expect(sanitizeReturnUrl('invalid-path')).toBe('/');

    // Custom fallback support
    expect(sanitizeReturnUrl('https://evil.com', '/fallback')).toBe('/fallback');
    expect(sanitizeReturnUrl(null, '/custom')).toBe('/custom');
  });
});
