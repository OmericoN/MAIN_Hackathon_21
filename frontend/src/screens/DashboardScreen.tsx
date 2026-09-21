import { useEffect, useState } from 'react'
import { ArrowRight, CalendarDays, CircleCheck, PackageOpen, PiggyBank, Scale, WalletCards } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader, Section, LoadingState, ErrorState, Money } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import { emojiBySlug } from '../lib/demoData'
import type { ImpactSummary, PantryItem } from '../lib/types'

const monday = () => { const date = new Date(); const day = date.getDay() || 7; date.setDate(date.getDate() - day + 1); return date.toISOString().slice(0, 10) }

export function DashboardScreen() {
  const { api } = useAuth(); const [impact, setImpact] = useState<ImpactSummary | null>(null); const [expiring, setExpiring] = useState<PantryItem[]>([]); const [error, setError] = useState('')
  useEffect(() => { let active = true; void Promise.all([api.impact(monday()), api.pantry()]).then(([nextImpact, pantry]) => { if (active) { setImpact(nextImpact); setExpiring(pantry.items.filter((item) => item.best_before_on).slice(0, 2)) } }).catch((reason: Error) => setError(reason.message)); return () => { active = false } }, [api])
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />
  if (!impact) return <LoadingState />
  const budget = 50; const percent = Math.min(100, Math.round(impact.spent_amount / budget * 100))
  return <div className="screen dashboard">
    <PageHeader title="This week" subtitle={`${new Date(impact.week_start).toLocaleDateString('en-NL', { month: 'short', day: 'numeric' })} – ${new Date(impact.week_end).toLocaleDateString('en-NL', { month: 'short', day: 'numeric' })}`} action={<Link className="avatar-button" to="/profile">A</Link>} />
    <div className="metric-strip">
      <article><WalletCards /><span>Spent</span><strong><Money value={impact.spent_amount} /></strong><small>on groceries</small></article>
      <article className="metric--positive"><PiggyBank /><span>Saved</span><strong><Money value={impact.estimated_saved_amount} /></strong><small>vs. buying new</small></article>
      <article className="metric--positive"><Scale /><span>Food saved</span><strong>{(impact.estimated_food_saved_g / 1000).toFixed(1)} kg</strong><small>estimated</small></article>
    </div>
    <Section title="Weekly spend vs. budget" action={<strong><Money value={impact.spent_amount} /> / €{budget}</strong>}><div className="budget-track"><i style={{ width: `${percent}%` }} /></div><div className="positive-line"><CircleCheck /> You’re €{(budget - impact.spent_amount).toFixed(2)} under budget</div></Section>
    <Section title="Today’s meals" action={<CalendarDays />}><div className="coming-soon-inline"><span>🍽️</span><div><strong>Personal recipes are coming soon</strong><small>Your meal slots and preferences are ready for the recipe-generation endpoint.</small></div></div></Section>
    <Section tone="warning" title="Expiring soon" action={<Link to="/pantry">{expiring.length} items <ArrowRight /></Link>}><p className="section-copy">Use these before they go bad.</p>{expiring.map((item) => <div className="list-row" key={item.id}><span className="emoji-tile">{emojiBySlug[item.ingredient.slug] ?? '🥕'}</span><span><strong>{item.ingredient.name}</strong><small>{item.ingredient.storage_instructions}</small></span><span className="freshness freshness--warning">{Math.max(0, Math.ceil((new Date(item.best_before_on!).getTime() - Date.now()) / 86400000))} days</span></div>)}</Section>
    <Link className="next-week-card" to="/plan/new"><span><PackageOpen /><small>Ready when you are</small><strong>Plan a low-waste week</strong></span><ArrowRight /></Link>
  </div>
}
