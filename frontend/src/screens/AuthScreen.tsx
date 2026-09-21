import { useState, type FormEvent } from 'react'
import { Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Brand, Button } from '../components/UI'

export function AuthScreen() {
  const { user, signIn, signUp, signInWithGoogle, isDemo } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('alex@example.com')
  const [password, setPassword] = useState('freshloop')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/" replace />

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { if (mode === 'signin') await signIn(email, password); else await signUp(email, password); navigate(mode === 'signup' ? '/onboarding' : '/') }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Authentication failed') }
    finally { setBusy(false) }
  }

  return <div className="auth-screen">
    <div className="auth-brand"><Brand /><p>Good food. Less waste.</p></div>
    <form className="auth-panel" onSubmit={submit}>
      <h1>{mode === 'signin' ? 'Welcome back' : 'Create your account'}</h1>
      <p>{mode === 'signin' ? 'Sign in to plan meals and waste less.' : 'Start with the food you already have.'}</p>
      {isDemo ? <div className="notice notice--positive">Demo mode is ready—any details will work.</div> : null}
      <label className="input-with-icon"><span>Email</span><div><Mail /><input aria-label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></div></label>
      <label className="input-with-icon"><span>Password</span><div><LockKeyhole /><input aria-label="Password" type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required /><button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff /> : <Eye />}</button></div></label>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <Button type="submit" disabled={busy}>{busy ? 'One moment…' : mode === 'signin' ? 'Continue →' : 'Create account →'}</Button>
      <div className="divider"><span>or continue with</span></div>
      <Button type="button" variant="secondary" onClick={() => void signInWithGoogle()}>ⓖ Continue with Google</Button>
      <p className="auth-switch">{mode === 'signin' ? 'New to FreshLoop?' : 'Already have an account?'} <button type="button" onClick={() => setMode((value) => value === 'signin' ? 'signup' : 'signin')}>{mode === 'signin' ? 'Create account' : 'Sign in'}</button></p>
    </form>
  </div>
}
