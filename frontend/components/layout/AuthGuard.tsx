import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';

const publicRoutes = ['/login'];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    authCheck(router.asPath);

    const hideContent = () => setAuthorized(false);
    router.events.on('routeChangeStart', hideContent);
    // on route change complete - run auth check
    router.events.on('routeChangeComplete', authCheck);

    return () => {
      router.events.off('routeChangeStart', hideContent);
      router.events.off('routeChangeComplete', authCheck);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.asPath, router.events]);

  function authCheck(url: string) {
    // In a real HttpOnly cookie setup, checking token might involve an API call (e.g. /api/me). 
    // For now we assume API client handles 401s and redirects to login, 
    // or we look for a frontend "isLoggedIn" flag. 
    // Since we are transitioning to httpOnly, we might not have a local token.
    // If you haven't fully moved to HttpOnly yet, you can still check localStorage or generic auth state.
    const path = url.split('?')[0];
    
    // For transition: Check local storage OR assume backend verify based on cookies.
    // We will do a generic check here. We can just rely on the API calls firing 401, but doing a basic check is good too.
    const hasToken = typeof window !== 'undefined' ? !!localStorage.getItem('luvcraft_auth_token') : false;

    // If using strict HTTP-only cookies, you might remove this hasToken check and rely on an API request 
    // to validate the session. For this step, we'll keep the logic generic.
    if (!publicRoutes.includes(path) && !hasToken) {
      setAuthorized(false);
      router.push({
        pathname: '/login',
        query: { returnUrl: router.asPath }
      });
    } else {
      setAuthorized(true);
    }
  }

  return authorized ? <>{children}</> : null;
}
