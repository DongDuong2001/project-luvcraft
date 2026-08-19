import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { getSupabaseClient } from '../../services/auth/supabase';

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export default function AuthCallback() {
  const router = useRouter();

  useEffect(() => {
    void (async () => {
      try {
        const { data, error } = await getSupabaseClient().auth.getSession();
        if (error || !data.session) throw error || new Error('No OAuth session returned');
        const response = await fetch(`${API_BASE_URL}/api/v1/auth/session`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ access_token: data.session.access_token }),
        });
        if (!response.ok) throw new Error('Backend session exchange failed');
        await router.replace('/');
      } catch {
        await router.replace('/login?error=auth_failed');
      }
    })();
  }, [router]);

  return <div className="min-h-screen bg-app-bg flex items-center justify-center text-slate-300">Completing sign in…</div>;
}
