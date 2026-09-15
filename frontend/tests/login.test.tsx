import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import Login from '../pages/login';
import * as authContextModule from '../state/auth/AuthContext';
import * as nextRouter from 'next/router';
import type { NextRouter } from 'next/router';

describe('Login Page', () => {
  it('toggles password visibility when the eye button is clicked', () => {
    vi.spyOn(nextRouter, 'useRouter').mockReturnValue({
      asPath: '/login',
      pathname: '/login',
      query: {},
      push: vi.fn(),
    } as unknown as NextRouter);

    vi.spyOn(authContextModule, 'useAuth').mockReturnValue({
      profile: null,
      loading: false,
      refreshProfile: vi.fn(),
      signInWithOAuth: vi.fn(),
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    } as unknown as authContextModule.AuthContextValue);

    render(<Login />);

    const passwordInput = screen.getByLabelText('Password') as HTMLInputElement;
    expect(passwordInput.type).toBe('password');

    const toggleButton = screen.getByLabelText('Show password');
    expect(toggleButton).toBeDefined();
    fireEvent.click(toggleButton);

    expect(passwordInput.type).toBe('text');
    expect(screen.getByLabelText('Hide password')).toBeDefined();

    fireEvent.click(screen.getByLabelText('Hide password'));
    expect(passwordInput.type).toBe('password');
    expect(screen.getByLabelText('Show password')).toBeDefined();
  });
});
