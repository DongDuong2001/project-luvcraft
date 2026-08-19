import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getSupabaseClient } from '../../services/auth/supabase';

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export type UserRole = 'admin' | 'analyst' | 'client' | 'viewer';

export interface AuthProfile {
  user_id: string;
  email: string | null;
  role: UserRole;
  brand_id: string | null;
  is_active: boolean;
  auth_method: 'cookie' | 'bearer' | 'api_key';
}

interface AuthContextValue {
  profile: AuthProfile | null;
  loading: boolean;
  error: string | null;
  refreshProfile: () => Promise<AuthProfile | null>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signInWithOAuth: (provider: 'google' | 'azure') => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function fetchProfile(): Promise<AuthProfile | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    credentials: 'include',
  });
  if (response.status === 401 || response.status === 403) return null;
  if (!response.ok) throw new Error('Unable to load your access profile');
  return response.json() as Promise<AuthProfile>;
}

async function exchangeSession(accessToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/session`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken }),
  });
  if (!response.ok) throw new Error('Unable to establish backend session');
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          await exchangeSession(data.session.access_token);
          const nextProfile = await fetchProfile();
          if (active) setProfile(nextProfile);
        }
      } catch {
        // Missing local Supabase configuration is valid for backend dev-login.
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
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

  const signInWithOAuth = useCallback(async (provider: 'google' | 'azure') => {
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
