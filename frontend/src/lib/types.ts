export type MealType = 'breakfast' | 'lunch' | 'dinner'
export type StorageLocation = 'pantry' | 'refrigerator' | 'freezer' | 'counter' | 'other'

export interface Profile {
  display_name: string | null
  dietary_preferences: string[]
  allergies: string[]
  preferred_cuisines: string[]
  preferred_tastes: string[]
  daily_calorie_target: number | null
  onboarding_completed_at: string | null
  locale: string
  timezone: string
  currency_code: string
}

export interface Ingredient {
  id: number
  slug: string
  name: string
  base_unit: 'g' | 'ml' | 'each'
  dietary_tags: string[]
  allergens: string[]
  recommended_storage_location: StorageLocation | null
  typical_shelf_life_days: number | null
  storage_instructions: string | null
}

export interface PantryItem {
  id: number
  ingredient_id: number
  initial_quantity: number
  remaining_quantity: number
  unit: 'g' | 'ml' | 'each'
  storage_location: StorageLocation
  best_before_on: string | null
  status: 'available' | 'depleted' | 'discarded'
  purchase_price: number | null
  currency_code: string | null
  ingredient: Ingredient
  active_storage_guidance?: {
    storage_instructions: string
    avoidance_notes?: string | null
  } | null
}

export interface RecipeIngredient {
  id?: number
  ingredient_id: number
  quantity: number
  unit: 'g' | 'ml' | 'each'
  preparation_note?: string | null
  optional?: boolean
}

export interface Recipe {
  id: number
  title: string
  description: string | null
  source: 'manual' | 'generated'
  cuisine: string | null
  category: string | null
  servings: number
  prep_minutes: number
  cook_minutes: number
  instructions: Array<string | { text?: string }>
  nutrition: Record<string, number | string>
  saved_at: string | null
  ingredients: RecipeIngredient[]
}

export interface MealSlot {
  id: number
  meal_date: string
  meal_type: MealType
  requested_cuisine: string | null
  requested_category: string | null
  recipe_id: number | null
  servings: number
  status: 'requested' | 'generated' | 'accepted' | 'cooked' | 'skipped'
}

export interface MealPlan {
  id: number
  name: string | null
  start_date: string
  end_date: string
  checkout_budget: number | null
  currency_code: string
  selected_meal_types: MealType[]
  status: 'draft' | 'generating' | 'ready' | 'active' | 'completed' | 'archived' | 'failed'
  meals: MealSlot[]
}

export interface ShoppingItem {
  id: number
  ingredient_id: number | null
  custom_label: string | null
  source: 'generated' | 'manual'
  required_quantity: number
  pantry_quantity: number
  to_buy_quantity: number
  unit: 'g' | 'ml' | 'each' | null
  needed_by_date: string | null
  estimated_price: number | null
  status: 'pending' | 'bought' | 'skipped'
}

export interface ShoppingList {
  id: number
  meal_plan_id: number
  currency_code: string
  estimated_total: number | null
  status: 'active' | 'completed' | 'archived'
  items: ShoppingItem[]
}

export interface ReceiptItem {
  id: number
  line_number: number
  raw_text: string
  ingredient_id: number | null
  quantity: number | null
  unit: 'g' | 'ml' | 'each' | null
  unit_price: number | null
  line_total: number | null
  match_confidence: number | null
  review_status: 'pending' | 'accepted' | 'corrected' | 'ignored'
}

export interface Receipt {
  id: number
  merchant_name: string | null
  purchased_at: string | null
  total_amount: number | null
  currency_code: string
  status: 'uploaded' | 'processing' | 'review' | 'confirmed' | 'failed'
  items: ReceiptItem[]
}

export interface ImpactSummary {
  week_start: string
  week_end: string
  currency_code: string
  spent_amount: number
  estimated_saved_amount: number
  estimated_food_saved_g: number
  pantry_items_used: number
  previous_week_food_saved_g: number
  streak_weeks: number
}

export interface GeneratedPlan {
  plan: MealPlan
  recipes: Recipe[]
  shopping_list: ShoppingList
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
