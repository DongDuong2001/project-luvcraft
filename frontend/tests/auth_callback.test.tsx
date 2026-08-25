import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, waitFor } from '@testing-library/react';
import AuthCallback from '../pages/auth/callback';
import * as supabaseModule from '../services/auth/supabase';
import * as sessionModule from '../services/auth/session';
import * as authContextModule from '../state/auth/AuthContext';
import * as nextRouter from 'next/router';
import type { NextRouter } from 'next/router';

describe('AuthCallback Page', () => {
  let routerReplace: ReturnType<typeof vi.fn>;
  let refreshProfileMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    routerReplace = vi.fn();
    refreshProfileMock = vi.fn().mockResolvedValue({ user_id: '1', email: 'test@pluto.studio' });
    vi.spyOn(sessionModule, 'exchangeSession').mockResolvedValue(undefined);

    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      refreshProfile: refreshProfileMock,
    } as unknown as authContextModule.AuthContextValue);
  });

  it('exchanges Supabase session for backend cookie and navigates to restored returnUrl', async () => {
    sessionStorage.setItem(sessionModule.OAUTH_RETURN_URL_KEY, '/dashboard?tab=geo');

    const mockSupabaseClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'oauth-supabase-token' } },
          error: null,
        }),
      },
    };
    vi.spyOn(supabaseModule, 'getSupabaseClient').mockReturnValue(mockSupabaseClient as unknown as ReturnType<typeof supabaseModule.getSupabaseClient>);

    render(<AuthCallback />);

    await waitFor(() => {
      expect(sessionModule.exchangeSession).toHaveBeenCalledWith('oauth-supabase-token');
      expect(refreshProfileMock).toHaveBeenCalled();
      expect(routerReplace).toHaveBeenCalledWith('/dashboard?tab=geo');
    });

    expect(sessionStorage.getItem(sessionModule.OAUTH_RETURN_URL_KEY)).toBeNull();
  });

  it('sanitizes malicious returnUrl and falls back to / upon successful login', async () => {
    sessionStorage.setItem(sessionModule.OAUTH_RETURN_URL_KEY, 'https://evil.com');

    const mockSupabaseClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: 'oauth-supabase-token' } },
          error: null,
        }),
      },
    };
    vi.spyOn(supabaseModule, 'getSupabaseClient').mockReturnValue(mockSupabaseClient as unknown as ReturnType<typeof supabaseModule.getSupabaseClient>);

    render(<AuthCallback />);

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/');
    });
  });

  it('redirects to /login?error=auth_failed on OAuth exchange failure and clears sessionStorage', async () => {
    sessionStorage.setItem(sessionModule.OAUTH_RETURN_URL_KEY, '/stale-dest');

    const mockSupabaseClient = {
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: { session: null },
          error: new Error('OAuth provider error'),
        }),
      },
    };
    vi.spyOn(supabaseModule, 'getSupabaseClient').mockReturnValue(mockSupabaseClient as unknown as ReturnType<typeof supabaseModule.getSupabaseClient>);

    render(<AuthCallback />);

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/login?error=auth_failed');
    });

    expect(sessionStorage.getItem(sessionModule.OAUTH_RETURN_URL_KEY)).toBeNull();
  });
});
