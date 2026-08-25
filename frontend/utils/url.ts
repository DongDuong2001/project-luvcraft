/**
 * Validates and sanitizes a returnUrl parameter to prevent Open Redirect vulnerabilities (CWE-601).
 *
 * Requirements:
 * - Must be a string.
 * - Must start with a single '/' and cannot start with '//' or '/\\'.
 * - Must not contain any backslashes ('\\') anywhere in the string to prevent browser normalization bypasses (e.g. '/\\evil.com').
 * - Must not contain control characters or whitespace.
 * - Must resolve to the same origin when parsed as a relative URL.
 * - Disallows dangerous protocols (e.g. 'javascript:', 'data:').
 *
 * @param value The candidate URL to sanitize.
 * @param fallback The fallback path to return if validation fails (defaults to '/').
 * @returns A safe relative path (e.g. '/dashboard?tab=trend') or the fallback.
 */
export function sanitizeReturnUrl(value: unknown, fallback = '/'): string {
  if (typeof value !== 'string') return fallback;

  const trimmed = value.trim();
  if (!trimmed) return fallback;

  // Disallow any backslashes to block normalization tricks (e.g. '/\\evil.com' -> 'https://evil.com')
  if (trimmed.includes('\\')) return fallback;

  // Must begin with a single '/' and not protocol-relative '//'
  if (!trimmed.startsWith('/') || trimmed.startsWith('//')) return fallback;

  // Disallow control characters
  if (/[\u0000-\u001F\u007F]/.test(trimmed)) return fallback;

  // Parse against a dummy base origin to verify resolution
  try {
    const baseOrigin = 'https://localhost';
    const parsed = new URL(trimmed, baseOrigin);

    // Verify the origin didn't change
    if (parsed.origin !== baseOrigin) return fallback;

    // Verify the protocol is HTTP/HTTPS
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return fallback;

    // Reconstruct the relative path with search and hash
    const relativePath = `${parsed.pathname}${parsed.search}${parsed.hash}`;

    if (!relativePath.startsWith('/') || relativePath.startsWith('//') || relativePath.includes('\\')) {
      return fallback;
    }

    return relativePath;
  } catch {
    return fallback;
  }
}
