import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth, REVALIDATE_INTERVAL_MS } from '../state/auth/AuthContext';
import * as supabaseModule from '../services/auth/supabase';
import { OAUTH_RETURN_URL_KEY } from '../services/auth/session';
import type { Session, AuthChangeEvent } from '@supabase/supabase-js';

// Helper component to inspect AuthContext state
function TestConsumer({ onState }: { onState: (auth: ReturnType<typeof useAuth>) => void }) {
  const auth = useAuth();
  React.useEffect(() => {
    onState(auth);
  }, [auth, onState]);
  return <div>{auth.loading ? 'loading' : auth.profile ? auth.profile.email : 'unauthenticated'}</div>;
}

describe('AuthContext and Session Lifecycle', () => {
  let authStateCallback: ((event: AuthChangeEvent, session: Session | null) => void) | null = null;
  let unsubscribeMock: ReturnType<typeof vi.fn>;
  let mockSupabaseClient: {
    auth: {
      getSession: ReturnType<typeof vi.fn>;
      onAuthStateChange: ReturnType<typeof vi.fn>;
      signInWithPassword: ReturnType<typeof vi.fn>;
      signInWithOAuth: ReturnType<typeof vi.fn>;
      signOut: ReturnType<typeof vi.fn>;
    };
  };

  beforeEach(() => {
    authStateCallback = null;
    unsubscribeMock = vi.fn();

    mockSupabaseClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
        onAuthStateChange: vi.fn().mockImplementation((cb) => {
          authStateCallback = cb;
          return { data: { subscription: { unsubscribe: unsubscribeMock } } };
        }),
        signInWithPassword: vi.fn().mockResolvedValue({ data: { session: { access_token: 'pw-token' } }, error: null }),
        signInWithOAuth: vi.fn().mockResolvedValue({ data: { provider: 'google', url: 'https://oauth.google.com' }, error: null }),
        signOut: vi.fn().mockResolvedValue({ error: null }),
      },
    };

    vi.spyOn(supabaseModule, 'getSupabaseClient').mockReturnValue(mockSupabaseClient as unknown as ReturnType<typeof supabaseModule.getSupabaseClient>);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('recovers session when backend cookie is expired but valid Supabase session exists', async () => {
    const mockSession = { access_token: 'valid-supabase-token' } as Session;
    mockSupabaseClient.auth.getSession.mockResolvedValueOnce({
      data: { session: mockSession },
      error: null,
    });

    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/me')) {
        // Initial cookie check fails (expired cookie)
        if (fetchMock.mock.calls.filter((c: unknown[]) => String(c[0]).endsWith('/api/v1/auth/me')).length === 1) {
          return { status: 401, ok: false } as Response;
        }
        // After session exchange, me returns valid profile
        return {
          status: 200,
          ok: true,
          json: async () => ({
            user_id: 'user-123',
            email: 'analyst@pluto.studio',
            role: 'analyst',
            brand_id: null,
            is_active: true,
            auth_method: 'cookie',
          }),
        } as unknown as Response;
      }
      if (url.endsWith('/api/v1/auth/session')) {
        return { status: 200, ok: true, json: async () => ({ status: 'ok' }) } as unknown as Response;
      }
      return { status: 404, ok: false } as Response;
    });

    globalThis.fetch = fetchMock;

    let capturedAuth: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <TestConsumer onState={(auth) => { capturedAuth = auth; }} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(capturedAuth?.loading).toBe(false);
      expect(capturedAuth?.profile?.email).toBe('analyst@pluto.studio');
    });

    const sessionExchangeCall = fetchMock.mock.calls.find((c: unknown[]) => String(c[0]).endsWith('/api/v1/auth/session'));
    expect(sessionExchangeCall).toBeDefined();
    expect(JSON.parse(String((sessionExchangeCall?.[1] as RequestInit)?.body))).toEqual({ access_token: 'valid-supabase-token' });
  });

  it('re-exchanges backend cookie on TOKEN_REFRESHED event from Supabase', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/me')) {
        if (fetchMock.mock.calls.filter((c: unknown[]) => String(c[0]).endsWith('/api/v1/auth/me')).length === 1) {
          return { status: 401, ok: false } as Response;
        }
        return {
          status: 200,
          ok: true,
          json: async () => ({
            user_id: 'user-123',
            email: 'refreshed@pluto.studio',
            role: 'admin',
            brand_id: null,
            is_active: true,
            auth_method: 'cookie',
          }),
        } as unknown as Response;
      }
      if (url.endsWith('/api/v1/auth/session')) {
        return { status: 200, ok: true, json: async () => ({ status: 'ok' }) } as unknown as Response;
      }
      return { status: 404, ok: false } as Response;
    });

    globalThis.fetch = fetchMock;

    let capturedAuth: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <TestConsumer onState={(auth) => { capturedAuth = auth; }} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(capturedAuth?.loading).toBe(false);
      expect(capturedAuth?.profile).toBeNull();
    });

    expect(authStateCallback).toBeTypeOf('function');
    await act(async () => {
      authStateCallback!('TOKEN_REFRESHED', { access_token: 'new-rotated-token' } as Session);
    });

    await waitFor(() => {
      expect(capturedAuth?.profile?.email).toBe('refreshed@pluto.studio');
    });

    const sessionExchangeCall = fetchMock.mock.calls.find(
      (c: unknown[]) => String(c[0]).endsWith('/api/v1/auth/session') && String((c[1] as RequestInit)?.body).includes('new-rotated-token')
    );
    expect(sessionExchangeCall).toBeDefined();
  });

  it('clears authenticated profile on SIGNED_OUT event', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/me')) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            user_id: 'user-123',
            email: 'active@pluto.studio',
            role: 'viewer',
            brand_id: null,
            is_active: true,
            auth_method: 'cookie',
          }),
        } as unknown as Response;
      }
      return { status: 404, ok: false } as Response;
    });

    globalThis.fetch = fetchMock;

    let capturedAuth: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <TestConsumer onState={(auth) => { capturedAuth = auth; }} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(capturedAuth?.profile?.email).toBe('active@pluto.studio');
    });

    await act(async () => {
      authStateCallback!('SIGNED_OUT', null);
    });

    await waitFor(() => {
      expect(capturedAuth?.profile).toBeNull();
    });
  });

  it('respects debounce interval on tab focus (visibilitychange)', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/me')) {
        return {
          status: 200,
          ok: true,
          json: async () => ({
            user_id: 'user-123',
            email: 'debounced@pluto.studio',
            role: 'analyst',
            brand_id: null,
            is_active: true,
            auth_method: 'cookie',
          }),
        } as unknown as Response;
      }
      return { status: 404, ok: false } as Response;
    });

    globalThis.fetch = fetchMock;

    render(
      <AuthProvider>
        <TestConsumer onState={() => {}} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const initialFetchCount = fetchMock.mock.calls.length;

    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    expect(fetchMock.mock.calls.length).toBe(initialFetchCount);

    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + REVALIDATE_INTERVAL_MS + 1000);

    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialFetchCount);
    });
  });

  it('persists sanitized returnUrl in sessionStorage during signInWithOAuth', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 401, ok: false } as Response);
    globalThis.fetch = fetchMock;

    let capturedAuth: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <TestConsumer onState={(auth) => { capturedAuth = auth; }} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(capturedAuth?.loading).toBe(false);
    });

    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');
    const removeItemSpy = vi.spyOn(Storage.prototype, 'removeItem');

    await act(async () => {
      await capturedAuth?.signInWithOAuth('google', '/dashboard?tab=geo');
    });

    expect(removeItemSpy).toHaveBeenCalledWith(OAUTH_RETURN_URL_KEY);
    expect(setItemSpy).toHaveBeenCalledWith(OAUTH_RETURN_URL_KEY, '/dashboard?tab=geo');
    expect(mockSupabaseClient.auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: 'google',
      options: expect.objectContaining({
        redirectTo: expect.stringContaining('/auth/callback'),
      }),
    });
  });

  it('clears stale returnUrl in sessionStorage when signInWithOAuth receives default or invalid URL', async () => {
    sessionStorage.setItem(OAUTH_RETURN_URL_KEY, '/stale-destination');
    const fetchMock = vi.fn().mockResolvedValue({ status: 401, ok: false } as Response);
    globalThis.fetch = fetchMock;

    let capturedAuth: ReturnType<typeof useAuth> | undefined;
    render(
      <AuthProvider>
        <TestConsumer onState={(auth) => { capturedAuth = auth; }} />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(capturedAuth?.loading).toBe(false);
    });

    // Call signInWithOAuth with default/malicious URL
    await act(async () => {
      await capturedAuth?.signInWithOAuth('google', 'https://evil.com');
    });

    // The stale key was cleared and not replaced by evil.com
    expect(sessionStorage.getItem(OAUTH_RETURN_URL_KEY)).toBeNull();

    // Call again with undefined/empty URL
    sessionStorage.setItem(OAUTH_RETURN_URL_KEY, '/another-stale');
    await act(async () => {
      await capturedAuth?.signInWithOAuth('google', undefined);
    });

    expect(sessionStorage.getItem(OAUTH_RETURN_URL_KEY)).toBeNull();
  });
});

