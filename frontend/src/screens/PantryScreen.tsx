import { useEffect, useMemo, useState } from 'react'
import { Bell, ChevronDown, ChevronUp, Clock3, PackageOpen, ShoppingCart } from 'lucide-react'
import { ErrorState, LoadingState, PageHeader } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import { demoGeneratedPlan, emojiBySlug } from '../lib/demoData'
import type { PantryItem, StorageLocation } from '../lib/types'

const labels: Record<StorageLocation, { label: string; emoji: string }> = { refrigerator: { label: 'Fridge', emoji: '🧊' }, pantry: { label: 'Pantry', emoji: '🫙' }, freezer: { label: 'Freezer', emoji: '❄️' }, counter: { label: 'Counter', emoji: '🍌' }, other: { label: 'Other', emoji: '📦' } }
const daysLeft = (date: string | null) => date ? Math.ceil((new Date(date).getTime() - Date.now()) / 86400000) : null

export function PantryScreen() {
  const { api } = useAuth(); const [items, setItems] = useState<PantryItem[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [tab, setTab] = useState<'all' | 'soon' | 'later'>('all')
  const [open, setOpen] = useState<Record<string, boolean>>({ refrigerator: true, pantry: false, freezer: false, counter: false }); const [reminders, setReminders] = useState(() => localStorage.getItem('freshloop-reminders') !== 'false')
  useEffect(() => { void api.pantry().then((page) => setItems(page.items)).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false)) }, [api])
  const soon = useMemo(() => items.filter((item) => { const days = daysLeft(item.best_before_on); return days !== null && days <= 4 }), [items])
  const later = demoGeneratedPlan.shopping_list.items.filter((item) => item.needed_by_date && new Date(item.needed_by_date).getTime() > Date.now() + 86400000)
  if (loading) return <LoadingState label="Checking what stays fresh…" />
  if (error) return <ErrorState message={error} />
  const locations = Object.keys(labels) as StorageLocation[]
  return <div className="screen pantry-screen">
    <PageHeader title="Keep it fresh" subtitle="Storage tips and freshness reminders for your pantry." />
    <div className="segmented"><button className={tab === 'all' ? 'is-active' : ''} onClick={() => setTab('all')}>All items</button><button className={tab === 'soon' ? 'is-active' : ''} onClick={() => setTab('soon')}>Use soon <b>{soon.length}</b></button><button className={tab === 'later' ? 'is-active' : ''} onClick={() => setTab('later')}>Pick up later <b>{later.length}</b></button></div>
    {tab !== 'later' && soon.length ? <section className="use-soon"><div className="section-heading"><h2><Clock3 /> Use soon</h2><span>{soon.length} items</span></div><p>Plan a meal before these expire.</p>{soon.map((item) => <div className="list-row" key={item.id}><span className="emoji-tile">{emojiBySlug[item.ingredient.slug] ?? '🌿'}</span><span><strong>{item.ingredient.name}</strong><small>{item.storage_location} · {item.ingredient.storage_instructions}</small></span><span className="freshness freshness--warning">{Math.max(0, daysLeft(item.best_before_on) ?? 0)} days</span></div>)}</section> : null}
    {tab === 'later' ? <section className="pick-up-later"><div className="section-heading"><h2><ShoppingCart /> Pick up later</h2></div><p>Items needed later in your plan stay off today’s list.</p>{later.map((item) => <div className="list-row" key={item.id}><span className="emoji-tile">🛒</span><span><strong>Planned grocery</strong><small>Buy on {new Date(item.needed_by_date!).toLocaleDateString('en-NL', { weekday: 'short', month: 'short', day: 'numeric' })}</small></span><span className="freshness">Later</span></div>)}</section> : null}
    {tab !== 'later' ? <div className="storage-groups">{locations.map((location) => { const group = items.filter((item) => item.storage_location === location && (tab === 'all' || soon.includes(item))); if (!group.length) return null; return <section key={location} className="storage-group"><button onClick={() => setOpen((current) => ({ ...current, [location]: !current[location] }))}><span>{labels[location].emoji} <strong>{labels[location].label}</strong><small>{group.length} items</small></span>{open[location] || tab === 'soon' ? <ChevronUp /> : <ChevronDown />}</button>{open[location] || tab === 'soon' ? group.map((item) => <div className="list-row" key={item.id}><span className="emoji-tile">{emojiBySlug[item.ingredient.slug] ?? '🥕'}</span><span><strong>{item.ingredient.name}</strong><small>{item.active_storage_guidance?.storage_instructions ?? item.ingredient.storage_instructions ?? 'Keep stored safely.'}</small></span><span className="freshness">{daysLeft(item.best_before_on) === null ? 'Fresh' : `${daysLeft(item.best_before_on)} days`}</span></div>) : null}</section> })}</div> : null}
    <label className="notification-toggle"><Bell /><span><strong>Notify me about expiring items</strong><small>In-app reminders appear 2 days before expiry.</small></span><input type="checkbox" checked={reminders} onChange={(event) => { setReminders(event.target.checked); localStorage.setItem('freshloop-reminders', String(event.target.checked)); if (event.target.checked && 'Notification' in window && Notification.permission === 'default') void Notification.requestPermission() }} /><i /></label>
    {!items.length ? <div className="state"><PackageOpen /><h2>Your pantry is ready</h2><p>Scan a receipt to add your first groceries.</p></div> : null}
  </div>
}
