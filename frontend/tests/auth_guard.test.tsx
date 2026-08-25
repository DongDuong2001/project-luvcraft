import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { AuthGuard } from '../components/layout/AuthGuard';
import * as authContextModule from '../state/auth/AuthContext';
import * as nextRouter from 'next/router';
import type { NextRouter } from 'next/router';

describe('AuthGuard', () => {
  let routerReplace: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    routerReplace = vi.fn();
  });

  it('allows access to explicit public routes (/login, /auth/callback) when unauthenticated', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/login',
      pathname: '/login',
      query: {},
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: null,
      loading: false,
    } as unknown as authContextModule.AuthContextValue);

    render(
      <AuthGuard>
        <div>Public Content</div>
      </AuthGuard>
    );

    expect(screen.getByText('Public Content')).toBeDefined();
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('redirects unauthenticated users on protected route to /login with returnUrl', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/dashboard?tab=geo',
      pathname: '/dashboard',
      query: { tab: 'geo' },
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: null,
      loading: false,
    } as unknown as authContextModule.AuthContextValue);

    render(
      <AuthGuard>
        <div>Protected Content</div>
      </AuthGuard>
    );

    expect(screen.queryByText('Protected Content')).toBeNull();
    expect(routerReplace).toHaveBeenCalledWith({
      pathname: '/login',
      query: { returnUrl: '/dashboard?tab=geo' },
    });
  });

  it('default-denies non-allowlisted /auth/* subroutes when unauthenticated', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/auth/session-settings',
      pathname: '/auth/session-settings',
      query: {},
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: null,
      loading: false,
    } as unknown as authContextModule.AuthContextValue);

    render(
      <AuthGuard>
        <div>Private Auth Subroute</div>
      </AuthGuard>
    );

    expect(screen.queryByText('Private Auth Subroute')).toBeNull();
    expect(routerReplace).toHaveBeenCalledWith({
      pathname: '/login',
      query: { returnUrl: '/auth/session-settings' },
    });
  });

  it('redirects authenticated user on /login to sanitized returnUrl', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/login',
      pathname: '/login',
      query: { returnUrl: '/dashboard?tab=trend' },
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: { user_id: '123', email: 'test@pluto.studio', role: 'analyst', brand_id: null, is_active: true, auth_method: 'cookie' },
      loading: false,
    } as unknown as authContextModule.AuthContextValue);

    render(
      <AuthGuard>
        <div>Login Page</div>
      </AuthGuard>
    );

    expect(routerReplace).toHaveBeenCalledWith('/dashboard?tab=trend');
  });

  it('sanitizes malicious returnUrl when redirecting authenticated user from /login', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/login',
      pathname: '/login',
      query: { returnUrl: 'https://evil.com' },
      replace: routerReplace,
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: { user_id: '123', email: 'test@pluto.studio', role: 'admin', brand_id: null, is_active: true, auth_method: 'cookie' },
      loading: false,
    } as unknown as authContextModule.AuthContextValue);

    render(
      <AuthGuard>
        <div>Login Page</div>
      </AuthGuard>
    );

    // Neutralized to '/'
    expect(routerReplace).toHaveBeenCalledWith('/');
  });
});
