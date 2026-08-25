import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Session } from '@supabase/supabase-js';
import { getSupabaseClient } from '../../services/auth/supabase';
import {
  API_BASE_URL,
  OAUTH_RETURN_URL_KEY,
  type AuthProfile,
  type UserRole,
  fetchProfile,
  exchangeSession,
} from '../../services/auth/session';
import { sanitizeReturnUrl } from '../../utils/url';

export type { AuthProfile, UserRole };

/** Minimum gap between tab-focus session revalidations. */
export const REVALIDATE_INTERVAL_MS = 60_000;

export interface AuthContextValue {
  profile: AuthProfile | null;
  loading: boolean;
  error: string | null;
  refreshProfile: () => Promise<AuthProfile | null>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signInWithOAuth: (provider: 'google' | 'azure', returnUrl?: string | string[]) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Debounce marker for tab-focus revalidation; stamped on mount inside the
  // effect so no impure call happens during render.
  const lastRevalidatedAtRef = useRef(0);

  const refreshProfile = useCallback(async () => {
    try {
      const nextProfile = await fetchProfile();
      setProfile(nextProfile);
      return nextProfile;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Authentication failed');
      setProfile(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    // The mount bootstrap below counts as the first revalidation.
    lastRevalidatedAtRef.current = Date.now();

    const reportError = (context: string, caught: unknown) => {
      console.error(`[auth] ${context}`, caught);
      if (active) setError(caught instanceof Error ? caught.message : 'Authentication failed');
    };

    /** Re-mint the httpOnly backend cookie from a live Supabase session, then reload the profile. */
    const syncFromSession = async (session: Session) => {
      await exchangeSession(session.access_token);
      const nextProfile = await fetchProfile();
      if (!active) return;
      setProfile(nextProfile);
      setError(null);
    };

    void (async () => {
      const cookieProfile = await fetchProfile().catch(() => null);
      if (cookieProfile) {
        if (active) setProfile(cookieProfile);
        if (active) setLoading(false);
        return;
      }

      try {
        const { data } = await getSupabaseClient().auth.getSession();
        if (data.session) {
          await syncFromSession(data.session);
        }
      } catch {
        // Missing local Supabase configuration is valid for backend dev-login.
      } finally {
        if (active) setLoading(false);
      }
    })();

    // The backend cookie is short-lived (1h). Supabase silently rotates its own
    // access token, so every rotation must be re-exchanged for a fresh cookie —
    // otherwise the cookie dies mid-session and the next API call 401s.
    let unsubscribe: (() => void) | null = null;
    let supabaseAvailable = true;
    try {
      const { data } = getSupabaseClient().auth.onAuthStateChange((event, session) => {
        if (!active) return;
        if (event === 'SIGNED_OUT') {
          setProfile(null);
          return;
        }
        if ((event === 'TOKEN_REFRESHED' || event === 'SIGNED_IN') && session) {
          void syncFromSession(session).catch((caught) =>
            reportError(`failed to re-exchange supabase session after ${event}`, caught),
          );
        }
      });
      unsubscribe = () => data.subscription.unsubscribe();
    } catch (caught) {
      // Supabase is not configured (backend dev-login path). Cookie-only
      // sessions keep working until the cookie expires; just skip the listener.
      supabaseAvailable = false;
      console.warn('[auth] supabase client unavailable, skipping auth state subscription', caught);
    }

    // Revalidate when the user returns to the tab: a backgrounded tab can miss a
    // rotation, and the cookie may have expired while it was hidden.
    const revalidate = async () => {
      const now = Date.now();
      if (now - lastRevalidatedAtRef.current < REVALIDATE_INTERVAL_MS) return;
      lastRevalidatedAtRef.current = now;
      try {
        const nextProfile = await fetchProfile();
        if (nextProfile) {
          if (active) setProfile(nextProfile);
          return;
        }
        if (!supabaseAvailable) {
          if (active) setProfile(null);
          return;
        }
        const { data } = await getSupabaseClient().auth.getSession();
        if (!data.session) {
          if (active) setProfile(null);
          return;
        }
        await syncFromSession(data.session);
      } catch (caught) {
        reportError('failed to revalidate session on tab focus', caught);
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return;
      void revalidate();
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      active = false;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      unsubscribe?.();
    };
  }, []);

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    setError(null);
    const { data, error: signInError } = await getSupabaseClient().auth.signInWithPassword({
      email,
      password,
    });
    if (signInError || !data.session) throw signInError || new Error('No session returned');
    await exchangeSession(data.session.access_token);
    const nextProfile = await fetchProfile();
    setProfile(nextProfile);
  }, []);

  const signInWithOAuth = useCallback(async (provider: 'google' | 'azure', targetReturnUrl?: string | string[]) => {
    if (typeof window !== 'undefined') {
      try {
        sessionStorage.removeItem(OAUTH_RETURN_URL_KEY);
        const sanitized = sanitizeReturnUrl(targetReturnUrl);
        if (sanitized !== '/') {
          sessionStorage.setItem(OAUTH_RETURN_URL_KEY, sanitized);
        }
      } catch {
        // sessionStorage unavailable
      }
    }
    const { error: oauthError } = await getSupabaseClient().auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
        ...(provider === 'azure' ? { scopes: 'email' } : {}),
      },
    });
    if (oauthError) throw oauthError;
  }, []);

  const signOut = useCallback(async () => {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    try {
      await getSupabaseClient().auth.signOut();
    } catch {
      // Backend dev-login does not require a configured Supabase client.
    }
    setProfile(null);
  }, []);

  const value = useMemo(
    () => ({ profile, loading, error, refreshProfile, signInWithPassword, signInWithOAuth, signOut }),
    [profile, loading, error, refreshProfile, signInWithPassword, signInWithOAuth, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
