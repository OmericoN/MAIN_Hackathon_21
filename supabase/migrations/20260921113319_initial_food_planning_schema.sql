-- Initial schema for the food-planning and waste-reduction application.
-- Supabase Auth owns identities; public.profiles owns application-specific user data.

set statement_timeout = '30s';

-- -----------------------------------------------------------------------------
-- Shared catalog and profile tables
-- -----------------------------------------------------------------------------

create table public.measurement_units (
  code text primary key,
  name text not null,
  dimension text not null check (dimension in ('mass', 'volume', 'count')),
  factor_to_base numeric(18, 8) not null check (factor_to_base > 0),
  created_at timestamptz not null default now()
);

create table public.dietary_tags (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.allergens (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.cuisines (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.meal_categories (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  created_at timestamptz not null default now()
);

create table public.retailers (
  id bigint generated always as identity primary key,
  name text not null,
  normalized_name text not null unique,
  external_provider text,
  external_id text,
  created_at timestamptz not null default now()
);

create unique index retailers_external_identity_idx
  on public.retailers (external_provider, external_id)
  where external_provider is not null and external_id is not null;

create table public.ingredients (
  id bigint generated always as identity primary key,
  slug text not null unique,
  name text not null,
  base_unit_code text not null references public.measurement_units(code),
  density_g_per_ml numeric(12, 6) check (density_g_per_ml > 0),
  average_unit_weight_g numeric(12, 4) check (average_unit_weight_g > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (base_unit_code in ('g', 'ml', 'each'))
);

create table public.ingredient_aliases (
  id bigint generated always as identity primary key,
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  alias text not null,
  normalized_alias text not null unique,
  source text not null default 'system' check (source in ('system', 'ocr', 'admin')),
  created_at timestamptz not null default now()
);

create table public.ingredient_allergens (
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  allergen_id bigint not null references public.allergens(id) on delete restrict,
  primary key (ingredient_id, allergen_id)
);

create table public.ingredient_dietary_tags (
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  dietary_tag_id bigint not null references public.dietary_tags(id) on delete restrict,
  primary key (ingredient_id, dietary_tag_id)
);

create table public.products (
  id bigint generated always as identity primary key,
  name text not null,
  brand text,
  barcode text unique,
  package_quantity numeric(12, 4) check (package_quantity > 0),
  package_unit_code text references public.measurement_units(code),
  external_provider text,
  external_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index products_external_identity_idx
  on public.products (external_provider, external_id)
  where external_provider is not null and external_id is not null;

create table public.product_ingredient_mappings (
  product_id bigint not null references public.products(id) on delete cascade,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  is_primary boolean not null default false,
  confidence numeric(5, 4) check (confidence between 0 and 1),
  primary key (product_id, ingredient_id)
);

create unique index product_one_primary_ingredient_idx
  on public.product_ingredient_mappings (product_id)
  where is_primary;

create table public.ingredient_storage_guidance (
  id bigint generated always as identity primary key,
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  storage_location text not null check (
    storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')
  ),
  unopened_min_days integer check (unopened_min_days >= 0),
  unopened_max_days integer check (unopened_max_days >= unopened_min_days),
  opened_min_days integer check (opened_min_days >= 0),
  opened_max_days integer check (opened_max_days >= opened_min_days),
  instructions text not null,
  source_url text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ingredient_id, storage_location)
);

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  daily_calorie_target integer check (daily_calorie_target between 500 and 10000),
  activity_level text check (
    activity_level in ('sedentary', 'light', 'moderate', 'very_active', 'athlete')
  ),
  locale text not null default 'en-NL',
  timezone text not null default 'Europe/Amsterdam',
  currency_code text not null default 'EUR' check (currency_code ~ '^[A-Z]{3}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.user_dietary_preferences (
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  dietary_tag_id bigint not null references public.dietary_tags(id) on delete restrict,
  created_at timestamptz not null default now(),
  primary key (user_id, dietary_tag_id)
);

create table public.user_allergies (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  allergen_id bigint references public.allergens(id) on delete restrict,
  custom_label text,
  severity text not null default 'allergy' check (
    severity in ('preference', 'intolerance', 'allergy', 'severe_allergy')
  ),
  notes text,
  created_at timestamptz not null default now(),
  check (num_nonnulls(allergen_id, nullif(btrim(custom_label), '')) = 1)
);

create unique index user_allergies_standard_unique_idx
  on public.user_allergies (user_id, allergen_id)
  where allergen_id is not null;

create unique index user_allergies_custom_unique_idx
  on public.user_allergies (user_id, lower(custom_label))
  where custom_label is not null;

create table public.user_cuisine_preferences (
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  cuisine_id bigint not null references public.cuisines(id) on delete restrict,
  preference text not null default 'preferred' check (preference in ('preferred', 'avoid')),
  rank smallint check (rank > 0),
  created_at timestamptz not null default now(),
  primary key (user_id, cuisine_id)
);

-- -----------------------------------------------------------------------------
-- Recipes and meal planning
-- -----------------------------------------------------------------------------

create table public.recipes (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  title text not null,
  source text not null default 'manual' check (source in ('manual', 'generated')),
  current_version_id bigint,
  saved_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create table public.recipe_versions (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  recipe_id bigint not null,
  version_number integer not null check (version_number > 0),
  status text not null default 'draft' check (status in ('draft', 'published')),
  description text,
  servings numeric(8, 2) not null check (servings > 0),
  prep_minutes integer not null default 0 check (prep_minutes >= 0),
  cook_minutes integer not null default 0 check (cook_minutes >= 0),
  cuisine_id bigint references public.cuisines(id) on delete set null,
  meal_category_id bigint references public.meal_categories(id) on delete set null,
  calories_per_serving numeric(10, 2) check (calories_per_serving >= 0),
  protein_g_per_serving numeric(10, 2) check (protein_g_per_serving >= 0),
  carbohydrates_g_per_serving numeric(10, 2) check (carbohydrates_g_per_serving >= 0),
  fat_g_per_serving numeric(10, 2) check (fat_g_per_serving >= 0),
  fiber_g_per_serving numeric(10, 2) check (fiber_g_per_serving >= 0),
  generation_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (id, user_id),
  unique (recipe_id, version_number),
  foreign key (recipe_id, user_id)
    references public.recipes(id, user_id) on delete cascade
);

alter table public.recipes
  add constraint recipes_current_version_fkey
  foreign key (current_version_id) references public.recipe_versions(id) on delete set null;

create table public.recipe_ingredients (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  recipe_version_id bigint not null,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  position integer not null check (position > 0),
  display_quantity numeric(12, 4) not null check (display_quantity > 0),
  display_unit_code text not null references public.measurement_units(code),
  base_quantity numeric(14, 4) not null check (base_quantity > 0),
  base_unit_code text not null references public.measurement_units(code),
  preparation_note text,
  optional boolean not null default false,
  created_at timestamptz not null default now(),
  unique (recipe_version_id, position),
  foreign key (recipe_version_id, user_id)
    references public.recipe_versions(id, user_id) on delete cascade,
  check (base_unit_code in ('g', 'ml', 'each'))
);

create table public.recipe_steps (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  recipe_version_id bigint not null,
  step_number integer not null check (step_number > 0),
  instruction text not null check (btrim(instruction) <> ''),
  created_at timestamptz not null default now(),
  unique (recipe_version_id, step_number),
  foreign key (recipe_version_id, user_id)
    references public.recipe_versions(id, user_id) on delete cascade
);

create table public.meal_plans (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  name text,
  start_date date not null,
  end_date date not null,
  target_checkout_budget numeric(12, 2) check (target_checkout_budget >= 0),
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  status text not null default 'draft' check (
    status in ('draft', 'generating', 'ready', 'active', 'completed', 'archived', 'failed')
  ),
  pantry_snapshot_at timestamptz,
  generation_version text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  check (end_date >= start_date),
  check (end_date <= start_date + 31)
);

create table public.meal_plan_slots (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  meal_plan_id bigint not null,
  meal_date date not null,
  meal_type text not null check (meal_type in ('breakfast', 'lunch', 'dinner')),
  requested_cuisine_id bigint references public.cuisines(id) on delete set null,
  requested_category_id bigint references public.meal_categories(id) on delete set null,
  servings numeric(8, 2) not null default 1 check (servings > 0),
  recipe_version_id bigint,
  status text not null default 'requested' check (
    status in ('requested', 'generated', 'accepted', 'cooked', 'skipped')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (meal_plan_id, meal_date, meal_type),
  unique (id, user_id),
  foreign key (meal_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade,
  foreign key (recipe_version_id, user_id)
    references public.recipe_versions(id, user_id) on delete restrict
);

-- -----------------------------------------------------------------------------
-- Receipts, pantry inventory, and shopping lists
-- -----------------------------------------------------------------------------

create table public.receipts (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  retailer_id bigint references public.retailers(id) on delete set null,
  merchant_name_raw text,
  purchased_at timestamptz,
  total_amount numeric(12, 2) check (total_amount >= 0),
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  image_path text,
  image_delete_after timestamptz,
  status text not null default 'uploaded' check (
    status in ('uploaded', 'processing', 'review', 'confirmed', 'failed')
  ),
  raw_ocr jsonb not null default '{}'::jsonb,
  extraction_version text,
  failure_reason text,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create table public.receipt_lines (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  receipt_id bigint not null,
  line_number integer not null check (line_number > 0),
  raw_text text not null,
  detected_quantity numeric(12, 4) check (detected_quantity > 0),
  detected_unit_code text references public.measurement_units(code),
  unit_price numeric(12, 4) check (unit_price >= 0),
  line_total numeric(12, 2) check (line_total >= 0),
  product_id bigint references public.products(id) on delete set null,
  ingredient_id bigint references public.ingredients(id) on delete set null,
  normalized_base_quantity numeric(14, 4) check (normalized_base_quantity > 0),
  normalized_base_unit_code text references public.measurement_units(code),
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
    references public.receipts(id, user_id) on delete cascade,
  check (
    normalized_base_unit_code is null
    or normalized_base_unit_code in ('g', 'ml', 'each')
  )
);

create table public.pantry_lots (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  ingredient_id bigint not null references public.ingredients(id) on delete restrict,
  product_id bigint references public.products(id) on delete set null,
  receipt_line_id bigint,
  source_type text not null check (source_type in ('manual', 'receipt')),
  base_unit_code text not null references public.measurement_units(code),
  storage_location text not null default 'pantry' check (
    storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')
  ),
  acquired_at timestamptz not null default now(),
  best_before_on date,
  opened_at timestamptz,
  acquisition_cost numeric(12, 2) check (acquisition_cost >= 0),
  currency_code text check (currency_code ~ '^[A-Z]{3}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  unique (receipt_line_id),
  foreign key (receipt_line_id, user_id)
    references public.receipt_lines(id, user_id) on delete restrict,
  check (base_unit_code in ('g', 'ml', 'each')),
  check ((acquisition_cost is null) = (currency_code is null))
);

create table public.inventory_events (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  pantry_lot_id bigint not null,
  event_type text not null check (
    event_type in ('acquired', 'consumed', 'wasted', 'adjusted')
  ),
  quantity_delta_base numeric(14, 4) not null check (quantity_delta_base <> 0),
  waste_reason text check (
    waste_reason is null or waste_reason in ('expired', 'spoiled', 'unused', 'other')
  ),
  note text,
  estimated_value_amount numeric(12, 2) check (estimated_value_amount >= 0),
  estimated_weight_g numeric(14, 4) check (estimated_weight_g >= 0),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (pantry_lot_id, user_id)
    references public.pantry_lots(id, user_id) on delete cascade,
  check (
    (event_type = 'acquired' and quantity_delta_base > 0)
    or (event_type in ('consumed', 'wasted') and quantity_delta_base < 0)
    or event_type = 'adjusted'
  ),
  check ((event_type = 'wasted') = (waste_reason is not null))
);

create unique index inventory_events_one_acquisition_idx
  on public.inventory_events (pantry_lot_id)
  where event_type = 'acquired';

create table public.shopping_lists (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  meal_plan_id bigint not null unique,
  revision integer not null default 1 check (revision > 0),
  status text not null default 'draft' check (
    status in ('draft', 'active', 'completed', 'archived')
  ),
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  calculated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (meal_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade
);

create table public.shopping_list_items (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  shopping_list_id bigint not null,
  ingredient_id bigint references public.ingredients(id) on delete restrict,
  custom_label text,
  preferred_product_id bigint references public.products(id) on delete set null,
  source_type text not null default 'generated' check (source_type in ('generated', 'manual')),
  base_unit_code text references public.measurement_units(code),
  required_base_quantity numeric(14, 4) not null default 0 check (required_base_quantity >= 0),
  pantry_applied_base_quantity numeric(14, 4) not null default 0 check (
    pantry_applied_base_quantity >= 0
  ),
  to_buy_base_quantity numeric(14, 4) not null default 0 check (to_buy_base_quantity >= 0),
  display_quantity numeric(12, 4) check (display_quantity > 0),
  display_unit_code text references public.measurement_units(code),
  needed_by_date date,
  estimated_line_cost numeric(12, 2) check (estimated_line_cost >= 0),
  status text not null default 'pending' check (status in ('pending', 'bought', 'skipped')),
  needs_review boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  foreign key (shopping_list_id, user_id)
    references public.shopping_lists(id, user_id) on delete cascade,
  check (num_nonnulls(ingredient_id, nullif(btrim(custom_label), '')) = 1),
  check (
    source_type = 'manual'
    or base_unit_code in ('g', 'ml', 'each')
  ),
  check (
    source_type = 'manual'
    or abs(required_base_quantity - pantry_applied_base_quantity - to_buy_base_quantity) < 0.0001
  )
);

create unique index shopping_generated_item_unique_idx
  on public.shopping_list_items (shopping_list_id, ingredient_id, base_unit_code)
  where source_type = 'generated';

create table public.shopping_list_item_sources (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  shopping_list_item_id bigint not null,
  meal_plan_slot_id bigint not null,
  required_base_quantity numeric(14, 4) not null check (required_base_quantity > 0),
  pantry_applied_base_quantity numeric(14, 4) not null default 0 check (
    pantry_applied_base_quantity >= 0
    and pantry_applied_base_quantity <= required_base_quantity
  ),
  created_at timestamptz not null default now(),
  unique (shopping_list_item_id, meal_plan_slot_id),
  foreign key (shopping_list_item_id, user_id)
    references public.shopping_list_items(id, user_id) on delete cascade,
  foreign key (meal_plan_slot_id, user_id)
    references public.meal_plan_slots(id, user_id) on delete cascade
);

-- -----------------------------------------------------------------------------
-- AI operations and transparent weekly impact snapshots
-- -----------------------------------------------------------------------------

create table public.ai_runs (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  job_type text not null check (job_type in ('receipt_extraction', 'meal_plan_generation')),
  receipt_id bigint,
  meal_plan_id bigint,
  status text not null default 'queued' check (
    status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')
  ),
  provider text,
  model text,
  prompt_version text,
  input_hash text,
  output_payload jsonb not null default '{}'::jsonb,
  error_code text,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (receipt_id, user_id)
    references public.receipts(id, user_id) on delete cascade,
  foreign key (meal_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade,
  check (
    (job_type = 'receipt_extraction' and receipt_id is not null and meal_plan_id is null)
    or
    (job_type = 'meal_plan_generation' and meal_plan_id is not null and receipt_id is null)
  )
);

create table public.weekly_impact_summaries (
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  week_start date not null,
  currency_code text not null check (currency_code ~ '^[A-Z]{3}$'),
  status text not null default 'provisional' check (status in ('provisional', 'final')),
  actual_spend_amount numeric(12, 2) not null default 0 check (actual_spend_amount >= 0),
  actual_waste_value_amount numeric(12, 2) not null default 0 check (
    actual_waste_value_amount >= 0
  ),
  actual_waste_weight_g numeric(14, 4) not null default 0 check (
    actual_waste_weight_g >= 0
  ),
  discount_savings_amount numeric(12, 2) not null default 0 check (
    discount_savings_amount >= 0
  ),
  estimated_pantry_reuse_value_amount numeric(12, 2) not null default 0 check (
    estimated_pantry_reuse_value_amount >= 0
  ),
  estimated_avoided_waste_weight_g numeric(14, 4) not null default 0 check (
    estimated_avoided_waste_weight_g >= 0
  ),
  unquantified_waste_event_count integer not null default 0 check (
    unquantified_waste_event_count >= 0
  ),
  methodology_version text not null,
  confidence numeric(5, 4) check (confidence between 0 and 1),
  generated_at timestamptz not null default now(),
  primary key (user_id, week_start, currency_code),
  check (extract(isodow from week_start) = 1)
);

-- -----------------------------------------------------------------------------
-- Trigger helpers, immutable recipe versions, and authenticated RPCs
-- -----------------------------------------------------------------------------

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

create trigger ingredients_set_updated_at
before update on public.ingredients
for each row execute function public.set_updated_at();

create trigger products_set_updated_at
before update on public.products
for each row execute function public.set_updated_at();

create trigger ingredient_storage_guidance_set_updated_at
before update on public.ingredient_storage_guidance
for each row execute function public.set_updated_at();

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger recipes_set_updated_at
before update on public.recipes
for each row execute function public.set_updated_at();

create trigger meal_plans_set_updated_at
before update on public.meal_plans
for each row execute function public.set_updated_at();

create trigger meal_plan_slots_set_updated_at
before update on public.meal_plan_slots
for each row execute function public.set_updated_at();

create trigger receipts_set_updated_at
before update on public.receipts
for each row execute function public.set_updated_at();

create trigger receipt_lines_set_updated_at
before update on public.receipt_lines
for each row execute function public.set_updated_at();

create trigger pantry_lots_set_updated_at
before update on public.pantry_lots
for each row execute function public.set_updated_at();

create trigger shopping_lists_set_updated_at
before update on public.shopping_lists
for each row execute function public.set_updated_at();

create trigger shopping_list_items_set_updated_at
before update on public.shopping_list_items
for each row execute function public.set_updated_at();

create trigger ai_runs_set_updated_at
before update on public.ai_runs
for each row execute function public.set_updated_at();

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

create or replace function public.protect_published_recipe_version()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if old.status = 'published' then
    if tg_op = 'DELETE' and (select auth.uid()) is null then
      return old;
    end if;

    raise exception 'Published recipe versions are immutable';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

create trigger recipe_versions_protect_published
before update or delete on public.recipe_versions
for each row execute function public.protect_published_recipe_version();

create or replace function public.protect_published_recipe_component()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_recipe_version_id bigint;
  v_status text;
begin
  v_recipe_version_id := case when tg_op = 'DELETE'
    then old.recipe_version_id else new.recipe_version_id end;

  select status
  into v_status
  from public.recipe_versions
  where id = v_recipe_version_id;

  if v_status = 'published' then
    if tg_op = 'DELETE' and (select auth.uid()) is null then
      return old;
    end if;

    raise exception 'Published recipe versions are immutable';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

create trigger recipe_ingredients_protect_published
before insert or update or delete on public.recipe_ingredients
for each row execute function public.protect_published_recipe_component();

create trigger recipe_steps_protect_published
before insert or update or delete on public.recipe_steps
for each row execute function public.protect_published_recipe_component();

create or replace function public.validate_ingredient_base_unit()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_ingredient_id bigint;
  v_base_unit_code text;
  v_expected_base_unit_code text;
  v_row jsonb := to_jsonb(new);
begin
  v_ingredient_id := nullif(v_row ->> tg_argv[0], '')::bigint;
  v_base_unit_code := nullif(v_row ->> tg_argv[1], '');

  if v_ingredient_id is null or v_base_unit_code is null then
    return new;
  end if;

  select base_unit_code
  into v_expected_base_unit_code
  from public.ingredients
  where id = v_ingredient_id;

  if v_expected_base_unit_code is distinct from v_base_unit_code then
    raise exception 'Normalized base unit % does not match ingredient base unit %',
      v_base_unit_code,
      v_expected_base_unit_code;
  end if;

  return new;
end;
$$;

create trigger recipe_ingredients_validate_base_unit
before insert or update of ingredient_id, base_unit_code on public.recipe_ingredients
for each row execute function public.validate_ingredient_base_unit('ingredient_id', 'base_unit_code');

create trigger receipt_lines_validate_base_unit
before insert or update of ingredient_id, normalized_base_unit_code on public.receipt_lines
for each row execute function public.validate_ingredient_base_unit(
  'ingredient_id',
  'normalized_base_unit_code'
);

create trigger pantry_lots_validate_base_unit
before insert or update of ingredient_id, base_unit_code on public.pantry_lots
for each row execute function public.validate_ingredient_base_unit('ingredient_id', 'base_unit_code');

create or replace function public.validate_meal_plan_recipe_version()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.meal_plans
    where id = new.meal_plan_id
      and user_id = new.user_id
      and new.meal_date between start_date and end_date
  ) then
    raise exception 'Meal date must fall inside the owning meal plan date range';
  end if;

  if new.recipe_version_id is null then
    return new;
  end if;

  if not exists (
    select 1
    from public.recipe_versions
    where id = new.recipe_version_id
      and user_id = new.user_id
      and status = 'published'
  ) then
    raise exception 'Meal plan slots may reference only published recipe versions owned by the user';
  end if;

  return new;
end;
$$;

create trigger meal_plan_slots_validate_recipe_version
before insert or update of recipe_version_id, user_id on public.meal_plan_slots
for each row execute function public.validate_meal_plan_recipe_version();

create or replace function public.publish_recipe_version(p_recipe_version_id bigint)
returns public.recipe_versions
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_version public.recipe_versions;
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;

  select *
  into v_version
  from public.recipe_versions
  where id = p_recipe_version_id
    and user_id = v_user_id
  for update;

  if not found then
    raise exception 'Recipe version not found';
  end if;

  if v_version.status = 'published' then
    return v_version;
  end if;

  if not exists (
    select 1 from public.recipe_ingredients
    where recipe_version_id = p_recipe_version_id and user_id = v_user_id
  ) then
    raise exception 'A recipe needs at least one ingredient';
  end if;

  if not exists (
    select 1 from public.recipe_steps
    where recipe_version_id = p_recipe_version_id and user_id = v_user_id
  ) then
    raise exception 'A recipe needs at least one instruction step';
  end if;

  update public.recipe_versions
  set status = 'published', published_at = now()
  where id = p_recipe_version_id
  returning * into v_version;

  update public.recipes
  set current_version_id = v_version.id
  where id = v_version.recipe_id and user_id = v_user_id;

  return v_version;
end;
$$;

create or replace function public.add_pantry_lot(
  p_ingredient_id bigint,
  p_quantity_base numeric,
  p_base_unit_code text,
  p_product_id bigint default null,
  p_storage_location text default 'pantry',
  p_acquired_at timestamptz default now(),
  p_best_before_on date default null,
  p_acquisition_cost numeric default null,
  p_currency_code text default null
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_lot_id bigint;
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;

  if p_quantity_base <= 0 then
    raise exception 'Quantity must be positive';
  end if;

  insert into public.pantry_lots (
    user_id,
    ingredient_id,
    product_id,
    source_type,
    base_unit_code,
    storage_location,
    acquired_at,
    best_before_on,
    acquisition_cost,
    currency_code
  ) values (
    v_user_id,
    p_ingredient_id,
    p_product_id,
    'manual',
    p_base_unit_code,
    p_storage_location,
    p_acquired_at,
    p_best_before_on,
    p_acquisition_cost,
    p_currency_code
  )
  returning id into v_lot_id;

  insert into public.inventory_events (
    user_id,
    pantry_lot_id,
    event_type,
    quantity_delta_base,
    occurred_at
  ) values (
    v_user_id,
    v_lot_id,
    'acquired',
    p_quantity_base,
    p_acquired_at
  );

  return v_lot_id;
end;
$$;

create or replace function public.confirm_receipt(p_receipt_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_receipt public.receipts;
  v_line record;
  v_lot_id bigint;
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;

  select *
  into v_receipt
  from public.receipts
  where id = p_receipt_id and user_id = v_user_id
  for update;

  if not found then
    raise exception 'Receipt not found';
  end if;

  if v_receipt.status = 'confirmed' then
    return;
  end if;

  if v_receipt.status <> 'review' then
    raise exception 'Receipt must be in review before confirmation';
  end if;

  if not exists (
    select 1 from public.receipt_lines
    where receipt_id = p_receipt_id
      and user_id = v_user_id
      and review_status in ('accepted', 'corrected')
  ) then
    raise exception 'Receipt has no accepted lines';
  end if;

  if exists (
    select 1 from public.receipt_lines
    where receipt_id = p_receipt_id
      and user_id = v_user_id
      and review_status in ('accepted', 'corrected')
      and (
        ingredient_id is null
        or normalized_base_quantity is null
        or normalized_base_unit_code is null
      )
  ) then
    raise exception 'Every accepted receipt line needs an ingredient and normalized quantity';
  end if;

  for v_line in
    select *
    from public.receipt_lines
    where receipt_id = p_receipt_id
      and user_id = v_user_id
      and review_status in ('accepted', 'corrected')
    order by line_number
  loop
    insert into public.pantry_lots (
      user_id,
      ingredient_id,
      product_id,
      receipt_line_id,
      source_type,
      base_unit_code,
      storage_location,
      acquired_at,
      acquisition_cost,
      currency_code
    ) values (
      v_user_id,
      v_line.ingredient_id,
      v_line.product_id,
      v_line.id,
      'receipt',
      v_line.normalized_base_unit_code,
      'pantry',
      coalesce(v_receipt.purchased_at, now()),
      v_line.line_total,
      v_receipt.currency_code
    )
    returning id into v_lot_id;

    insert into public.inventory_events (
      user_id,
      pantry_lot_id,
      event_type,
      quantity_delta_base,
      occurred_at
    ) values (
      v_user_id,
      v_lot_id,
      'acquired',
      v_line.normalized_base_quantity,
      coalesce(v_receipt.purchased_at, now())
    );
  end loop;

  update public.receipts
  set status = 'confirmed',
      confirmed_at = now(),
      image_delete_after = now() + interval '30 days'
  where id = p_receipt_id;
end;
$$;

create or replace function public.record_inventory_change(
  p_pantry_lot_id bigint,
  p_event_type text,
  p_quantity_delta_base numeric,
  p_waste_reason text default null,
  p_note text default null,
  p_occurred_at timestamptz default now()
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid := (select auth.uid());
  v_lot public.pantry_lots;
  v_remaining numeric;
  v_acquired_quantity numeric;
  v_event_id bigint;
  v_density numeric;
  v_unit_weight numeric;
  v_estimated_value numeric;
  v_estimated_weight numeric;
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;

  if p_event_type not in ('consumed', 'wasted', 'adjusted') then
    raise exception 'Unsupported inventory event type';
  end if;

  if p_quantity_delta_base = 0
     or (p_event_type in ('consumed', 'wasted') and p_quantity_delta_base >= 0) then
    raise exception 'Consumed and wasted quantities must be negative';
  end if;

  select *
  into v_lot
  from public.pantry_lots
  where id = p_pantry_lot_id and user_id = v_user_id
  for update;

  if not found then
    raise exception 'Pantry lot not found';
  end if;

  select coalesce(sum(quantity_delta_base), 0),
         coalesce(sum(quantity_delta_base) filter (where event_type = 'acquired'), 0)
  into v_remaining, v_acquired_quantity
  from public.inventory_events
  where pantry_lot_id = p_pantry_lot_id and user_id = v_user_id;

  if v_remaining + p_quantity_delta_base < 0 then
    raise exception 'Inventory change would make the pantry lot negative';
  end if;

  if p_event_type = 'wasted' then
    if p_waste_reason is null then
      raise exception 'Waste reason is required';
    end if;

    if v_lot.acquisition_cost is not null and v_acquired_quantity > 0 then
      v_estimated_value := round(
        abs(p_quantity_delta_base) * v_lot.acquisition_cost / v_acquired_quantity,
        2
      );
    end if;

    select density_g_per_ml, average_unit_weight_g
    into v_density, v_unit_weight
    from public.ingredients
    where id = v_lot.ingredient_id;

    v_estimated_weight := case v_lot.base_unit_code
      when 'g' then abs(p_quantity_delta_base)
      when 'ml' then abs(p_quantity_delta_base) * v_density
      when 'each' then abs(p_quantity_delta_base) * v_unit_weight
      else null
    end;
  end if;

  insert into public.inventory_events (
    user_id,
    pantry_lot_id,
    event_type,
    quantity_delta_base,
    waste_reason,
    note,
    estimated_value_amount,
    estimated_weight_g,
    occurred_at
  ) values (
    v_user_id,
    p_pantry_lot_id,
    p_event_type,
    p_quantity_delta_base,
    p_waste_reason,
    p_note,
    v_estimated_value,
    v_estimated_weight,
    p_occurred_at
  )
  returning id into v_event_id;

  return v_event_id;
end;
$$;

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
  v_source record;
  v_stock record;
  v_need numeric;
  v_allocate numeric;
  v_allocated numeric;
begin
  if v_user_id is null then
    raise exception 'Authentication required';
  end if;

  select *
  into v_plan
  from public.meal_plans
  where id = p_meal_plan_id and user_id = v_user_id
  for update;

  if not found then
    raise exception 'Meal plan not found';
  end if;

  if exists (
    select 1
    from public.meal_plan_slots
    where meal_plan_id = p_meal_plan_id
      and user_id = v_user_id
      and status <> 'skipped'
      and recipe_version_id is null
  ) then
    raise exception 'Every active meal plan slot needs a recipe before building the shopping list';
  end if;

  insert into public.shopping_lists (
    user_id,
    meal_plan_id,
    currency_code,
    status,
    calculated_at
  ) values (
    v_user_id,
    p_meal_plan_id,
    v_plan.currency_code,
    'active',
    now()
  )
  on conflict (meal_plan_id) do update
  set revision = public.shopping_lists.revision + 1,
      currency_code = excluded.currency_code,
      status = 'active',
      calculated_at = now(),
      updated_at = now()
  returning id into v_list_id;

  delete from public.shopping_list_items
  where shopping_list_id = v_list_id
    and user_id = v_user_id
    and source_type = 'generated';

  insert into public.shopping_list_items (
    user_id,
    shopping_list_id,
    ingredient_id,
    source_type,
    base_unit_code,
    required_base_quantity,
    pantry_applied_base_quantity,
    to_buy_base_quantity,
    needed_by_date
  )
  select
    v_user_id,
    v_list_id,
    ri.ingredient_id,
    'generated',
    ri.base_unit_code,
    round(sum(ri.base_quantity * mps.servings / rv.servings), 4),
    0,
    round(sum(ri.base_quantity * mps.servings / rv.servings), 4),
    min(mps.meal_date)
  from public.meal_plan_slots mps
  join public.recipe_versions rv
    on rv.id = mps.recipe_version_id and rv.user_id = mps.user_id
  join public.recipe_ingredients ri
    on ri.recipe_version_id = rv.id and ri.user_id = rv.user_id
  where mps.meal_plan_id = p_meal_plan_id
    and mps.user_id = v_user_id
    and mps.status <> 'skipped'
    and not ri.optional
  group by ri.ingredient_id, ri.base_unit_code;

  insert into public.shopping_list_item_sources (
    user_id,
    shopping_list_item_id,
    meal_plan_slot_id,
    required_base_quantity
  )
  select
    v_user_id,
    sli.id,
    mps.id,
    round(sum(ri.base_quantity * mps.servings / rv.servings), 4)
  from public.meal_plan_slots mps
  join public.recipe_versions rv
    on rv.id = mps.recipe_version_id and rv.user_id = mps.user_id
  join public.recipe_ingredients ri
    on ri.recipe_version_id = rv.id and ri.user_id = rv.user_id
  join public.shopping_list_items sli
    on sli.shopping_list_id = v_list_id
   and sli.user_id = v_user_id
   and sli.source_type = 'generated'
   and sli.ingredient_id = ri.ingredient_id
   and sli.base_unit_code = ri.base_unit_code
  where mps.meal_plan_id = p_meal_plan_id
    and mps.user_id = v_user_id
    and mps.status <> 'skipped'
    and not ri.optional
  group by sli.id, mps.id;

  create temporary table if not exists shopping_stock_allocation (
    pantry_lot_id bigint primary key,
    ingredient_id bigint not null,
    base_unit_code text not null,
    best_before_on date,
    remaining_quantity numeric(14, 4) not null
  ) on commit drop;

  truncate table pg_temp.shopping_stock_allocation;

  insert into pg_temp.shopping_stock_allocation (
    pantry_lot_id,
    ingredient_id,
    base_unit_code,
    best_before_on,
    remaining_quantity
  )
  select
    pl.id,
    pl.ingredient_id,
    pl.base_unit_code,
    pl.best_before_on,
    sum(ie.quantity_delta_base)
  from public.pantry_lots pl
  join public.inventory_events ie
    on ie.pantry_lot_id = pl.id and ie.user_id = pl.user_id
  where pl.user_id = v_user_id
  group by pl.id, pl.ingredient_id, pl.base_unit_code, pl.best_before_on
  having sum(ie.quantity_delta_base) > 0;

  for v_source in
    select
      slis.id,
      slis.required_base_quantity,
      sli.ingredient_id,
      sli.base_unit_code,
      mps.meal_date
    from public.shopping_list_item_sources slis
    join public.shopping_list_items sli
      on sli.id = slis.shopping_list_item_id and sli.user_id = slis.user_id
    join public.meal_plan_slots mps
      on mps.id = slis.meal_plan_slot_id and mps.user_id = slis.user_id
    where sli.shopping_list_id = v_list_id
      and slis.user_id = v_user_id
    order by mps.meal_date, slis.meal_plan_slot_id, slis.id
  loop
    v_need := v_source.required_base_quantity;
    v_allocated := 0;

    for v_stock in
      select pantry_lot_id, remaining_quantity
      from pg_temp.shopping_stock_allocation
      where ingredient_id = v_source.ingredient_id
        and base_unit_code = v_source.base_unit_code
        and remaining_quantity > 0
        and (best_before_on is null or best_before_on >= v_source.meal_date)
      order by best_before_on nulls last, pantry_lot_id
    loop
      exit when v_need <= 0;

      v_allocate := least(v_need, v_stock.remaining_quantity);

      update pg_temp.shopping_stock_allocation
      set remaining_quantity = remaining_quantity - v_allocate
      where pantry_lot_id = v_stock.pantry_lot_id;

      v_need := v_need - v_allocate;
      v_allocated := v_allocated + v_allocate;
    end loop;

    update public.shopping_list_item_sources
    set pantry_applied_base_quantity = v_allocated
    where id = v_source.id;
  end loop;

  update public.shopping_list_items sli
  set pantry_applied_base_quantity = source_totals.pantry_quantity,
      to_buy_base_quantity = greatest(
        sli.required_base_quantity - source_totals.pantry_quantity,
        0
      ),
      updated_at = now()
  from (
    select shopping_list_item_id, sum(pantry_applied_base_quantity) as pantry_quantity
    from public.shopping_list_item_sources
    where user_id = v_user_id
    group by shopping_list_item_id
  ) source_totals
  where sli.id = source_totals.shopping_list_item_id
    and sli.shopping_list_id = v_list_id
    and sli.user_id = v_user_id;

  with latest_prices as (
    select distinct on (rl.ingredient_id, rl.normalized_base_unit_code)
      rl.ingredient_id,
      rl.normalized_base_unit_code,
      rl.line_total / rl.normalized_base_quantity as unit_cost
    from public.receipt_lines rl
    join public.receipts r
      on r.id = rl.receipt_id and r.user_id = rl.user_id
    where rl.user_id = v_user_id
      and r.status = 'confirmed'
      and r.currency_code = v_plan.currency_code
      and rl.ingredient_id is not null
      and rl.line_total is not null
      and rl.normalized_base_quantity > 0
    order by
      rl.ingredient_id,
      rl.normalized_base_unit_code,
      coalesce(r.purchased_at, r.created_at) desc,
      rl.id desc
  )
  update public.shopping_list_items sli
  set estimated_line_cost = round(sli.to_buy_base_quantity * lp.unit_cost, 2),
      updated_at = now()
  from latest_prices lp
  where sli.shopping_list_id = v_list_id
    and sli.user_id = v_user_id
    and sli.ingredient_id = lp.ingredient_id
    and sli.base_unit_code = lp.normalized_base_unit_code;

  update public.meal_plans
  set pantry_snapshot_at = now()
  where id = p_meal_plan_id and user_id = v_user_id;

  return v_list_id;
end;
$$;

create view public.current_pantry
with (security_invoker = true)
as
select
  pl.id as pantry_lot_id,
  pl.user_id,
  pl.ingredient_id,
  pl.product_id,
  pl.base_unit_code,
  pl.storage_location,
  pl.acquired_at,
  pl.best_before_on,
  pl.opened_at,
  pl.acquisition_cost,
  pl.currency_code,
  sum(ie.quantity_delta_base) as remaining_quantity_base
from public.pantry_lots pl
join public.inventory_events ie
  on ie.pantry_lot_id = pl.id and ie.user_id = pl.user_id
group by
  pl.id,
  pl.user_id,
  pl.ingredient_id,
  pl.product_id,
  pl.base_unit_code,
  pl.storage_location,
  pl.acquired_at,
  pl.best_before_on,
  pl.opened_at,
  pl.acquisition_cost,
  pl.currency_code
having sum(ie.quantity_delta_base) > 0;

create view public.weekly_actuals
with (security_invoker = true)
as
select
  p.user_id,
  date_trunc('week', event_time at time zone p.timezone)::date as week_start,
  events.currency_code,
  sum(spend_amount) as actual_spend_amount,
  sum(waste_value_amount) as actual_waste_value_amount,
  sum(waste_weight_g) as actual_waste_weight_g,
  count(*) filter (where is_unquantified_waste) as unquantified_waste_event_count
from public.profiles p
join (
  select
    r.user_id,
    coalesce(r.purchased_at, r.confirmed_at, r.created_at) as event_time,
    r.currency_code,
    coalesce(r.total_amount, 0) as spend_amount,
    0::numeric as waste_value_amount,
    0::numeric as waste_weight_g,
    false as is_unquantified_waste
  from public.receipts r
  where r.status = 'confirmed'

  union all

  select
    ie.user_id,
    ie.occurred_at as event_time,
    coalesce(pl.currency_code, p2.currency_code) as currency_code,
    0::numeric as spend_amount,
    coalesce(ie.estimated_value_amount, 0) as waste_value_amount,
    coalesce(ie.estimated_weight_g, 0) as waste_weight_g,
    ie.estimated_weight_g is null as is_unquantified_waste
  from public.inventory_events ie
  join public.pantry_lots pl
    on pl.id = ie.pantry_lot_id and pl.user_id = ie.user_id
  join public.profiles p2 on p2.user_id = ie.user_id
  where ie.event_type = 'wasted'
) events on events.user_id = p.user_id
group by
  p.user_id,
  date_trunc('week', event_time at time zone p.timezone)::date,
  events.currency_code;

-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------

create index ingredient_aliases_ingredient_id_idx
  on public.ingredient_aliases (ingredient_id);
create index ingredient_allergens_allergen_id_idx
  on public.ingredient_allergens (allergen_id);
create index ingredient_dietary_tags_tag_id_idx
  on public.ingredient_dietary_tags (dietary_tag_id);
create index product_ingredient_mappings_ingredient_id_idx
  on public.product_ingredient_mappings (ingredient_id);
create index user_dietary_preferences_tag_id_idx
  on public.user_dietary_preferences (dietary_tag_id);
create index user_allergies_user_id_idx
  on public.user_allergies (user_id);
create index user_allergies_allergen_id_idx
  on public.user_allergies (allergen_id) where allergen_id is not null;
create index user_cuisine_preferences_cuisine_id_idx
  on public.user_cuisine_preferences (cuisine_id);

create index recipes_user_id_created_at_idx
  on public.recipes (user_id, created_at desc);
create index recipes_current_version_id_idx
  on public.recipes (current_version_id) where current_version_id is not null;
create index recipe_versions_user_id_idx
  on public.recipe_versions (user_id);
create index recipe_versions_cuisine_id_idx
  on public.recipe_versions (cuisine_id) where cuisine_id is not null;
create index recipe_versions_category_id_idx
  on public.recipe_versions (meal_category_id) where meal_category_id is not null;
create index recipe_ingredients_user_id_idx
  on public.recipe_ingredients (user_id);
create index recipe_ingredients_ingredient_id_idx
  on public.recipe_ingredients (ingredient_id);
create index recipe_steps_user_id_idx
  on public.recipe_steps (user_id);

create index meal_plans_user_id_start_date_idx
  on public.meal_plans (user_id, start_date desc);
create index meal_plan_slots_user_id_meal_date_idx
  on public.meal_plan_slots (user_id, meal_date);
create index meal_plan_slots_recipe_version_id_idx
  on public.meal_plan_slots (recipe_version_id) where recipe_version_id is not null;
create index meal_plan_slots_requested_cuisine_id_idx
  on public.meal_plan_slots (requested_cuisine_id) where requested_cuisine_id is not null;
create index meal_plan_slots_requested_category_id_idx
  on public.meal_plan_slots (requested_category_id) where requested_category_id is not null;

create index receipts_user_id_purchased_at_idx
  on public.receipts (user_id, purchased_at desc);
create index receipts_retailer_id_idx
  on public.receipts (retailer_id) where retailer_id is not null;
create index receipt_lines_user_id_idx
  on public.receipt_lines (user_id);
create index receipt_lines_product_id_idx
  on public.receipt_lines (product_id) where product_id is not null;
create index receipt_lines_ingredient_id_idx
  on public.receipt_lines (ingredient_id) where ingredient_id is not null;
create index receipt_lines_pending_review_idx
  on public.receipt_lines (receipt_id, line_number)
  where review_status = 'pending';

create index pantry_lots_user_ingredient_expiry_idx
  on public.pantry_lots (user_id, ingredient_id, best_before_on);
create index pantry_lots_product_id_idx
  on public.pantry_lots (product_id) where product_id is not null;
create index inventory_events_lot_id_idx
  on public.inventory_events (pantry_lot_id);
create index inventory_events_user_occurred_at_idx
  on public.inventory_events (user_id, occurred_at desc);

create index shopping_lists_user_id_idx
  on public.shopping_lists (user_id);
create index shopping_list_items_user_list_status_idx
  on public.shopping_list_items (user_id, shopping_list_id, status);
create index shopping_list_items_ingredient_id_idx
  on public.shopping_list_items (ingredient_id) where ingredient_id is not null;
create index shopping_list_items_product_id_idx
  on public.shopping_list_items (preferred_product_id) where preferred_product_id is not null;
create index shopping_list_item_sources_user_id_idx
  on public.shopping_list_item_sources (user_id);
create index shopping_list_item_sources_slot_id_idx
  on public.shopping_list_item_sources (meal_plan_slot_id);

create index ai_runs_user_status_created_idx
  on public.ai_runs (user_id, status, created_at desc);
create index ai_runs_receipt_id_idx
  on public.ai_runs (receipt_id) where receipt_id is not null;
create index ai_runs_meal_plan_id_idx
  on public.ai_runs (meal_plan_id) where meal_plan_id is not null;
create index ai_runs_queued_idx
  on public.ai_runs (created_at)
  where status = 'queued';

-- -----------------------------------------------------------------------------
-- Row-level security and least-privilege grants
-- -----------------------------------------------------------------------------

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'measurement_units',
    'dietary_tags',
    'allergens',
    'cuisines',
    'meal_categories',
    'retailers',
    'ingredients',
    'ingredient_aliases',
    'ingredient_allergens',
    'ingredient_dietary_tags',
    'products',
    'product_ingredient_mappings',
    'ingredient_storage_guidance'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format(
      'create policy %I on public.%I for select to authenticated using (true)',
      table_name || '_authenticated_read',
      table_name
    );
  end loop;
end;
$$;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'profiles',
    'user_dietary_preferences',
    'user_allergies',
    'user_cuisine_preferences',
    'recipes',
    'recipe_versions',
    'recipe_ingredients',
    'recipe_steps',
    'meal_plans',
    'meal_plan_slots',
    'receipts',
    'receipt_lines',
    'pantry_lots',
    'inventory_events',
    'shopping_lists',
    'shopping_list_items',
    'shopping_list_item_sources',
    'ai_runs',
    'weekly_impact_summaries'
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

grant select on
  public.measurement_units,
  public.dietary_tags,
  public.allergens,
  public.cuisines,
  public.meal_categories,
  public.retailers,
  public.ingredients,
  public.ingredient_aliases,
  public.ingredient_allergens,
  public.ingredient_dietary_tags,
  public.products,
  public.product_ingredient_mappings,
  public.ingredient_storage_guidance
to authenticated;

grant select, update on public.profiles to authenticated;

grant select, insert, update, delete on
  public.user_dietary_preferences,
  public.user_allergies,
  public.user_cuisine_preferences,
  public.recipe_versions,
  public.recipe_ingredients,
  public.recipe_steps,
  public.meal_plans,
  public.meal_plan_slots,
  public.receipt_lines
to authenticated;

grant select, insert, update on
  public.recipes,
  public.receipts
to authenticated;

grant select, update on public.pantry_lots to authenticated;
grant select on public.inventory_events to authenticated;
grant select, update on public.shopping_lists, public.shopping_list_items to authenticated;
grant select on public.shopping_list_item_sources, public.ai_runs, public.weekly_impact_summaries
  to authenticated;
grant select on public.current_pantry, public.weekly_actuals to authenticated;

grant usage, select on all sequences in schema public to authenticated;

grant execute on function public.publish_recipe_version(bigint) to authenticated;
grant execute on function public.add_pantry_lot(
  bigint, numeric, text, bigint, text, timestamptz, date, numeric, text
) to authenticated;
grant execute on function public.confirm_receipt(bigint) to authenticated;
grant execute on function public.record_inventory_change(
  bigint, text, numeric, text, text, timestamptz
) to authenticated;
grant execute on function public.rebuild_shopping_list(bigint) to authenticated;

-- Private receipt images. Object paths must begin with the authenticated user UUID.
insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
) values (
  'receipt-images',
  'receipt-images',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create policy receipt_images_owner_select
on storage.objects
for select
to authenticated
using (
  bucket_id = 'receipt-images'
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

create policy receipt_images_owner_insert
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'receipt-images'
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

create policy receipt_images_owner_delete
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'receipt-images'
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

-- -----------------------------------------------------------------------------
-- Required reference data
-- -----------------------------------------------------------------------------

insert into public.measurement_units (code, name, dimension, factor_to_base) values
  ('g', 'gram', 'mass', 1),
  ('kg', 'kilogram', 'mass', 1000),
  ('ml', 'millilitre', 'volume', 1),
  ('l', 'litre', 'volume', 1000),
  ('each', 'each', 'count', 1),
  ('tsp', 'teaspoon', 'volume', 5),
  ('tbsp', 'tablespoon', 'volume', 15),
  ('cup', 'metric cup', 'volume', 250)
on conflict (code) do nothing;

insert into public.dietary_tags (slug, name) values
  ('vegan', 'Vegan'),
  ('vegetarian', 'Vegetarian')
on conflict (slug) do nothing;

insert into public.allergens (slug, name) values
  ('gluten', 'Cereals containing gluten'),
  ('crustaceans', 'Crustaceans'),
  ('eggs', 'Eggs'),
  ('fish', 'Fish'),
  ('peanuts', 'Peanuts'),
  ('soybeans', 'Soybeans'),
  ('milk', 'Milk'),
  ('nuts', 'Tree nuts'),
  ('celery', 'Celery'),
  ('mustard', 'Mustard'),
  ('sesame', 'Sesame'),
  ('sulphites', 'Sulphur dioxide and sulphites'),
  ('lupin', 'Lupin'),
  ('molluscs', 'Molluscs')
on conflict (slug) do nothing;

insert into public.cuisines (slug, name) values
  ('mediterranean', 'Mediterranean'),
  ('italian', 'Italian'),
  ('mexican', 'Mexican'),
  ('indian', 'Indian'),
  ('middle-eastern', 'Middle Eastern'),
  ('east-asian', 'East Asian'),
  ('southeast-asian', 'Southeast Asian'),
  ('dutch', 'Dutch'),
  ('international', 'International')
on conflict (slug) do nothing;

insert into public.meal_categories (slug, name) values
  ('stir-fry', 'Stir-fry'),
  ('soup', 'Soup'),
  ('salad', 'Salad'),
  ('pasta', 'Pasta'),
  ('curry', 'Curry'),
  ('bowl', 'Bowl'),
  ('sandwich', 'Sandwich'),
  ('breakfast', 'Breakfast'),
  ('tray-bake', 'Tray bake')
on conflict (slug) do nothing;

insert into public.ingredients (
  slug,
  name,
  base_unit_code,
  density_g_per_ml,
  average_unit_weight_g
) values
  ('tomato', 'Tomato', 'g', null, 120),
  ('onion', 'Onion', 'g', null, 110),
  ('garlic', 'Garlic', 'g', null, 4),
  ('rice', 'Rice', 'g', null, null),
  ('pasta', 'Pasta', 'g', null, null),
  ('potato', 'Potato', 'g', null, 170),
  ('carrot', 'Carrot', 'g', null, 70),
  ('broccoli', 'Broccoli', 'g', null, null),
  ('spinach', 'Spinach', 'g', null, null),
  ('chickpeas', 'Chickpeas', 'g', null, null),
  ('lentils', 'Lentils', 'g', null, null),
  ('tofu', 'Tofu', 'g', null, null),
  ('chicken-breast', 'Chicken breast', 'g', null, null),
  ('salmon', 'Salmon', 'g', null, null),
  ('egg', 'Egg', 'each', null, 60),
  ('milk', 'Milk', 'ml', 1.03, null),
  ('yogurt', 'Yogurt', 'g', null, null),
  ('cheese', 'Cheese', 'g', null, null),
  ('bread', 'Bread', 'g', null, 35),
  ('olive-oil', 'Olive oil', 'ml', 0.91, null)
on conflict (slug) do nothing;

insert into public.ingredient_aliases (ingredient_id, alias, normalized_alias)
select id, name, lower(name)
from public.ingredients
on conflict (normalized_alias) do nothing;

insert into public.ingredient_dietary_tags (ingredient_id, dietary_tag_id)
select i.id, dt.id
from public.ingredients i
cross join public.dietary_tags dt
where i.slug in (
  'tomato', 'onion', 'garlic', 'rice', 'pasta', 'potato', 'carrot', 'broccoli',
  'spinach', 'chickpeas', 'lentils', 'tofu', 'bread', 'olive-oil'
)
and dt.slug in ('vegan', 'vegetarian')
on conflict do nothing;

insert into public.ingredient_dietary_tags (ingredient_id, dietary_tag_id)
select i.id, dt.id
from public.ingredients i
cross join public.dietary_tags dt
where i.slug in ('egg', 'milk', 'yogurt', 'cheese')
  and dt.slug = 'vegetarian'
on conflict do nothing;

insert into public.ingredient_allergens (ingredient_id, allergen_id)
select i.id, a.id
from public.ingredients i
join public.allergens a on (
  (i.slug in ('pasta', 'bread') and a.slug = 'gluten')
  or (i.slug = 'tofu' and a.slug = 'soybeans')
  or (i.slug = 'salmon' and a.slug = 'fish')
  or (i.slug = 'egg' and a.slug = 'eggs')
  or (i.slug in ('milk', 'yogurt', 'cheese') and a.slug = 'milk')
)
on conflict do nothing;

insert into public.ingredient_storage_guidance (
  ingredient_id,
  storage_location,
  unopened_min_days,
  unopened_max_days,
  opened_min_days,
  opened_max_days,
  instructions
)
select
  i.id,
  guidance.storage_location,
  guidance.unopened_min_days,
  guidance.unopened_max_days,
  guidance.opened_min_days,
  guidance.opened_max_days,
  guidance.instructions
from public.ingredients i
join (values
  ('tomato', 'counter', 3, 7, null, null, 'Keep at room temperature away from direct sunlight; refrigerate once fully ripe if needed.'),
  ('onion', 'pantry', 14, 30, 3, 7, 'Store whole onions in a cool, dry, ventilated place. Refrigerate cut onion in a sealed container.'),
  ('garlic', 'pantry', 21, 60, 3, 7, 'Keep whole bulbs dry and ventilated. Refrigerate peeled cloves in a sealed container.'),
  ('broccoli', 'refrigerator', 3, 5, null, null, 'Refrigerate unwashed in a loose or perforated bag.'),
  ('spinach', 'refrigerator', 3, 7, null, null, 'Refrigerate dry with an absorbent towel in a ventilated container.'),
  ('milk', 'refrigerator', 5, 10, 3, 7, 'Keep refrigerated and return it promptly after use; follow the package date.'),
  ('bread', 'counter', 3, 5, 3, 5, 'Keep sealed at room temperature or freeze portions for longer storage.')
) as guidance(
  slug,
  storage_location,
  unopened_min_days,
  unopened_max_days,
  opened_min_days,
  opened_max_days,
  instructions
) on guidance.slug = i.slug
on conflict (ingredient_id, storage_location) do nothing;
