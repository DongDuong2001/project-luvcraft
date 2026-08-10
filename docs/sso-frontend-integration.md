# Frontend Supabase Auth Integration Guide

## Overview
This guide shows how to integrate Supabase authentication with the Next.js frontend for Project Luvcraft.

## Prerequisites
- Supabase project configured with Google OAuth (or email/password)
- Backend API running on `http://localhost:8000`
- Environment variables configured

## Installation

```bash
cd frontend
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs
```

## Environment Configuration

Create `frontend/.env.local`:

```bash
# Supabase Client
NEXT_PUBLIC_SUPABASE_URL=https://svnndjisftzropetvisq.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Implementation

### 1. Create Supabase Client

`frontend/services/auth/supabase.ts`:

```typescript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

### 2. Create Auth Service

`frontend/services/auth/authService.ts`:

```typescript
import { supabase } from './supabase'
import type { User } from '@supabase/supabase-js'

export interface AuthState {
  user: User | null
  session: any | null
  loading: boolean
}

export const authService = {
  /**
   * Sign in with Google OAuth
   */
  async signInWithGoogle() {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
    
    if (error) throw error
    return data
  },

  /**
   * Sign in with email and password
   */
  async signInWithPassword(email: string, password: string) {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    
    if (error) throw error
    return data
  },

  /**
   * Sign out
   */
  async signOut() {
    const { error } = await supabase.auth.signOut()
    if (error) throw error
  },

  /**
   * Get current session
   */
  async getSession() {
    const { data, error } = await supabase.auth.getSession()
    if (error) throw error
    return data.session
  },

  /**
   * Get access token for API calls
   */
  async getAccessToken(): Promise<string | null> {
    const session = await this.getSession()
    return session?.access_token || null
  },

  /**
   * Listen to auth state changes
   */
  onAuthStateChange(callback: (event: string, session: any) => void) {
    return supabase.auth.onAuthStateChange(callback)
  },
}
```

### 3. Create API Client with Auth

`frontend/services/api/client.ts`:

```typescript
import { authService } from '../auth/authService'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export class APIClient {
  /**
   * Make authenticated API request
   */
  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    // Get access token
    const token = await authService.getAccessToken()
    
    // Add Authorization header
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    }
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    
    // Make request
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    })
    
    // Handle errors
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'API request failed')
    }
    
    return response.json()
  }

  // Convenience methods
  async get<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  async post<T>(endpoint: string, data: any) {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async put<T>(endpoint: string, data: any) {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async delete<T>(endpoint: string) {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }
}

export const apiClient = new APIClient()
```

### 4. Create Auth Context

`frontend/contexts/AuthContext.tsx`:

```typescript
import React, { createContext, useContext, useEffect, useState } from 'react'
import type { User } from '@supabase/supabase-js'
import { authService } from '@/services/auth/authService'

interface AuthContextType {
  user: User | null
  loading: boolean
  signInWithGoogle: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check active session
    authService.getSession().then((session) => {
      setUser(session?.user || null)
      setLoading(false)
    })

    // Listen for auth changes
    const { data: { subscription } } = authService.onAuthStateChange(
      (event, session) => {
        setUser(session?.user || null)
        setLoading(false)
      }
    )

    return () => subscription.unsubscribe()
  }, [])

  const handleSignInWithGoogle = async () => {
    try {
      await authService.signInWithGoogle()
    } catch (error) {
      console.error('Sign in error:', error)
    }
  }

  const handleSignOut = async () => {
    try {
      await authService.signOut()
      setUser(null)
    } catch (error) {
      console.error('Sign out error:', error)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        signInWithGoogle: handleSignInWithGoogle,
        signOut: handleSignOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
```

### 5. OAuth Callback Page

`frontend/pages/auth/callback.tsx`:

```typescript
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { supabase } from '@/services/auth/supabase'

export default function AuthCallback() {
  const router = useRouter()

  useEffect(() => {
    // Handle OAuth callback
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        // Successfully authenticated
        router.push('/')
      } else {
        // Authentication failed
        router.push('/login?error=auth_failed')
      }
    })
  }, [router])

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <h2 className="text-xl font-semibold mb-2">Completing sign in...</h2>
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
      </div>
    </div>
  )
}
```

### 6. Login Page

`frontend/pages/login.tsx`:

```typescript
import { useAuth } from '@/contexts/AuthContext'
import { useRouter } from 'next/router'
import { useEffect } from 'react'

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth()
  const router = useRouter()

  useEffect(() => {
    // Redirect if already logged in
    if (user && !loading) {
      router.push('/')
    }
  }, [user, loading, router])

  if (loading) {
    return <div>Loading...</div>
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold mb-6 text-center">
          Sign in to Luvcraft
        </h1>
        
        <button
          onClick={signInWithGoogle}
          className="w-full bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-50 flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            {/* Google Icon SVG */}
          </svg>
          Continue with Google
        </button>
      </div>
    </div>
  )
}
```

### 7. Update _app.tsx

`frontend/pages/_app.tsx`:

```typescript
import type { AppProps } from 'next/app'
import { AuthProvider } from '@/contexts/AuthContext'
import '@/styles/globals.css'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <AuthProvider>
      <Component {...pageProps} />
    </AuthProvider>
  )
}
```

### 8. Protected Route Example

`frontend/components/ProtectedRoute.tsx`:

```typescript
import { useAuth } from '@/contexts/AuthContext'
import { useRouter } from 'next/router'
import { useEffect } from 'react'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login')
    }
  }, [user, loading, router])

  if (loading) {
    return <div>Loading...</div>
  }

  if (!user) {
    return null
  }

  return <>{children}</>
}
```

### 9. Use in Dashboard

`frontend/pages/index.tsx`:

```typescript
import { useAuth } from '@/contexts/AuthContext'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { apiClient } from '@/services/api/client'
import { useEffect, useState } from 'react'

export default function DashboardPage() {
  const { user, signOut } = useAuth()
  const [runs, setRuns] = useState([])

  useEffect(() => {
    // Fetch runs from authenticated API
    apiClient.get('/api/v1/runs')
      .then(data => setRuns(data))
      .catch(error => console.error('Failed to fetch runs:', error))
  }, [])

  return (
    <ProtectedRoute>
      <div className="p-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <div className="flex items-center gap-4">
            <span>Welcome, {user?.email}</span>
            <button onClick={signOut} className="btn">
              Sign Out
            </button>
          </div>
        </div>

        {/* Your dashboard content */}
        <div>
          {runs.map((run) => (
            <div key={run.id}>{/* Run item */}</div>
          ))}
        </div>
      </div>
    </ProtectedRoute>
  )
}
```

## Testing

### 1. Disable Email Confirmation (Development Only)

Supabase Dashboard → Authentication → Settings → Enable email confirmations → OFF

### 2. Test Flow

1. Start backend: `cd backend && ./start_server.sh`
2. Start frontend: `cd frontend && npm run dev`
3. Visit http://localhost:3000
4. Click "Sign in with Google"
5. Complete OAuth flow
6. Redirect back to dashboard
7. API calls automatically include JWT token

### 3. Test API Calls

```typescript
// In browser console
const token = (await supabase.auth.getSession()).data.session?.access_token
console.log('Token:', token)

// Test authenticated endpoint
fetch('http://localhost:8000/api/v1/runs', {
  headers: { 'Authorization': `Bearer ${token}` }
})
```

## Troubleshooting

### "Email not confirmed"
- Disable email confirmations in Supabase Dashboard
- Or manually confirm user in Authentication → Users

### "Not authenticated" error
- Check token is being sent: Network tab → Headers → Authorization
- Verify SUPABASE_JWT_SECRET matches in backend config
- Check token expiry (default 1 hour)

### CORS errors
- Verify CORS_ORIGINS in backend `.env.local`
- Should include: `http://localhost:3000`

### "Invalid authentication credentials"
- Check JWT_SECRET matches Supabase project
- Verify token hasn't expired
- Check user exists in Supabase auth.users table

## Security Best Practices

1. ✅ Never commit `.env.local` files
2. ✅ Use HTTPOnly cookies for tokens (Supabase handles this)
3. ✅ Implement token refresh (Supabase SDK does this automatically)
4. ✅ Use HTTPS in production
5. ✅ Validate JWT on backend (already implemented)
6. ✅ Implement rate limiting (TODO)
7. ✅ Add CSRF protection (TODO)

## Production Deployment

### Backend
```bash
# Update production .env
SUPABASE_URL=https://svnndjisftzropetvisq.supabase.co
SUPABASE_JWT_SECRET=<production-secret>
CORS_ORIGINS=https://your-production-domain.com
```

### Frontend
```bash
# Update production environment
NEXT_PUBLIC_SUPABASE_URL=https://svnndjisftzropetvisq.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<production-anon-key>
NEXT_PUBLIC_API_URL=https://api.your-domain.com
```

### Supabase Configuration
1. Add production URL to redirect URLs
2. Configure Google OAuth production credentials
3. Enable email confirmations
4. Set up custom email templates

## Next Steps

- [ ] Implement role-based access control (RBAC)
- [ ] Add user profile management
- [ ] Implement password reset flow
- [ ] Add Microsoft OAuth provider
- [ ] Set up email templates
- [ ] Add rate limiting middleware
- [ ] Implement audit logging
