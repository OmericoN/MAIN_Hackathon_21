import { useEffect, useState } from 'react'
import { ArrowUpRight, CalendarDays, Share2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Button, LoadingState, PageHeader } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import type { ImpactSummary } from '../lib/types'

export function SummaryScreen() {
  const { week = new Date().toISOString().slice(0, 10) } = useParams(); const { api } = useAuth(); const [impact, setImpact] = useState<ImpactSummary | null>(null)
  useEffect(() => { void api.impact(week).then(setImpact) }, [api, week])
  if (!impact) return <LoadingState label="Counting up your impact…" />
  const improvement = impact.previous_week_food_saved_g ? Math.round((impact.estimated_food_saved_g - impact.previous_week_food_saved_g) / impact.previous_week_food_saved_g * 100) : 0
  return <div className="screen summary-screen">
    <PageHeader title="You gave food a second chance" subtitle={`Here’s your impact from ${new Date(impact.week_start).toLocaleDateString('en-NL', { month: 'short', day: 'numeric' })} – ${new Date(impact.week_end).toLocaleDateString('en-NL', { month: 'short', day: 'numeric' })}.`} />
    <div className="confetti" aria-hidden="true">{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>
    <section className="impact-hero"><span>🌿</span><strong>{(impact.estimated_food_saved_g / 1000).toFixed(1)} kg</strong><h2>food saved</h2><p>That’s the equivalent of about {Math.max(1, Math.round(impact.estimated_food_saved_g / 450))} meals kept out of the bin.</p></section>
    <div className="summary-metrics"><article><span>👛</span><strong>€{impact.estimated_saved_amount.toFixed(2)}</strong><small>money saved</small></article><article><span>🫙</span><strong>{impact.pantry_items_used}</strong><small>pantry items used</small></article><article><span>🌱</span><strong>{(impact.estimated_food_saved_g / 1000).toFixed(1)} kg</strong><small>food saved</small></article></div>
    <section className="comparison"><h2>Week over week</h2><div><span>This week</span><i><b style={{ width: '86%' }} /></i><strong>{(impact.estimated_food_saved_g / 1000).toFixed(1)} kg</strong></div><div><span>Last week</span><i><b style={{ width: `${Math.min(86, impact.previous_week_food_saved_g / impact.estimated_food_saved_g * 86)}%` }} /></i><strong>{(impact.previous_week_food_saved_g / 1000).toFixed(1)} kg</strong></div><em><ArrowUpRight /> {improvement >= 0 ? '+' : ''}{improvement}%</em></section>
    <div className="streak">🔥 <span><strong>{impact.streak_weeks} week streak</strong><small>You’ve saved food every week. Keep it going!</small></span></div>
    <div className="summary-actions"><Link className="button button--primary" to="/plan/new"><CalendarDays /> Plan next week</Link><Button variant="secondary" onClick={() => void navigator.clipboard?.writeText(`I saved ${(impact.estimated_food_saved_g / 1000).toFixed(1)} kg of food with FreshLoop!`)}><Share2 /> Share impact</Button></div>
  </div>
}
