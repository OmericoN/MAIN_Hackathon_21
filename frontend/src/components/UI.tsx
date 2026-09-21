import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { AlertCircle, ArrowLeft, Leaf, LoaderCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand ${compact ? 'brand--compact' : ''}`}><Leaf aria-hidden="true" /><span>Fresh<span>Loop</span></span></div>
}

export function PageHeader({ title, subtitle, back = false, action }: { title: string; subtitle?: string; back?: boolean; action?: ReactNode }) {
  const navigate = useNavigate()
  return <header className="page-header">
    <div className="page-header__top">
      {back ? <button className="icon-button" type="button" onClick={() => navigate(-1)} aria-label="Go back"><ArrowLeft /></button> : <Brand compact />}
      {action}
    </div>
    <h1>{title}</h1>
    {subtitle ? <p>{subtitle}</p> : null}
  </header>
}

export function Button({ children, variant = 'primary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' }) {
  return <button className={`button button--${variant} ${className}`} {...props}>{children}</button>
}

export function Field({ label, hint, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return <label className="field"><span>{label}</span><input {...props} />{hint ? <small>{hint}</small> : null}</label>
}

export function Chip({ selected, children, onClick, className = '' }: { selected?: boolean; children: ReactNode; onClick?: () => void; className?: string }) {
  return <button type="button" className={`chip ${selected ? 'is-selected' : ''} ${className}`} onClick={onClick}>{children}</button>
}

export function Section({ title, action, children, tone = 'default' }: { title?: string; action?: ReactNode; children: ReactNode; tone?: 'default' | 'positive' | 'warning' }) {
  return <section className={`panel panel--${tone}`}>
    {title ? <div className="section-heading"><h2>{title}</h2>{action}</div> : null}
    {children}
  </section>
}

export function LoadingState({ label = 'Loading your fresh start…' }: { label?: string }) {
  return <div className="state state--loading"><LoaderCircle className="spin" aria-hidden="true" /><p>{label}</p></div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="state state--error"><AlertCircle aria-hidden="true" /><h2>Something went sideways</h2><p>{message}</p>{onRetry ? <Button variant="secondary" onClick={onRetry}>Try again</Button> : null}</div>
}

export function EmptyState({ emoji, title, body, action }: { emoji: string; title: string; body: string; action?: ReactNode }) {
  return <div className="state"><span className="state__emoji" aria-hidden="true">{emoji}</span><h2>{title}</h2><p>{body}</p>{action}</div>
}

export function Money({ value, currency = 'EUR', unknown = 'Estimate unavailable' }: { value: number | null | undefined; currency?: string; unknown?: string }) {
  if (value === null || value === undefined) return <span className="muted">{unknown}</span>
  return <>{new Intl.NumberFormat('en-NL', { style: 'currency', currency }).format(value)}</>
}
