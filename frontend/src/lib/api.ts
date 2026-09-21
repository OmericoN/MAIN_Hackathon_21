import { demoGeneratedPlan, demoImpact, demoIngredients, demoPantry, demoProfile, demoReceipt, demoRecipes } from './demoData'
import type { GeneratedPlan, ImpactSummary, Ingredient, MealPlan, Page, PantryItem, Profile, Receipt, Recipe, ShoppingItem, ShoppingList } from './types'

const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

export class FreshLoopApi {
  private getToken: () => Promise<string | null>
  private demo: boolean
  private demoPantryItems = structuredClone(demoPantry)
  private confirmedDemoReceipts = new Set<number>()
  constructor(getToken: () => Promise<string | null>, demo = false) { this.getToken = getToken; this.demo = demo }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    if (this.demo) throw new ApiError('demo', 418)
    const token = await this.getToken()
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { message?: string } | null
      throw new ApiError(body?.message ?? `Request failed (${response.status})`, response.status)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  async profile(): Promise<Profile> { if (this.demo) return structuredClone(demoProfile); return this.request('/v1/me/profile') }
  async completeOnboarding(profile: Partial<Profile>): Promise<Profile> {
    if (this.demo) return { ...structuredClone(demoProfile), ...profile, onboarding_completed_at: new Date().toISOString() }
    return this.request('/v1/me/onboarding', { method: 'PUT', body: JSON.stringify(profile) })
  }
  async updateProfile(profile: Partial<Profile>): Promise<Profile> {
    if (this.demo) return { ...structuredClone(demoProfile), ...profile }
    return this.request('/v1/me/profile', { method: 'PATCH', body: JSON.stringify(profile) })
  }
  async ingredients(query = ''): Promise<Page<Ingredient>> {
    if (this.demo) { const q = query.toLowerCase(); const items = demoIngredients.filter((item) => item.name.toLowerCase().includes(q)); return { items, total: items.length, limit: 50, offset: 0 } }
    return this.request(`/v1/ingredients?limit=50${query ? `&q=${encodeURIComponent(query)}` : ''}`)
  }
  async pantry(): Promise<Page<PantryItem>> { if (this.demo) return { items: structuredClone(this.demoPantryItems), total: this.demoPantryItems.length, limit: 50, offset: 0 }; return this.request('/v1/pantry-items?limit=100') }
  async addPantryItem(payload: Record<string, unknown>): Promise<PantryItem> {
    if (this.demo) {
      const ingredient = demoIngredients.find((item) => item.id === Number(payload.ingredient_id)) ?? demoIngredients[0]
      const item: PantryItem = {
        id: Math.max(0, ...this.demoPantryItems.map((entry) => entry.id)) + 1,
        ingredient_id: ingredient.id,
        initial_quantity: Number(payload.initial_quantity ?? 1), remaining_quantity: Number(payload.initial_quantity ?? 1),
        unit: (payload.unit as PantryItem['unit'] | undefined) ?? ingredient.base_unit,
        storage_location: (payload.storage_location as PantryItem['storage_location'] | undefined) ?? ingredient.recommended_storage_location ?? 'pantry',
        best_before_on: null, status: 'available', purchase_price: null, currency_code: 'EUR', ingredient,
        active_storage_guidance: { storage_instructions: ingredient.storage_instructions ?? 'Store safely.' },
      }
      this.demoPantryItems.push(item)
      return structuredClone(item)
    }
    return this.request('/v1/pantry-items', { method: 'POST', body: JSON.stringify(payload) })
  }
  async recipes(savedOnly = false): Promise<Page<Recipe>> { if (this.demo) { const items = structuredClone(demoRecipes).filter((item) => !savedOnly || item.saved_at); return { items, total: items.length, limit: 50, offset: 0 } }; const page = await this.request<Page<Recipe>>('/v1/recipes?limit=100'); return savedOnly ? { ...page, items: page.items.filter((item) => item.saved_at), total: page.items.filter((item) => item.saved_at).length } : page }
  async recipe(id: number): Promise<Recipe> { if (this.demo) return structuredClone(demoRecipes.find((item) => item.id === id) ?? demoRecipes[0]); return this.request(`/v1/recipes/${id}`) }
  async saveRecipe(id: number, saved: boolean): Promise<Recipe> {
    if (this.demo) return { ...structuredClone(demoRecipes.find((item) => item.id === id) ?? demoRecipes[0]), saved_at: saved ? new Date().toISOString() : null }
    return this.request(`/v1/recipes/${id}`, { method: 'PATCH', body: JSON.stringify({ saved_at: saved ? new Date().toISOString() : null }) })
  }
  async createPlan(payload: Record<string, unknown>): Promise<MealPlan> { if (this.demo) return structuredClone(demoGeneratedPlan.plan); return this.request('/v1/meal-plans', { method: 'POST', body: JSON.stringify(payload) }) }
  async patchMeal(planId: number, mealId: number, payload: Record<string, unknown>) { if (this.demo) return; return this.request(`/v1/meal-plans/${planId}/meals/${mealId}`, { method: 'PATCH', body: JSON.stringify(payload) }) }
  async plan(id: number): Promise<GeneratedPlan> {
    if (this.demo) return structuredClone(demoGeneratedPlan)
    const plan = await this.request<MealPlan>(`/v1/meal-plans/${id}`)
    const [recipes, lists] = await Promise.all([this.request<Page<Recipe>>('/v1/recipes?limit=100'), this.request<Page<ShoppingList>>('/v1/shopping-lists?limit=100')])
    const shoppingList = lists.items.find((item) => item.meal_plan_id === id) ?? { id: 0, meal_plan_id: id, currency_code: plan.currency_code, estimated_total: null, status: 'active' as const, items: [] }
    return { plan, recipes: recipes.items.filter((recipe) => plan.meals.some((meal) => meal.recipe_id === recipe.id)), shopping_list: shoppingList }
  }
  async updateShoppingItem(listId: number, item: ShoppingItem): Promise<ShoppingItem> { if (this.demo) return item; return this.request(`/v1/shopping-lists/${listId}/items/${item.id}`, { method: 'PATCH', body: JSON.stringify({ status: item.status }) }) }
  async scanReceipt(file: File): Promise<Receipt> {
    if (this.demo) { await new Promise((resolve) => setTimeout(resolve, 1100)); return structuredClone(demoReceipt) }
    return this.request('/v1/receipts', { method: 'POST', body: JSON.stringify({ merchant_name: 'Uploaded receipt', purchased_at: new Date().toISOString(), currency_code: 'EUR', image_path: file.name }) })
  }
  async updateReceiptExtraction(receipt: Receipt): Promise<Receipt> {
    if (this.demo) return receipt
    return this.request(`/v1/receipts/${receipt.id}/extraction`, { method: 'PUT', body: JSON.stringify({ merchant_name: receipt.merchant_name, purchased_at: receipt.purchased_at, total_amount: receipt.total_amount, currency_code: receipt.currency_code, raw_ocr: {}, items: receipt.items.map((item) => ({ line_number: item.line_number, raw_text: item.raw_text, ingredient_id: item.ingredient_id, quantity: item.quantity, unit: item.unit, unit_price: item.unit_price, line_total: item.line_total, match_confidence: item.match_confidence, review_status: item.review_status })) }) })
  }
  async confirmReceipt(receipt: Receipt): Promise<Receipt> {
    if (this.demo) {
      if (!this.confirmedDemoReceipts.has(receipt.id)) {
        for (const line of receipt.items.filter((item) => item.review_status !== 'ignored' && item.ingredient_id)) {
          const ingredient = demoIngredients.find((item) => item.id === line.ingredient_id)
          if (!ingredient || !line.quantity || !line.unit) continue
          const current = this.demoPantryItems.find((item) => item.ingredient_id === ingredient.id && item.unit === line.unit)
          if (current) {
            current.initial_quantity += line.quantity
            current.remaining_quantity += line.quantity
            current.purchase_price = (current.purchase_price ?? 0) + (line.line_total ?? 0)
            continue
          }
          const bestBefore = new Date()
          bestBefore.setDate(bestBefore.getDate() + (ingredient.typical_shelf_life_days ?? 14))
          this.demoPantryItems.push({
            id: Math.max(0, ...this.demoPantryItems.map((item) => item.id)) + 1,
            ingredient_id: ingredient.id, initial_quantity: line.quantity, remaining_quantity: line.quantity,
            unit: line.unit, storage_location: ingredient.recommended_storage_location ?? 'pantry',
            best_before_on: bestBefore.toISOString().slice(0, 10), status: 'available',
            purchase_price: line.line_total, currency_code: receipt.currency_code, ingredient,
            active_storage_guidance: { storage_instructions: ingredient.storage_instructions ?? 'Store safely.' },
          })
        }
        this.confirmedDemoReceipts.add(receipt.id)
      }
      return { ...receipt, status: 'confirmed' }
    }
    await this.updateReceiptExtraction(receipt)
    return this.request(`/v1/receipts/${receipt.id}/confirm`, { method: 'POST' })
  }
  async impact(weekStart: string): Promise<ImpactSummary> {
    if (this.demo) return structuredClone(demoImpact)
    const [receipts, lists, waste] = await Promise.all([
      this.request<Page<Receipt>>('/v1/receipts?limit=100'),
      this.request<Page<ShoppingList>>('/v1/shopping-lists?limit=100'),
      this.request<Page<{ estimated_value: number | null; estimated_weight_g: number | null; occurred_at: string }>>('/v1/waste-events?limit=100'),
    ])
    const start = new Date(`${weekStart}T00:00:00`); const end = new Date(start); end.setDate(end.getDate() + 7)
    const within = (value: string | null) => value ? new Date(value) >= start && new Date(value) < end : false
    const spent = receipts.items.filter((item) => item.status === 'confirmed' && within(item.purchased_at)).reduce((sum, item) => sum + (item.total_amount ?? 0), 0)
    const saved = lists.items.flatMap((list) => list.items).reduce((sum, item) => sum + (item.pantry_quantity > 0 ? item.estimated_price ?? 0 : 0), 0)
    const wasted = waste.items.filter((item) => within(item.occurred_at)).reduce((sum, item) => sum + (item.estimated_weight_g ?? 0), 0)
    const weekEnd = new Date(end); weekEnd.setDate(weekEnd.getDate() - 1)
    return { week_start: weekStart, week_end: weekEnd.toISOString().slice(0, 10), currency_code: 'EUR', spent_amount: spent, estimated_saved_amount: saved, estimated_food_saved_g: Math.max(0, 1000 - wasted), pantry_items_used: lists.items.flatMap((list) => list.items).filter((item) => item.pantry_quantity > 0).length, previous_week_food_saved_g: 0, streak_weeks: spent || saved ? 1 : 0 }
  }
}
