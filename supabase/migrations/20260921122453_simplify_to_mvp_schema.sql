-- Replace the initial normalized schema with the agreed 12-table MVP schema.
-- This migration intentionally deletes data from the initial public tables.

set statement_timeout = '30s';

drop view if exists public.weekly_actuals cascade;
drop view if exists public.current_pantry cascade;

drop function if exists public.rebuild_shopping_list(bigint) cascade;
drop function if exists public.record_inventory_change(
  bigint, text, numeric, text, text, timestamptz
) cascade;
drop function if exists public.confirm_receipt(bigint) cascade;
drop function if exists public.add_pantry_lot(
  bigint, numeric, text, bigint, text, timestamptz, date, numeric, text
) cascade;
drop function if exists public.publish_recipe_version(bigint) cascade;
drop function if exists public.validate_meal_plan_recipe_version() cascade;
drop function if exists public.validate_ingredient_base_unit() cascade;
drop function if exists public.protect_published_recipe_component() cascade;
drop function if exists public.protect_published_recipe_version() cascade;
drop function if exists public.handle_new_user() cascade;
drop function if exists public.set_updated_at() cascade;

drop table if exists
  public.shopping_list_item_sources,
  public.shopping_list_items,
  public.shopping_lists,
  public.weekly_impact_summaries,
  public.ai_runs,
  public.inventory_events,
  public.pantry_lots,
  public.receipt_lines,
  public.receipts,
  public.meal_plan_slots,
  public.meal_plans,
  public.recipe_steps,
  public.recipe_ingredients,
  public.recipe_versions,
  public.recipes,
  public.user_cuisine_preferences,
  public.user_allergies,
  public.user_dietary_preferences,
  public.profiles,
  public.ingredient_storage_guidance,
  public.product_ingredient_mappings,
  public.products,
  public.ingredient_dietary_tags,
  public.ingredient_allergens,
  public.ingredient_aliases,
  public.ingredients,
  public.retailers,
  public.meal_categories,
  public.cuisines,
  public.allergens,
  public.dietary_tags,
  public.measurement_units
cascade;

-- 1. User profile and onboarding preferences.
create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  dietary_preferences text[] not null default '{}',
  allergies jsonb not null default '[]'::jsonb
    check (jsonb_typeof(allergies) = 'array'),
  preferred_cuisines text[] not null default '{}',
  activity_level text check (
    activity_level in ('sedentary', 'light', 'moderate', 'very_active', 'athlete')
  ),
  daily_calorie_target integer check (daily_calorie_target between 500 and 10000),
  locale text not null default 'en-NL',
  timezone text not null default 'Europe/Amsterdam',
  currency_code text not null default 'EUR' check (currency_code ~ '^[A-Z]{3}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. Shared canonical ingredient catalog, including storage guidance.
create table public.ingredients (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  base_unit text not null check (base_unit in ('g', 'ml', 'each')),
  dietary_tags text[] not null default '{}',
  allergens text[] not null default '{}',
  recommended_storage_location text check (
    recommended_storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')
  ),
  typical_shelf_life_days integer check (typical_shelf_life_days >= 0),
  storage_instructions text,
  density_g_per_ml numeric(12, 6) check (density_g_per_ml > 0),
  average_unit_weight_g numeric(12, 4) check (average_unit_weight_g > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. Private user recipes. Instructions and nutrition are compact JSON payloads.
create table public.recipes (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  title text not null,
  description text,
  source text not null default 'manual' check (source in ('manual', 'generated')),
  cuisine text,
  category text,
  servings numeric(8, 2) not null default 1 check (servings > 0),
  prep_minutes integer not null default 0 check (prep_minutes >= 0),
  cook_minutes integer not null default 0 check (cook_minutes >= 0),
  instructions jsonb not null default '[]'::jsonb
    check (jsonb_typeof(instructions) = 'array'),
  nutrition jsonb not null default '{}'::jsonb
    check (jsonb_typeof(nutrition) = 'object'),
  saved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

-- 4. Normalized recipe quantities in the ingredient's canonical base unit.
create table public.recipe_ingredients (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  recipe_id bigint not null,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  position integer not null check (position > 0),
  quantity numeric(14, 4) not null check (quantity > 0),
  unit text not null check (unit in ('g', 'ml', 'each')),
  preparation_note text,
  optional boolean not null default false,
  created_at timestamptz not null default now(),
  unique (recipe_id, position),
  foreign key (recipe_id, user_id)
    references public.recipes(id, user_id) on delete cascade
);

-- 5. One meal-planning request and its budget/settings.
create table public.meal_plans (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  name text,
  start_date date not null,
  end_date date not null,
  checkout_budget numeric(12, 2) check (checkout_budget >= 0),
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  selected_meal_types text[] not null default array['dinner']::text[],
  status text not null default 'draft' check (
    status in ('draft', 'generating', 'ready', 'active', 'completed', 'archived', 'failed')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  check (end_date between start_date and start_date + 31),
  check (selected_meal_types <@ array['breakfast', 'lunch', 'dinner']::text[])
);

-- 6. Daily breakfast/lunch/dinner assignments for a plan.
create table public.meal_plan_meals (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  meal_plan_id bigint not null,
  meal_date date not null,
  meal_type text not null check (meal_type in ('breakfast', 'lunch', 'dinner')),
  requested_cuisine text,
  requested_category text,
  recipe_id bigint,
  servings numeric(8, 2) not null default 1 check (servings > 0),
  status text not null default 'requested' check (
    status in ('requested', 'generated', 'accepted', 'cooked', 'skipped')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (meal_plan_id, meal_date, meal_type),
  unique (id, user_id),
  foreign key (meal_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade,
  foreign key (recipe_id, user_id)
    references public.recipes(id, user_id) on delete restrict
);

-- 7. Receipt metadata and private Storage object reference.
create table public.receipts (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  merchant_name text,
  purchased_at timestamptz,
  total_amount numeric(12, 2) check (total_amount >= 0),
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  image_path text,
  image_delete_after timestamptz,
  status text not null default 'uploaded' check (
    status in ('uploaded', 'processing', 'review', 'confirmed', 'failed')
  ),
  raw_ocr jsonb not null default '{}'::jsonb,
  failure_reason text,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

-- 8. AI-extracted lines, reviewed before they enter the pantry.
create table public.receipt_items (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  receipt_id bigint not null,
  line_number integer not null check (line_number > 0),
  raw_text text not null,
  ingredient_id bigint references public.ingredients(id) on delete set null,
  quantity numeric(14, 4) check (quantity > 0),
  unit text check (unit in ('g', 'ml', 'each')),
  unit_price numeric(12, 4) check (unit_price >= 0),
  line_total numeric(12, 2) check (line_total >= 0),
  match_confidence numeric(5, 4) check (match_confidence between 0 and 1),
  review_status text not null default 'pending' check (
    review_status in ('pending', 'accepted', 'corrected', 'ignored')
  ),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (receipt_id, line_number),
  unique (id, user_id),
  foreign key (receipt_id, user_id)
    references public.receipts(id, user_id) on delete cascade
);

-- 9. Current at-home inventory, one row per acquired batch.
create table public.pantry_items (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  receipt_item_id bigint unique,
  initial_quantity numeric(14, 4) not null check (initial_quantity > 0),
  remaining_quantity numeric(14, 4) not null check (remaining_quantity >= 0),
  unit text not null check (unit in ('g', 'ml', 'each')),
  storage_location text not null default 'pantry' check (
    storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')
  ),
  acquired_at timestamptz not null default now(),
  best_before_on date,
  opened_at timestamptz,
  purchase_price numeric(12, 2) check (purchase_price >= 0),
  currency_code text check (currency_code ~ '^[A-Z]{3}$'),
  status text not null default 'available' check (
    status in ('available', 'depleted', 'discarded')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (receipt_item_id, user_id)
    references public.receipt_items(id, user_id) on delete restrict,
  check (remaining_quantity <= initial_quantity),
  check ((purchase_price is null) = (currency_code is null))
);

-- 10. One persisted list per meal plan.
create table public.shopping_lists (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  meal_plan_id bigint not null unique,
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  estimated_total numeric(12, 2) check (estimated_total >= 0),
  status text not null default 'active' check (
    status in ('active', 'completed', 'archived')
  ),
  calculated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (meal_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade
);

-- 11. Generated missing items plus optional manual list entries.
create table public.shopping_list_items (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  shopping_list_id bigint not null,
  ingredient_id bigint references public.ingredients(id) on delete restrict,
  custom_label text,
  source text not null default 'generated' check (source in ('generated', 'manual')),
  required_quantity numeric(14, 4) not null default 0 check (required_quantity >= 0),
  pantry_quantity numeric(14, 4) not null default 0 check (pantry_quantity >= 0),
  to_buy_quantity numeric(14, 4) not null default 0 check (to_buy_quantity >= 0),
  unit text check (unit in ('g', 'ml', 'each')),
  needed_by_date date,
  estimated_price numeric(12, 2) check (estimated_price >= 0),
  status text not null default 'pending' check (status in ('pending', 'bought', 'skipped')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (shopping_list_id, user_id)
    references public.shopping_lists(id, user_id) on delete cascade,
  check (num_nonnulls(ingredient_id, nullif(btrim(custom_label), '')) = 1),
  check (
    source = 'manual'
    or abs(required_quantity - pantry_quantity - to_buy_quantity) < 0.0001
  )
);

create unique index shopping_list_generated_ingredient_idx
  on public.shopping_list_items (shopping_list_id, ingredient_id, unit)
  where source = 'generated';

-- 12. Explicit waste records used by the dashboard and weekly summary.
create table public.waste_events (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  pantry_item_id bigint not null,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  quantity numeric(14, 4) not null check (quantity > 0),
  unit text not null check (unit in ('g', 'ml', 'each')),
  reason text not null check (reason in ('expired', 'spoiled', 'unused', 'other')),
  estimated_value numeric(12, 2) check (estimated_value >= 0),
  estimated_weight_g numeric(14, 4) check (estimated_weight_g >= 0),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (pantry_item_id, user_id)
    references public.pantry_items(id, user_id) on delete restrict
);

-- Index ownership and foreign-key columns used by RLS and common queries.
create index recipes_user_created_idx on public.recipes (user_id, created_at desc);
create index recipe_ingredients_user_idx on public.recipe_ingredients (user_id);
create index recipe_ingredients_ingredient_idx on public.recipe_ingredients (ingredient_id);
create index meal_plans_user_start_idx on public.meal_plans (user_id, start_date desc);
create index meal_plan_meals_user_date_idx on public.meal_plan_meals (user_id, meal_date);
create index meal_plan_meals_recipe_idx on public.meal_plan_meals (recipe_id)
  where recipe_id is not null;
create index receipts_user_purchased_idx on public.receipts (user_id, purchased_at desc);
create index receipt_items_user_idx on public.receipt_items (user_id);
create index receipt_items_ingredient_idx on public.receipt_items (ingredient_id)
  where ingredient_id is not null;
create index pantry_items_user_ingredient_expiry_idx
  on public.pantry_items (user_id, ingredient_id, best_before_on);
create index shopping_lists_user_idx on public.shopping_lists (user_id);
create index shopping_list_items_user_status_idx
  on public.shopping_list_items (user_id, shopping_list_id, status);
create index shopping_list_items_ingredient_idx on public.shopping_list_items (ingredient_id)
  where ingredient_id is not null;
create index waste_events_user_occurred_idx on public.waste_events (user_id, occurred_at desc);
create index waste_events_ingredient_idx on public.waste_events (ingredient_id);

-- Keep updated_at consistent.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at before update on public.profiles
for each row execute function public.set_updated_at();
create trigger ingredients_set_updated_at before update on public.ingredients
for each row execute function public.set_updated_at();
create trigger recipes_set_updated_at before update on public.recipes
for each row execute function public.set_updated_at();
create trigger meal_plans_set_updated_at before update on public.meal_plans
for each row execute function public.set_updated_at();
create trigger meal_plan_meals_set_updated_at before update on public.meal_plan_meals
for each row execute function public.set_updated_at();
create trigger receipts_set_updated_at before update on public.receipts
for each row execute function public.set_updated_at();
create trigger receipt_items_set_updated_at before update on public.receipt_items
for each row execute function public.set_updated_at();
create trigger pantry_items_set_updated_at before update on public.pantry_items
for each row execute function public.set_updated_at();
create trigger shopping_lists_set_updated_at before update on public.shopping_lists
for each row execute function public.set_updated_at();
create trigger shopping_list_items_set_updated_at before update on public.shopping_list_items
for each row execute function public.set_updated_at();

-- Auth creates the application profile. Backfill any users created before this migration.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id, display_name)
  values (
    new.id,
    nullif(btrim(coalesce(new.raw_user_meta_data ->> 'display_name', '')), '')
  )
  on conflict (user_id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

insert into public.profiles (user_id, display_name)
select
  id,
  nullif(btrim(coalesce(raw_user_meta_data ->> 'display_name', '')), '')
from auth.users
on conflict (user_id) do nothing;

-- Cross-table checks that cannot be expressed as ordinary constraints.
create or replace function public.validate_mvp_row()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_expected_unit text;
begin
  if tg_table_name in ('recipe_ingredients', 'receipt_items', 'pantry_items')
     and new.ingredient_id is not null
     and new.unit is not null then
    select base_unit into v_expected_unit
    from public.ingredients
    where id = new.ingredient_id;

    if v_expected_unit is distinct from new.unit then
      raise exception 'Quantity unit must match the ingredient base unit';
    end if;
  end if;

  if tg_table_name = 'meal_plan_meals' then
    if not exists (
      select 1 from public.meal_plans
      where id = new.meal_plan_id
        and user_id = new.user_id
        and new.meal_date between start_date and end_date
    ) then
      raise exception 'Meal date must fall inside the owning meal plan';
    end if;
  end if;

  return new;
end;
$$;

create trigger recipe_ingredients_validate before insert or update on public.recipe_ingredients
for each row execute function public.validate_mvp_row();
create trigger receipt_items_validate before insert or update on public.receipt_items
for each row execute function public.validate_mvp_row();
create trigger pantry_items_validate before insert or update on public.pantry_items
for each row execute function public.validate_mvp_row();
create trigger meal_plan_meals_validate before insert or update on public.meal_plan_meals
for each row execute function public.validate_mvp_row();

-- Review-gated receipt import.
create or replace function public.confirm_receipt(p_receipt_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_receipt public.receipts;
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;

  select * into v_receipt
  from public.receipts
  where id = p_receipt_id and user_id = v_user_id
  for update;

  if not found then raise exception 'Receipt not found'; end if;
  if v_receipt.status = 'confirmed' then return; end if;
  if v_receipt.status <> 'review' then
    raise exception 'Receipt must be in review before confirmation';
  end if;

  if not exists (
    select 1 from public.receipt_items
    where receipt_id = p_receipt_id
      and user_id = v_user_id
      and review_status in ('accepted', 'corrected')
  ) then
    raise exception 'Receipt has no accepted items';
  end if;

  if exists (
    select 1 from public.receipt_items
    where receipt_id = p_receipt_id
      and user_id = v_user_id
      and review_status in ('accepted', 'corrected')
      and (ingredient_id is null or quantity is null or unit is null)
  ) then
    raise exception 'Accepted items need an ingredient, quantity, and unit';
  end if;

  insert into public.pantry_items (
    user_id,
    ingredient_id,
    receipt_item_id,
    initial_quantity,
    remaining_quantity,
    unit,
    storage_location,
    acquired_at,
    best_before_on,
    purchase_price,
    currency_code
  )
  select
    ri.user_id,
    ri.ingredient_id,
    ri.id,
    ri.quantity,
    ri.quantity,
    ri.unit,
    coalesce(i.recommended_storage_location, 'pantry'),
    coalesce(v_receipt.purchased_at, now()),
    case when i.typical_shelf_life_days is null then null
      else coalesce(v_receipt.purchased_at, now())::date + i.typical_shelf_life_days end,
    ri.line_total,
    v_receipt.currency_code
  from public.receipt_items ri
  join public.ingredients i on i.id = ri.ingredient_id
  where ri.receipt_id = p_receipt_id
    and ri.user_id = v_user_id
    and ri.review_status in ('accepted', 'corrected')
  on conflict (receipt_item_id) do nothing;

  update public.receipts
  set status = 'confirmed',
      confirmed_at = now(),
      image_delete_after = now() + interval '30 days'
  where id = p_receipt_id;
end;
$$;

-- Atomically decrement pantry stock and record waste.
create or replace function public.record_waste(
  p_pantry_item_id bigint,
  p_quantity numeric,
  p_reason text,
  p_occurred_at timestamptz default now()
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_item public.pantry_items;
  v_density numeric;
  v_unit_weight numeric;
  v_event_id bigint;
  v_estimated_value numeric;
  v_estimated_weight numeric;
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;
  if p_quantity <= 0 then raise exception 'Waste quantity must be positive'; end if;

  select * into v_item
  from public.pantry_items
  where id = p_pantry_item_id and user_id = v_user_id
  for update;

  if not found then raise exception 'Pantry item not found'; end if;
  if p_quantity > v_item.remaining_quantity then
    raise exception 'Waste quantity exceeds remaining pantry quantity';
  end if;

  if v_item.purchase_price is not null then
    v_estimated_value := round(
      p_quantity * v_item.purchase_price / v_item.initial_quantity,
      2
    );
  end if;

  select density_g_per_ml, average_unit_weight_g
  into v_density, v_unit_weight
  from public.ingredients where id = v_item.ingredient_id;

  v_estimated_weight := case v_item.unit
    when 'g' then p_quantity
    when 'ml' then p_quantity * v_density
    when 'each' then p_quantity * v_unit_weight
    else null
  end;

  update public.pantry_items
  set remaining_quantity = remaining_quantity - p_quantity,
      status = case when remaining_quantity - p_quantity = 0
        then 'discarded' else status end
  where id = p_pantry_item_id;

  insert into public.waste_events (
    user_id,
    pantry_item_id,
    ingredient_id,
    quantity,
    unit,
    reason,
    estimated_value,
    estimated_weight_g,
    occurred_at
  ) values (
    v_user_id,
    v_item.id,
    v_item.ingredient_id,
    p_quantity,
    v_item.unit,
    p_reason,
    v_estimated_value,
    v_estimated_weight,
    p_occurred_at
  ) returning id into v_event_id;

  return v_event_id;
end;
$$;

-- Recreate the generated part of a shopping list from recipes minus current pantry stock.
create or replace function public.rebuild_shopping_list(p_meal_plan_id bigint)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_plan public.meal_plans;
  v_list_id bigint;
begin
  if v_user_id is null then raise exception 'Authentication required'; end if;

  select * into v_plan
  from public.meal_plans
  where id = p_meal_plan_id and user_id = v_user_id
  for update;

  if not found then raise exception 'Meal plan not found'; end if;
  if exists (
    select 1 from public.meal_plan_meals
    where meal_plan_id = p_meal_plan_id
      and user_id = v_user_id
      and status <> 'skipped'
      and recipe_id is null
  ) then
    raise exception 'Every active planned meal needs a recipe';
  end if;

  insert into public.shopping_lists (
    user_id, meal_plan_id, currency_code, calculated_at
  ) values (
    v_user_id, p_meal_plan_id, v_plan.currency_code, now()
  )
  on conflict (meal_plan_id) do update
  set currency_code = excluded.currency_code,
      calculated_at = now(),
      updated_at = now()
  returning id into v_list_id;

  delete from public.shopping_list_items
  where shopping_list_id = v_list_id
    and user_id = v_user_id
    and source = 'generated';

  with requirements as (
    select
      ri.ingredient_id,
      ri.unit,
      round(sum(ri.quantity * mpm.servings / r.servings), 4) as required_quantity,
      min(mpm.meal_date) as needed_by_date
    from public.meal_plan_meals mpm
    join public.recipes r on r.id = mpm.recipe_id and r.user_id = mpm.user_id
    join public.recipe_ingredients ri on ri.recipe_id = r.id and ri.user_id = r.user_id
    where mpm.meal_plan_id = p_meal_plan_id
      and mpm.user_id = v_user_id
      and mpm.status <> 'skipped'
      and not ri.optional
    group by ri.ingredient_id, ri.unit
  ), pantry as (
    select ingredient_id, unit, sum(remaining_quantity) as available_quantity
    from public.pantry_items
    where user_id = v_user_id
      and status = 'available'
      and remaining_quantity > 0
      and (best_before_on is null or best_before_on >= v_plan.start_date)
    group by ingredient_id, unit
  ), latest_prices as (
    select distinct on (ri.ingredient_id, ri.unit)
      ri.ingredient_id,
      ri.unit,
      ri.line_total / ri.quantity as unit_cost
    from public.receipt_items ri
    join public.receipts receipt
      on receipt.id = ri.receipt_id and receipt.user_id = ri.user_id
    where ri.user_id = v_user_id
      and receipt.status = 'confirmed'
      and receipt.currency_code = v_plan.currency_code
      and ri.ingredient_id is not null
      and ri.quantity > 0
      and ri.line_total is not null
    order by ri.ingredient_id, ri.unit, coalesce(receipt.purchased_at, receipt.created_at) desc
  )
  insert into public.shopping_list_items (
    user_id,
    shopping_list_id,
    ingredient_id,
    source,
    required_quantity,
    pantry_quantity,
    to_buy_quantity,
    unit,
    needed_by_date,
    estimated_price
  )
  select
    v_user_id,
    v_list_id,
    req.ingredient_id,
    'generated',
    req.required_quantity,
    least(req.required_quantity, coalesce(p.available_quantity, 0)),
    greatest(req.required_quantity - coalesce(p.available_quantity, 0), 0),
    req.unit,
    req.needed_by_date,
    round(
      greatest(req.required_quantity - coalesce(p.available_quantity, 0), 0)
      * prices.unit_cost,
      2
    )
  from requirements req
  left join pantry p
    on p.ingredient_id = req.ingredient_id and p.unit = req.unit
  left join latest_prices prices
    on prices.ingredient_id = req.ingredient_id and prices.unit = req.unit;

  update public.shopping_lists
  set estimated_total = (
        select coalesce(sum(estimated_price), 0)
        from public.shopping_list_items
        where shopping_list_id = v_list_id and user_id = v_user_id
      ),
      calculated_at = now()
  where id = v_list_id;

  return v_list_id;
end;
$$;

-- RLS: the ingredient catalog is shared read-only; every other table is private.
alter table public.ingredients enable row level security;
create policy ingredients_authenticated_read on public.ingredients
for select to authenticated using (true);

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'profiles',
    'recipes',
    'recipe_ingredients',
    'meal_plans',
    'meal_plan_meals',
    'receipts',
    'receipt_items',
    'pantry_items',
    'shopping_lists',
    'shopping_list_items',
    'waste_events'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format(
      'create policy %I on public.%I for all to authenticated '
      || 'using ((select auth.uid()) = user_id) '
      || 'with check ((select auth.uid()) = user_id)',
      table_name || '_owner_access',
      table_name
    );
  end loop;
end;
$$;

revoke all on all tables in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

grant select on public.ingredients to authenticated;
grant select, update on public.profiles to authenticated;
grant select, insert, update, delete on
  public.recipes,
  public.recipe_ingredients,
  public.meal_plans,
  public.meal_plan_meals,
  public.receipts,
  public.receipt_items,
  public.pantry_items,
  public.shopping_lists,
  public.shopping_list_items
to authenticated;
grant select on public.waste_events to authenticated;
grant usage, select on all sequences in schema public to authenticated;

grant execute on function public.confirm_receipt(bigint) to authenticated;
grant execute on function public.record_waste(bigint, numeric, text, timestamptz)
  to authenticated;
grant execute on function public.rebuild_shopping_list(bigint) to authenticated;

-- Small demo catalog; the backend/service role can extend it later.
insert into public.ingredients (
  slug,
  name,
  base_unit,
  dietary_tags,
  allergens,
  recommended_storage_location,
  typical_shelf_life_days,
  storage_instructions,
  density_g_per_ml,
  average_unit_weight_g
) values
  ('tomato', 'Tomato', 'g', array['vegan', 'vegetarian'], '{}', 'counter', 7, 'Keep away from direct sunlight; refrigerate once fully ripe if needed.', null, 120),
  ('onion', 'Onion', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 30, 'Store in a cool, dry, ventilated place.', null, 110),
  ('garlic', 'Garlic', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 60, 'Keep whole bulbs dry and ventilated.', null, 4),
  ('rice', 'Rice', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Store dry in a sealed container.', null, null),
  ('pasta', 'Pasta', 'g', array['vegetarian'], array['gluten'], 'pantry', 365, 'Store dry in a sealed container.', null, null),
  ('potato', 'Potato', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 21, 'Keep cool, dark, dry, and away from onions.', null, 170),
  ('carrot', 'Carrot', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 21, 'Refrigerate dry in a ventilated bag.', null, 70),
  ('broccoli', 'Broccoli', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 5, 'Refrigerate unwashed in a loose bag.', null, null),
  ('spinach', 'Spinach', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 5, 'Refrigerate dry with an absorbent towel.', null, null),
  ('chickpeas', 'Chickpeas', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Store dry or canned chickpeas according to package guidance.', null, null),
  ('lentils', 'Lentils', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Store dry in a sealed container.', null, null),
  ('tofu', 'Tofu', 'g', array['vegan', 'vegetarian'], array['soybeans'], 'refrigerator', 7, 'Keep refrigerated and use promptly after opening.', null, null),
  ('chicken-breast', 'Chicken breast', 'g', '{}', '{}', 'refrigerator', 2, 'Keep refrigerated and separate from ready-to-eat food.', null, null),
  ('salmon', 'Salmon', 'g', '{}', array['fish'], 'refrigerator', 2, 'Keep refrigerated and use promptly.', null, null),
  ('egg', 'Egg', 'each', array['vegetarian'], array['eggs'], 'refrigerator', 28, 'Keep refrigerated in the original carton.', null, 60),
  ('milk', 'Milk', 'ml', array['vegetarian'], array['milk'], 'refrigerator', 7, 'Keep refrigerated and follow the package date.', 1.03, null),
  ('yogurt', 'Yogurt', 'g', array['vegetarian'], array['milk'], 'refrigerator', 10, 'Keep refrigerated and sealed.', null, null),
  ('cheese', 'Cheese', 'g', array['vegetarian'], array['milk'], 'refrigerator', 14, 'Wrap and refrigerate after opening.', null, null),
  ('bread', 'Bread', 'g', array['vegetarian'], array['gluten'], 'counter', 5, 'Keep sealed or freeze portions.', null, 35),
  ('olive-oil', 'Olive oil', 'ml', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Store sealed away from heat and light.', 0.91, null);
