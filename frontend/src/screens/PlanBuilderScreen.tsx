import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ArrowRight, CalendarDays, CirclePlus, Coins, PackageOpen, Search, Utensils } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button, Chip, PageHeader, Section } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import type { Ingredient, MealType, PantryItem } from '../lib/types'

const cuisines = ['Italian', 'Asian', 'Mediterranean', 'Indian', 'Global']
const categories = ['Pasta', 'Stir-fry', 'Salad', 'Curry', 'Soup']
const dateString = (offset: number) => { const date = new Date(); date.setDate(date.getDate() + offset); return date.toISOString().slice(0, 10) }

export function PlanBuilderScreen() {
  const { api } = useAuth(); const navigate = useNavigate()
  const [ingredients, setIngredients] = useState<Ingredient[]>([]); const [pantry, setPantry] = useState<PantryItem[]>([])
  const [query, setQuery] = useState(''); const [selected, setSelected] = useState<Ingredient[]>([])
  const [days, setDays] = useState(5); const [budget, setBudget] = useState(42)
  const [meals, setMeals] = useState<MealType[]>(['breakfast', 'lunch', 'dinner'])
  const [preferences, setPreferences] = useState(() => Array.from({ length: 7 }, (_, index) => ({ cuisine: cuisines[index % cuisines.length], category: categories[index % categories.length] })))
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  useEffect(() => { void Promise.all([api.ingredients(), api.pantry()]).then(([ingredientPage, pantryPage]) => { setIngredients(ingredientPage.items); setPantry(pantryPage.items); setSelected(pantryPage.items.map((item) => item.ingredient).slice(0, 6)) }) }, [api])
  const results = useMemo(() => query.trim() ? ingredients.filter((item) => item.name.toLowerCase().includes(query.toLowerCase()) && !selected.some((chosen) => chosen.id === item.id)).slice(0, 5) : [], [ingredients, query, selected])
  const toggleMeal = (meal: MealType) => setMeals((current) => current.includes(meal) ? current.filter((item) => item !== meal) : [...current, meal])
  const updatePreference = (index: number, key: 'cuisine' | 'category', value: string) => setPreferences((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))

  async function submit(event: FormEvent) {
    event.preventDefault(); if (!meals.length) { setError('Choose at least one meal type.'); return }
    setBusy(true); setError('')
    try {
      const existingIds = new Set(pantry.map((item) => item.ingredient_id))
      await Promise.all(selected.filter((item) => !existingIds.has(item.id)).map((item) => api.addPantryItem({ ingredient_id: item.id, initial_quantity: item.base_unit === 'each' ? 1 : 100, unit: item.base_unit, storage_location: item.recommended_storage_location ?? 'pantry' })))
      const plan = await api.createPlan({ name: 'FreshLoop week', start_date: dateString(0), end_date: dateString(days - 1), checkout_budget: budget, currency_code: 'EUR', selected_meal_types: meals })
      await Promise.all(plan.meals.map((slot) => { const dayIndex = Math.max(0, Math.round((new Date(slot.meal_date).getTime() - new Date(plan.start_date).getTime()) / 86400000)); return api.patchMeal(plan.id, slot.id, { requested_cuisine: preferences[dayIndex].cuisine, requested_category: preferences[dayIndex].category }) }))
      navigate(`/plans/${plan.id}`)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not generate your plan') }
    finally { setBusy(false) }
  }

  return <form className="screen plan-builder" onSubmit={submit}>
    <PageHeader title="Build your meal plan" subtitle="Add what you have, set your preferences, and we’ll create a low-waste week." />
    <Section title="What’s in your pantry?" action={<PackageOpen />}>
      <label className="search-field"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Add ingredients" /></label>
      {results.length ? <div className="search-results">{results.map((item) => <button key={item.id} type="button" onClick={() => { setSelected((current) => [...current, item]); setQuery('') }}><CirclePlus />{item.name}</button>)}</div> : null}
      <div className="selected-chips">{selected.map((item) => <Chip key={item.id} onClick={() => setSelected((current) => current.filter((chosen) => chosen.id !== item.id))}>{item.name} ×</Chip>)}</div>
    </Section>
    <div className="form-row"><label><span><CalendarDays />How many days?</span><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value="3">3 days</option><option value="5">5 days</option><option value="7">7 days</option></select></label><label><span><Coins />Budget (EUR)</span><input type="number" min="10" max="500" value={budget} onChange={(event) => setBudget(Number(event.target.value))} /></label></div>
    <Section title="Which meals should we include?" action={<Utensils />}><div className="meal-toggle">{(['breakfast', 'lunch', 'dinner'] as MealType[]).map((item) => <Chip key={item} selected={meals.includes(item)} onClick={() => toggleMeal(item)}>{item === 'breakfast' ? '☀️' : item === 'lunch' ? '🥗' : '🌙'} {item}</Chip>)}</div></Section>
    <div className="plan-by-day"><div className="section-heading"><h2>Plan by day</h2><small>Adaptable per day</small></div>{Array.from({ length: days }, (_, index) => <div className="day-preference" key={index}><strong>Day {index + 1}</strong><select aria-label={`Day ${index + 1} cuisine`} value={preferences[index].cuisine} onChange={(event) => updatePreference(index, 'cuisine', event.target.value)}>{cuisines.map((item) => <option key={item}>{item}</option>)}</select><select aria-label={`Day ${index + 1} category`} value={preferences[index].category} onChange={(event) => updatePreference(index, 'category', event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></div>)}</div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <div className="sticky-action"><Button type="submit" disabled={busy}>{busy ? 'Creating your plan…' : 'Generate my plan'} <ArrowRight /></Button></div>
  </form>
}
