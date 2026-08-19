import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '../../state/auth/AuthContext';

const publicRoutes = ['/login', '/auth/callback'];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { profile, loading } = useAuth();
  const path = router.asPath.split('?')[0];
  const isPublic = publicRoutes.includes(path);

  useEffect(() => {
    if (!loading && !isPublic && !profile) {
      void router.replace({ pathname: '/login', query: { returnUrl: router.asPath } });
    }
    if (!loading && path === '/login' && profile) {
      const returnUrl = typeof router.query.returnUrl === 'string' ? router.query.returnUrl : '/';
      void router.replace(returnUrl);
    }
  }, [isPublic, loading, path, profile, router]);

  if (loading && !isPublic) return null;
  if (!isPublic && !profile) return null;
  return <>{children}</>;
}
