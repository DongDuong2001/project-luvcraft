import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '../../state/auth/AuthContext';

const publicRoutes = ['/login', '/auth/callback'];

/**
 * Only same-origin, path-relative destinations are accepted. Anything else
 * (absolute URLs, protocol-relative "//evil.com") falls back to the app root so
 * a crafted returnUrl cannot be used as an open redirect.
 */
function sanitizeReturnUrl(value: unknown): string {
  if (typeof value !== 'string') return '/';
  if (!value.startsWith('/') || value.startsWith('//')) return '/';
  return value;
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { profile, loading } = useAuth();
  const path = router.asPath.split('?')[0];
  const isPublic = publicRoutes.includes(path) || path.startsWith('/auth/');

  useEffect(() => {
    if (!loading && !isPublic && !profile) {
      void router.replace({ pathname: '/login', query: { returnUrl: router.asPath } });
    }
    if (!loading && path === '/login' && profile) {
      void router.replace(sanitizeReturnUrl(router.query.returnUrl));
    }
  }, [isPublic, loading, path, profile, router]);

  if (loading && !isPublic) return null;
  if (!isPublic && !profile) return null;
  return <>{children}</>;
}
