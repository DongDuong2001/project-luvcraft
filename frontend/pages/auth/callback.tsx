import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseClient } from '../../services/auth/supabase';
import { exchangeSession, OAUTH_RETURN_URL_KEY } from '../../services/auth/session';
import { sanitizeReturnUrl } from '../../utils/url';
import { useAuth } from '../../state/auth/AuthContext';

export default function AuthCallback() {
  const router = useRouter();
  const { refreshProfile } = useAuth();

  useEffect(() => {
    void (async () => {
      try {
        const { data, error } = await getSupabaseClient().auth.getSession();
        if (error || !data.session) throw error || new Error('No OAuth session returned');

        // Exchange Supabase access token for httpOnly backend session cookie
        await exchangeSession(data.session.access_token);
        await refreshProfile();

        // Restore destination URL if saved before OAuth redirect
        let targetUrl: string | null = null;
        if (typeof window !== 'undefined') {
          try {
            targetUrl = sessionStorage.getItem(OAUTH_RETURN_URL_KEY);
            sessionStorage.removeItem(OAUTH_RETURN_URL_KEY);
          } catch {
            // sessionStorage unavailable
          }
        }

        const destination = sanitizeReturnUrl(targetUrl);
        await router.replace(destination);
      } catch (caught) {
        console.error('[auth] OAuth callback exchange failed', caught);
        await router.replace('/login?error=auth_failed');
      }
    })();
  }, [refreshProfile, router]);

  return <div className="min-h-screen bg-app-bg flex items-center justify-center text-slate-300">Completing sign in…</div>;
}

