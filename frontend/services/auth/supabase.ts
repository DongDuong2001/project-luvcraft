import { createClient, type SupabaseClient } from '@supabase/supabase-js';

let client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (client) return client;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error('Supabase frontend configuration is missing');
  }
  // Session handling is explicit rather than implicit:
  // - persistSession keeps the Supabase session in storage across reloads so a
  //   returning tab can re-establish the backend cookie without a fresh login.
  // - autoRefreshToken silently rotates the Supabase access token before it
  //   expires; AuthContext listens for TOKEN_REFRESHED and re-exchanges the new
  //   token for a freshly minted httpOnly backend cookie (backend max_age 1h).
  // - detectSessionInUrl completes the OAuth redirect handled by /auth/callback.
  client = createClient(url, anonKey, {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    },
  });
  return client;
}
