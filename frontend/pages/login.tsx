import React, { useState } from 'react';
import { useRouter } from 'next/router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import Head from 'next/head';
import Image from 'next/image';
import { useAuth } from '../state/auth/AuthContext';
import { sanitizeReturnUrl } from '../utils/url';

export default function Login() {
  const router = useRouter();
  const { refreshProfile, signInWithOAuth, signInWithPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const finishLogin = async () => {
    await router.push(sanitizeReturnUrl(router.query.returnUrl));
  };

  const handlePasswordLogin = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await signInWithPassword(email, password);
      await finishLogin();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to sign in');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDevBypass = async () => {
    setError(null);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/auth/dev-login`,
        {
          method: 'POST',
          credentials: 'include',
        }
      );
      if (!response.ok) {
        const message = `Developer bypass failed with status ${response.status}`;
        console.error(message);
        setError(message);
        return;
      }
      await refreshProfile();
      await finishLogin();
    } catch (err) {
      console.error('Dev bypass error:', err);
      setError(err instanceof Error ? err.message : 'Developer bypass failed');
    }
  };

  return (
    <div className="min-h-screen bg-app-bg flex items-center justify-center p-4">
      <Head>
        <title>Login - Company Portal</title>
      </Head>

      <Card className="w-full max-w-md bg-app-surface border-app-line shadow-2xl">
        <CardHeader className="space-y-3 pb-6">
          <div className="flex justify-center mb-2 mt-2">
            <div className="relative h-10 w-[220px] overflow-hidden md:h-12">
              <Image
                src="/Project_Pluto.avif"
                alt="Company Logo"
                fill
                priority
                sizes="220px"
                className="object-contain drop-shadow-sm"
              />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold text-center text-white">Employee Login</CardTitle>
          <CardDescription className="text-center text-slate-400">
            Internal Secure Access Portal
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          
          <div className="space-y-4">
            {/* Direct SSO Buttons */}
            <Button onClick={() => void signInWithOAuth('google', router.query.returnUrl)} className="w-full h-11 bg-white hover:bg-slate-100 text-slate-900 border border-slate-200">
              <div className="flex items-center justify-center gap-2">
                <span className="font-bold text-blue-600 text-lg">G</span>
                <span className="font-semibold">Continue with Google Workspace</span>
              </div>
            </Button>
            
            <Button onClick={() => void signInWithOAuth('azure', router.query.returnUrl)} className="w-full h-11 bg-[#0078D4] hover:bg-[#006cbd] text-white">
              <div className="flex items-center justify-center gap-2">
                <span className="font-bold text-white text-lg">M</span>
                <span className="font-semibold">Continue with Microsoft Entra</span>
              </div>
            </Button>
          </div>

          <div className="relative py-2">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-app-line" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-app-surface px-2 text-slate-500 font-medium">Or Use Custom SSO</span>
            </div>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-slate-300">
                Enterprise Email
              </label>
              <Input 
                id="email" 
                type="email" 
                placeholder="name@company.com" 
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="bg-app-bg border-app-line text-slate-200 focus-visible:ring-blue-500 h-11" 
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-slate-300">
                Password
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="bg-app-bg border-app-line text-slate-200 focus-visible:ring-blue-500 h-11"
              />
            </div>
            <Button
              onClick={() => void handlePasswordLogin()}
              disabled={submitting || !email || !password}
              className="w-full h-11 bg-[#2573ff] hover:bg-[#194daa] text-white font-medium"
            >
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
            {error && <p className="text-sm text-rose-400" role="alert">{error}</p>}
          </div>

          <div className="mt-8 p-4 bg-blue-500/10 border border-blue-500/20 rounded-lg text-center">
            <p className="text-xs text-blue-300 leading-relaxed">
              Upon successful authentication via your Identity Provider, a secure employee profile will automatically be created/updated for this session.
            </p>
          </div>

          {/* Development / Mock Bypass */}
          {process.env.NODE_ENV === 'development' && (
            <div className="pt-4 border-t border-app-line mt-4">
              <Button 
                onClick={handleDevBypass}
                variant="outline"
                className="w-full h-11 border-dashed border-amber-500/50 text-amber-500 hover:bg-amber-500/10 hover:text-amber-400"
              >
                🛠 Developer Mode: Bypass Login
              </Button>
            </div>
          )}

        </CardContent>
      </Card>
    </div>
  );
}
