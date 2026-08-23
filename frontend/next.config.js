
/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === 'production';
const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
let apiOrigin = 'http://localhost:8000';

try {
  apiOrigin = new URL(apiUrl).origin;
} catch {
  console.warn(`Invalid NEXT_PUBLIC_API_URL "${apiUrl}", using ${apiOrigin} for CSP`);
}

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || '';
const connectSources = ["'self'", apiOrigin];
let supabaseOrigin = '';

if (supabaseUrl) {
  try {
    const parsedSupabaseUrl = new URL(supabaseUrl);
    supabaseOrigin = parsedSupabaseUrl.origin;
    connectSources.push(supabaseOrigin);
    const wsProtocol = parsedSupabaseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    connectSources.push(`${wsProtocol}//${parsedSupabaseUrl.host}`);
  } catch {
    console.warn(`Invalid NEXT_PUBLIC_SUPABASE_URL "${supabaseUrl}", skipping CSP addition`);
  }
}

const formActionSources = ["'self'"];
if (supabaseOrigin) {
  formActionSources.push(supabaseOrigin);
}

const cspHeader = `
  default-src 'self';
  script-src 'self' 'unsafe-eval' 'unsafe-inline';
  style-src 'self' 'unsafe-inline';
  img-src 'self' blob: data: https:;
  font-src 'self' data:;
  connect-src ${connectSources.join(' ')};
  object-src 'none';
  base-uri 'none';
  form-action ${formActionSources.join(' ')};
  frame-ancestors 'none';
  ${isProd ? 'upgrade-insecure-requests;' : ''}
`;
const securityHeaders = [
  {
    key: 'Content-Security-Policy',
    value: cspHeader.replace(/\n/g, ''),
  },
  {
    key: 'X-DNS-Prefetch-Control',
    value: 'on'
  },
  {
    key: 'X-XSS-Protection',
    value: '1; mode=block'
  },
  {
    key: 'X-Frame-Options',
    value: 'DENY'
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff'
  },
  {
    key: 'Referrer-Policy',
    value: 'strict-origin-when-cross-origin'
  }
];
if (isProd) {
  securityHeaders.push({
    key: 'Strict-Transport-Security',
    value: 'max-age=63072000; includeSubDomains; preload'
  });
}
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: securityHeaders,
      },
    ]
  },
}
module.exports = nextConfig
