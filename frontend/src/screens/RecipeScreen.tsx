import { useEffect, useState } from 'react'
import { Bookmark, Check, Clock3, Flame, UsersRound } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { Button, ErrorState, LoadingState, PageHeader, Section } from '../components/UI'
import { useAuth } from '../context/AuthContext'
import { demoIngredients, emojiBySlug } from '../lib/demoData'
import type { Recipe } from '../lib/types'

export function RecipeScreen() {
  const { id = '101' } = useParams(); const { api } = useAuth(); const [recipe, setRecipe] = useState<Recipe | null>(null); const [error, setError] = useState('')
  useEffect(() => { void api.recipe(Number(id)).then(setRecipe).catch((reason: Error) => setError(reason.message)) }, [api, id])
  if (error) return <ErrorState message={error} />
  if (!recipe) return <LoadingState label="Opening your recipe…" />
  return <div className="screen recipe-screen">
    <PageHeader back title={recipe.title} subtitle={recipe.description ?? undefined} action={<button className={`icon-button ${recipe.saved_at ? 'is-saved' : ''}`} onClick={() => void api.saveRecipe(recipe.id, !recipe.saved_at).then(setRecipe)} aria-label={recipe.saved_at ? 'Remove saved recipe' : 'Save recipe'}><Bookmark /></button>} />
    <div className="recipe-hero" aria-hidden="true">{recipe.category?.toLowerCase().includes('salad') ? '🥗' : recipe.category?.toLowerCase().includes('breakfast') ? '🥣' : '🍝'}<span>{recipe.cuisine}</span></div>
    <div className="recipe-facts"><span><Clock3 />{recipe.prep_minutes + recipe.cook_minutes} min</span><span><UsersRound />{recipe.servings} servings</span><span><Flame />{String(recipe.nutrition.calories ?? '—')} kcal</span></div>
    <Section title="Ingredients"><div className="ingredient-list">{recipe.ingredients.map((item, index) => { const ingredient = demoIngredients.find((entry) => entry.id === item.ingredient_id); return <div key={`${item.ingredient_id}-${index}`}><span>{emojiBySlug[ingredient?.slug ?? ''] ?? '🌿'}</span><strong>{ingredient?.name ?? `Ingredient ${item.ingredient_id}`}</strong><small>{item.quantity} {item.unit}</small></div> })}</div></Section>
    <Section title="Directions"><ol className="directions">{recipe.instructions.map((step, index) => <li key={index}><span>{index + 1}</span><p>{typeof step === 'string' ? step : step.text ?? 'Prepare this step.'}</p></li>)}</ol></Section>
    <Button variant={recipe.saved_at ? 'secondary' : 'primary'} onClick={() => void api.saveRecipe(recipe.id, !recipe.saved_at).then(setRecipe)}>{recipe.saved_at ? <><Check /> Saved to profile</> : <><Bookmark /> Save recipe</>}</Button>
  </div>
}
