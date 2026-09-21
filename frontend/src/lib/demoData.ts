import type { GeneratedPlan, ImpactSummary, Ingredient, PantryItem, Profile, Receipt, Recipe } from './types'

export const emojiBySlug: Record<string, string> = {
  tomato: '🍅', onion: '🧅', garlic: '🧄', rice: '🍚', pasta: '🍝', spinach: '🥬',
  chickpeas: '🫘', 'chicken-breast': '🍗', egg: '🥚', milk: '🥛', cheese: '🧀',
  banana: '🍌', oats: '🥣', bread: '🍞', avocado: '🥑', 'bell-pepper': '🫑',
}

export const demoIngredients: Ingredient[] = [
  ['tomato', 'Tomato', 'g', 'counter', 7, 'Keep away from sunlight; chill when fully ripe.'],
  ['onion', 'Onion', 'g', 'pantry', 30, 'Store somewhere cool, dry and ventilated.'],
  ['garlic', 'Garlic', 'g', 'pantry', 60, 'Keep whole bulbs dry and ventilated.'],
  ['rice', 'Rice', 'g', 'pantry', 365, 'Store dry in a sealed container.'],
  ['pasta', 'Pasta', 'g', 'pantry', 365, 'Store dry in a sealed container.'],
  ['spinach', 'Spinach', 'g', 'refrigerator', 5, 'Refrigerate dry with an absorbent towel.'],
  ['chickpeas', 'Chickpeas', 'g', 'pantry', 365, 'Keep sealed; refrigerate after opening.'],
  ['chicken-breast', 'Chicken breast', 'g', 'refrigerator', 2, 'Keep cold and separate from ready-to-eat food.'],
  ['egg', 'Egg', 'each', 'refrigerator', 28, 'Keep in the original carton.'],
  ['milk', 'Milk', 'ml', 'refrigerator', 7, 'Keep refrigerated and sealed.'],
  ['cheese', 'Cheese', 'g', 'refrigerator', 14, 'Wrap and refrigerate after opening.'],
  ['banana', 'Banana', 'g', 'counter', 7, 'Keep away from other produce to slow ripening.'],
  ['oats', 'Rolled oats', 'g', 'pantry', 365, 'Store dry in a sealed container.'],
  ['bread', 'Bread', 'g', 'counter', 5, 'Keep sealed or freeze portions.'],
  ['avocado', 'Avocado', 'g', 'counter', 5, 'Keep on the counter until ripe, then refrigerate.'],
  ['bell-pepper', 'Bell pepper', 'g', 'refrigerator', 7, 'Keep dry in the crisper drawer.'],
].map(([slug, name, unit, location, days, guidance], index) => ({
  id: index + 1,
  slug: String(slug), name: String(name), base_unit: unit as Ingredient['base_unit'],
  dietary_tags: ['vegan', 'vegetarian'], allergens: slug === 'pasta' || slug === 'oats' ? ['gluten'] : [],
  recommended_storage_location: location as Ingredient['recommended_storage_location'],
  typical_shelf_life_days: Number(days), storage_instructions: String(guidance),
}))

export const demoProfile: Profile = {
  display_name: 'Alex', dietary_preferences: ['vegetarian'], allergies: [],
  preferred_cuisines: ['italian', 'asian', 'mediterranean'], preferred_tastes: ['fresh', 'savory'],
  daily_calorie_target: 2000, onboarding_completed_at: new Date().toISOString(),
  locale: 'en-NL', timezone: 'Europe/Amsterdam', currency_code: 'EUR',
}

const isoAfter = (days: number) => {
  const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10)
}

export const demoPantry: PantryItem[] = [
  [1, 500, 'g', 5, 2.8], [2, 3, 'each', 18, 1.2], [6, 200, 'g', 2, 2.2],
  [7, 400, 'g', 90, 1.5], [11, 180, 'g', 10, 3.4], [12, 5, 'each', 4, 1.9],
].map(([ingredientId, quantity, unit, days, price], index) => {
  const ingredient = demoIngredients[Number(ingredientId) - 1]
  return {
    id: index + 1, ingredient_id: ingredient.id, initial_quantity: Number(quantity),
    remaining_quantity: Number(quantity), unit: unit as PantryItem['unit'],
    storage_location: ingredient.recommended_storage_location ?? 'pantry', best_before_on: isoAfter(Number(days)),
    status: 'available', purchase_price: Number(price), currency_code: 'EUR', ingredient,
    active_storage_guidance: { storage_instructions: ingredient.storage_instructions ?? '' },
  }
})

export const demoRecipes: Recipe[] = [
  { id: 101, title: 'Banana oat breakfast', description: 'Creamy oats that rescue ripe bananas.', source: 'generated', cuisine: 'Global', category: 'Breakfast', servings: 1, prep_minutes: 5, cook_minutes: 8, instructions: ['Slice the banana.', 'Simmer oats until creamy.', 'Fold in banana and serve.'], nutrition: { calories: 320, protein: '10g' }, saved_at: new Date().toISOString(), ingredients: [{ ingredient_id: 13, quantity: 60, unit: 'g' }, { ingredient_id: 12, quantity: 120, unit: 'g' }] },
  { id: 102, title: 'Tomato basil pasta', description: 'A bright pantry-first pasta.', source: 'generated', cuisine: 'Italian', category: 'Pasta', servings: 2, prep_minutes: 8, cook_minutes: 18, instructions: ['Boil the pasta.', 'Sauté garlic and tomato.', 'Toss together and season.'], nutrition: { calories: 540, protein: '18g' }, saved_at: null, ingredients: [{ ingredient_id: 5, quantity: 180, unit: 'g' }, { ingredient_id: 1, quantity: 300, unit: 'g' }] },
  { id: 103, title: 'Mediterranean chickpea salad', description: 'Crunchy, fresh and ready in minutes.', source: 'generated', cuisine: 'Mediterranean', category: 'Salad', servings: 2, prep_minutes: 15, cook_minutes: 0, instructions: ['Rinse the chickpeas.', 'Chop the vegetables.', 'Dress, toss and serve.'], nutrition: { calories: 420, protein: '16g' }, saved_at: null, ingredients: [{ ingredient_id: 7, quantity: 240, unit: 'g' }, { ingredient_id: 6, quantity: 120, unit: 'g' }] },
]

const start = new Date(); start.setHours(0, 0, 0, 0)
const dateAt = (offset: number) => { const d = new Date(start); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10) }

export const demoGeneratedPlan: GeneratedPlan = {
  plan: {
    id: 42, name: 'FreshLoop week', start_date: dateAt(0), end_date: dateAt(4), checkout_budget: 42,
    currency_code: 'EUR', selected_meal_types: ['breakfast', 'lunch', 'dinner'], status: 'ready',
    meals: Array.from({ length: 5 }, (_, day) => demoRecipes.map((recipe, mealIndex) => ({
      id: day * 3 + mealIndex + 1, meal_date: dateAt(day), meal_type: ['breakfast', 'lunch', 'dinner'][mealIndex] as 'breakfast' | 'lunch' | 'dinner',
      requested_cuisine: day === 0 ? 'Italian' : ['Asian', 'Mediterranean', 'Indian', 'Global'][day - 1],
      requested_category: ['Breakfast', 'Salad', 'Pasta'][mealIndex], recipe_id: recipe.id,
      servings: 1, status: 'generated' as const,
    }))).flat(),
  },
  recipes: demoRecipes,
  shopping_list: {
    id: 22, meal_plan_id: 42, currency_code: 'EUR', estimated_total: 38.2, status: 'active',
    items: [
      [1, 500, 500, 0, 'g', null], [16, 300, 0, 300, 'g', 2.1], [6, 200, 200, 0, 'g', null],
      [8, 600, 600, 0, 'g', null], [7, 400, 200, 200, 'g', 1.5], [9, 6, 0, 6, 'each', 2.7],
    ].map(([ingredientId, required, pantry, buy, unit, price], index) => ({
      id: index + 1, ingredient_id: Number(ingredientId), custom_label: null, source: 'generated' as const,
      required_quantity: Number(required), pantry_quantity: Number(pantry), to_buy_quantity: Number(buy),
      unit: unit as 'g' | 'each', needed_by_date: dateAt(index > 3 ? 3 : 0),
      estimated_price: price === null ? null : Number(price), status: 'pending' as const,
    })),
  },
}

export const demoReceipt: Receipt = {
  id: 88, merchant_name: 'Carrefour', purchased_at: new Date().toISOString(), total_amount: 38.2,
  currency_code: 'EUR', status: 'review', items: demoGeneratedPlan.shopping_list.items.map((item, index) => ({
    id: index + 1, line_number: index + 1,
    raw_text: demoIngredients.find((ingredient) => ingredient.id === item.ingredient_id)?.name ?? 'Grocery item',
    ingredient_id: item.ingredient_id, quantity: item.required_quantity, unit: item.unit,
    unit_price: item.estimated_price, line_total: item.estimated_price,
    match_confidence: Math.max(.86, .98 - index * .02), review_status: 'accepted',
  })),
}

export const demoImpact: ImpactSummary = {
  week_start: dateAt(-5), week_end: dateAt(1), currency_code: 'EUR', spent_amount: 38.2,
  estimated_saved_amount: 12.4, estimated_food_saved_g: 1800, pantry_items_used: 8,
  previous_week_food_saved_g: 1100, streak_weeks: 4,
}

export const demoDeals = [
  { retailer: 'Albert Heijn', item: 'Bell peppers', price: '€1.49', note: 'Demo offer' },
  { retailer: 'Lidl', item: 'Chickpeas', price: '€0.79', note: 'Demo offer' },
  { retailer: 'Jumbo', item: 'Free-range eggs', price: '€2.29', note: 'Demo offer' },
]
