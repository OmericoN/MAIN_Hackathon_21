import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronUp, Pencil, ShoppingCart } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Button, ErrorState, LoadingState, Money, PageHeader } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import { demoDeals, demoIngredients, emojiBySlug } from '../lib/demoData'
import type { GeneratedPlan, ShoppingItem } from '../lib/types'

const mealEmoji = ['🥣', '🥗', '🍝']

export function PlanDetailScreen() {
  const { id = '42' } = useParams(); const { api } = useAuth()
  const [data, setData] = useState<GeneratedPlan | null>(null); const [activeDay, setActiveDay] = useState(0); const [error, setError] = useState(''); const [openDeals, setOpenDeals] = useState(true)
  useEffect(() => { void api.plan(Number(id)).then(setData).catch((reason: Error) => setError(reason.message)) }, [api, id])
  const dates = useMemo(() => data ? [...new Set(data.plan.meals.map((meal) => meal.meal_date))] : [], [data])
  if (error) return <ErrorState message={error} />
  if (!data) return <LoadingState label="Putting your week on the table…" />
  const dayMeals = data.plan.meals.filter((meal) => meal.meal_date === dates[activeDay])
  async function toggleShopping(item: ShoppingItem) {
    const updated = { ...item, status: item.status === 'bought' ? 'pending' as const : 'bought' as const }
    setData((current) => current ? { ...current, shopping_list: { ...current.shopping_list, items: current.shopping_list.items.map((entry) => entry.id === item.id ? updated : entry) } } : current)
    await api.updateShoppingItem(data!.shopping_list.id, updated)
  }
  return <div className="screen plan-detail">
    <PageHeader back title="Your meal plan" subtitle={`${dates.length}-day plan · ${data.plan.checkout_budget ? `€${data.plan.checkout_budget} budget` : 'flexible budget'}`} action={<Link className="small-button" to="/plan/new"><Pencil /> Edit plan</Link>} />
    <div className="day-tabs">{dates.map((date, index) => <button key={date} className={activeDay === index ? 'is-active' : ''} onClick={() => setActiveDay(index)}>Day {index + 1}</button>)}</div>
    <div className="day-title"><h2>Day {activeDay + 1} · {dayMeals[0]?.requested_cuisine ?? 'Fresh picks'}</h2></div>
    <div className="coming-soon-banner"><span>✨</span><div><small>COMING SOON</small><strong>Recipes will appear here</strong><p>Your cuisine, category, pantry and dietary preferences are already stored on each meal slot.</p></div></div>
    <div className="meal-list plan-meals">{dayMeals.map((meal, index) => <div className="list-row recipe-placeholder" key={meal.id}><span className="emoji-tile">{mealEmoji[index]}</span><span><small>{meal.meal_type}</small><strong>{meal.requested_category ?? 'Flexible meal'} · {meal.requested_cuisine ?? 'Any cuisine'}</strong></span><span className="soon-label">Recipe soon</span></div>)}</div>
    <div className="shopping-heading"><h2><ShoppingCart /> Shopping list</h2><span>Estimated total: <strong><Money value={data.shopping_list.estimated_total} /></strong></span></div>
    <div className="shopping-list">{data.shopping_list.items.length ? data.shopping_list.items.map((item) => { const ingredient = demoIngredients.find((entry) => entry.id === item.ingredient_id); return <button type="button" className="shopping-row" key={item.id} onClick={() => void toggleShopping(item)}><span className={`checkbox ${item.status === 'bought' ? 'is-checked' : ''}`}>{item.status === 'bought' ? <Check /> : null}</span><span className="shopping-row__emoji">{emojiBySlug[ingredient?.slug ?? ''] ?? '🛒'}</span><span><strong>{ingredient?.name ?? item.custom_label ?? 'Grocery item'}</strong><small>{item.to_buy_quantity} {item.unit ?? ''} · {item.pantry_quantity ? `${item.pantry_quantity} ${item.unit} in pantry` : 'to buy'}</small></span><Money value={item.estimated_price} unknown="—" /></button> }) : <p className="empty-inline">The shopping list will be calculated when recipe assignments become available.</p>}</div>
    <section className="deals"><button className="deals__heading" onClick={() => setOpenDeals((value) => !value)}><span>🏷️ Deals near you <small>Simulated offers</small></span>{openDeals ? <ChevronUp /> : <ChevronDown />}</button>{openDeals ? <div className="deal-strip">{demoDeals.map((deal) => <article key={deal.retailer}><small>{deal.retailer}</small><strong>{deal.item}</strong><span>{deal.price}</span><em>{deal.note}</em></article>)}</div> : null}</section>
    <Button className="wide-save" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>Plan & list saved <Check /></Button>
  </div>
}
