import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { FreshLoopApi } from '../lib/api'
import { isSupabaseConfigured, supabase } from '../lib/supabase'

interface AuthState {
  user: User | null
  session: Session | null
  loading: boolean
  isDemo: boolean
  api: FreshLoopApi
  signIn(email: string, password: string): Promise<void>
  signUp(email: string, password: string): Promise<void>
  signInWithGoogle(): Promise<void>
  signOut(): Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [demoSignedIn, setDemoSignedIn] = useState(() => localStorage.getItem('freshloop-demo-signed-in') !== 'false')
  const [loading, setLoading] = useState(isSupabaseConfigured)

  useEffect(() => {
    if (!supabase) return
    void supabase.auth.getSession().then(({ data }) => { setSession(data.session); setLoading(false) })
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => { setSession(nextSession); setLoading(false) })
    return () => data.subscription.unsubscribe()
  }, [])

  const api = useMemo(() => new FreshLoopApi(async () => {
    if (!supabase) return null
    return (await supabase.auth.getSession()).data.session?.access_token ?? null
  }, !isSupabaseConfigured), [])

  const value: AuthState = {
    user: isSupabaseConfigured ? session?.user ?? null : demoSignedIn ? ({ id: 'demo-user', email: 'alex@example.com' } as User) : null,
    session, loading, isDemo: !isSupabaseConfigured, api,
    async signIn(email, password) {
      if (!supabase) { localStorage.setItem('freshloop-demo-signed-in', 'true'); setDemoSignedIn(true); return }
      const { error } = await supabase.auth.signInWithPassword({ email, password }); if (error) throw error
    },
    async signUp(email, password) {
      if (!supabase) { localStorage.setItem('freshloop-demo-signed-in', 'true'); setDemoSignedIn(true); return }
      const { error } = await supabase.auth.signUp({ email, password }); if (error) throw error
    },
    async signInWithGoogle() {
      if (!supabase) { localStorage.setItem('freshloop-demo-signed-in', 'true'); setDemoSignedIn(true); return }
      const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } }); if (error) throw error
    },
    async signOut() { if (supabase) await supabase.auth.signOut(); localStorage.setItem('freshloop-demo-signed-in', 'false'); setDemoSignedIn(false) },
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// This small hook intentionally lives beside its provider so the auth contract stays in one place.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
