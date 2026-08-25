export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const OAUTH_RETURN_URL_KEY = 'pluto_oauth_return_url';

export type UserRole = 'admin' | 'analyst' | 'client' | 'viewer';

export interface AuthProfile {
  user_id: string;
  email: string | null;
  role: UserRole;
  brand_id: string | null;
  is_active: boolean;
  auth_method: 'cookie' | 'bearer' | 'api_key';
}

/**
 * Loads the current authenticated user profile via cookie credentials.
 */
export async function fetchProfile(): Promise<AuthProfile | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    credentials: 'include',
  });
  if (response.status === 401 || response.status === 403) return null;
  if (!response.ok) throw new Error('Unable to load your access profile');
  return response.json() as Promise<AuthProfile>;
}

/**
 * Exchanges a Supabase access token for a freshly minted httpOnly backend session cookie.
 */
export async function exchangeSession(accessToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/session`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ access_token: accessToken }),
  });
  if (!response.ok) throw new Error('Unable to establish backend session');
}

