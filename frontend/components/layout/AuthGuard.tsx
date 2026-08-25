import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '../../state/auth/AuthContext';
import { sanitizeReturnUrl } from '../../utils/url';

const PUBLIC_ROUTES = new Set(['/login', '/auth/callback']);

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { profile, loading } = useAuth();
  const path = router.asPath.split('?')[0];
  const isPublic = PUBLIC_ROUTES.has(path);

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
