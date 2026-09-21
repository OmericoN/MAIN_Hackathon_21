-- Waste-first recipe generation and weekly meal planning.
-- Compatible with storage guidance already on main: this does not recreate
-- ingredient_storage_rules or pantry storage_state columns.

create table public.ingredient_package_options (
  id bigint generated always as identity primary key,
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  label text not null check (btrim(label) <> ''),
  quantity numeric(14, 4) not null check (quantity > 0),
  unit text not null check (unit in ('g', 'ml', 'each')),
  estimated_price numeric(12, 2) check (estimated_price >= 0),
  currency_code text check (currency_code ~ '^[A-Z]{3}$'),
  is_default boolean not null default false,
  can_freeze boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ingredient_id, quantity, unit),
  check ((estimated_price is null) = (currency_code is null))
);

create index ingredient_package_options_ingredient_id_idx
  on public.ingredient_package_options (ingredient_id);

create trigger ingredient_package_options_set_updated_at
before update on public.ingredient_package_options
for each row execute function public.set_updated_at();

create table public.meal_plan_generation_previews (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(user_id) on delete cascade,
  status text not null default 'ready' check (status in ('ready', 'failed', 'confirmed')),
  request jsonb not null check (jsonb_typeof(request) = 'object'),
  candidates jsonb not null check (jsonb_typeof(candidates) = 'array'),
  solution jsonb not null check (jsonb_typeof(solution) = 'object'),
  prompt_version text not null,
  model text not null,
  failure_reason text,
  expires_at timestamptz not null default (now() + interval '24 hours'),
  confirmed_plan_id bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id),
  constraint meal_plan_generation_previews_confirmed_plan_id_user_id_fkey
    foreign key (confirmed_plan_id, user_id)
    references public.meal_plans(id, user_id) on delete cascade
);

create index meal_plan_generation_previews_user_created_idx
  on public.meal_plan_generation_previews (user_id, created_at desc);
create index meal_plan_generation_previews_expiry_idx
  on public.meal_plan_generation_previews (expires_at) where status = 'ready';
create index meal_plan_generation_previews_confirmed_plan_idx
  on public.meal_plan_generation_previews (confirmed_plan_id)
  where confirmed_plan_id is not null;

create trigger meal_plan_generation_previews_set_updated_at
before update on public.meal_plan_generation_previews
for each row execute function public.set_updated_at();

alter table public.recipes
  add column preference_tags text[] not null default '{}',
  add column generation_metadata jsonb not null default '{}'::jsonb
    check (jsonb_typeof(generation_metadata) = 'object');

alter table public.meal_plans
  add column planning_request jsonb not null default '{}'::jsonb
    check (jsonb_typeof(planning_request) = 'object'),
  add column optimizer_summary jsonb not null default '{}'::jsonb
    check (jsonb_typeof(optimizer_summary) = 'object');

alter table public.meal_plan_meals
  add column preparation_mode text not null default 'fresh'
    check (preparation_mode in ('fresh', 'leftover')),
  add column source_meal_id bigint,
  add column prepared_servings numeric(8, 2) not null default 1 check (prepared_servings > 0),
  add column consumed_servings numeric(8, 2) not null default 1 check (consumed_servings > 0),
  add constraint meal_plan_meals_source_meal_id_user_id_fkey
    foreign key (source_meal_id, user_id)
    references public.meal_plan_meals(id, user_id) on delete cascade;

create index meal_plan_meals_source_meal_id_idx
  on public.meal_plan_meals (source_meal_id) where source_meal_id is not null;

alter table public.shopping_list_items
  add column package_quantity numeric(14, 4) check (package_quantity > 0),
  add column package_count integer check (package_count > 0),
  add column projected_leftover_quantity numeric(14, 4)
    check (projected_leftover_quantity >= 0),
  add column price_source text check (
    price_source in ('catalog', 'receipt_history', 'user_override', 'unknown')
  ),
  add column storage_action text;

insert into public.ingredients (
  slug, name, base_unit, dietary_tags, allergens,
  recommended_storage_location, typical_shelf_life_days,
  storage_instructions, density_g_per_ml, average_unit_weight_g
) values
  ('ground-beef', 'Ground beef', 'g', '{}', '{}', 'refrigerator', 2, 'Keep refrigerated and use promptly or freeze.', null, null),
  ('chicken-thigh', 'Chicken thigh', 'g', '{}', '{}', 'refrigerator', 2, 'Keep refrigerated and separate from ready-to-eat food.', null, null),
  ('beef-steak', 'Beef steak', 'g', '{}', '{}', 'refrigerator', 3, 'Keep refrigerated or freeze.', null, null),
  ('prawns', 'Prawns', 'g', '{}', array['crustaceans'], 'refrigerator', 2, 'Keep refrigerated and use promptly or freeze.', null, null),
  ('canned-tuna', 'Canned tuna', 'g', '{}', array['fish'], 'pantry', 730, 'Store unopened in a cool dry place; refrigerate after opening.', null, null),
  ('soy-sauce', 'Soy sauce', 'ml', array['vegan', 'vegetarian'], array['soybeans', 'gluten'], 'pantry', 365, 'Refrigerate after opening for best quality.', 1.16, null),
  ('honey', 'Honey', 'g', array['vegetarian'], '{}', 'pantry', 730, 'Store sealed at room temperature.', null, null),
  ('mustard', 'Mustard', 'g', array['vegan', 'vegetarian'], array['mustard'], 'refrigerator', 180, 'Refrigerate after opening.', null, null),
  ('gochujang', 'Gochujang', 'g', array['vegan', 'vegetarian'], array['soybeans'], 'refrigerator', 180, 'Refrigerate after opening.', null, null),
  ('sesame-oil', 'Sesame oil', 'ml', array['vegan', 'vegetarian'], array['sesame'], 'pantry', 365, 'Store sealed away from heat and light.', 0.92, null),
  ('ginger', 'Ginger', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 21, 'Keep dry and refrigerated.', null, null),
  ('spring-onion', 'Spring onion', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 7, 'Refrigerate in a loose bag.', null, 15),
  ('noodles', 'Noodles', 'g', array['vegetarian'], array['gluten'], 'pantry', 365, 'Store dry and sealed.', null, null),
  ('tortilla', 'Tortilla', 'each', array['vegetarian'], array['gluten'], 'pantry', 14, 'Keep sealed; refrigerate after opening.', null, 45),
  ('black-beans', 'Black beans', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 730, 'Store unopened in a cool dry place.', null, null),
  ('kidney-beans', 'Kidney beans', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 730, 'Store unopened in a cool dry place.', null, null),
  ('coconut-milk', 'Coconut milk', 'ml', array['vegan', 'vegetarian'], '{}', 'pantry', 730, 'Refrigerate after opening and use promptly.', 1.01, null),
  ('curry-paste', 'Curry paste', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 90, 'Refrigerate after opening.', null, null),
  ('lime', 'Lime', 'each', array['vegan', 'vegetarian'], '{}', 'refrigerator', 21, 'Refrigerate for longest quality.', null, 70),
  ('lemon', 'Lemon', 'each', array['vegan', 'vegetarian'], '{}', 'refrigerator', 21, 'Refrigerate for longest quality.', null, 90),
  ('red-bell-pepper', 'Red bell pepper', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 7, 'Refrigerate dry.', null, 160),
  ('courgette', 'Courgette', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 7, 'Refrigerate dry.', null, 200),
  ('mushrooms', 'Mushrooms', 'g', array['vegan', 'vegetarian'], '{}', 'refrigerator', 5, 'Refrigerate in a paper bag.', null, null),
  ('green-peas', 'Green peas', 'g', array['vegan', 'vegetarian'], '{}', 'freezer', 180, 'Keep frozen until use.', null, null),
  ('passata', 'Passata', 'ml', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Refrigerate after opening and use promptly.', 1.04, null),
  ('canned-tomatoes', 'Canned tomatoes', 'g', array['vegan', 'vegetarian'], '{}', 'pantry', 730, 'Transfer leftovers to a covered container and refrigerate.', null, null),
  ('cream', 'Cream', 'ml', array['vegetarian'], array['milk'], 'refrigerator', 7, 'Keep refrigerated.', 1.01, null),
  ('parmesan', 'Parmesan', 'g', array['vegetarian'], array['milk'], 'refrigerator', 30, 'Wrap and refrigerate.', null, null),
  ('mozzarella', 'Mozzarella', 'g', array['vegetarian'], array['milk'], 'refrigerator', 7, 'Keep refrigerated in its liquid until opened.', null, null),
  ('flour', 'Flour', 'g', array['vegan', 'vegetarian'], array['gluten'], 'pantry', 365, 'Store dry and sealed.', null, null),
  ('breadcrumbs', 'Breadcrumbs', 'g', array['vegetarian'], array['gluten'], 'pantry', 180, 'Store dry and sealed.', null, null),
  ('vegetable-stock', 'Vegetable stock', 'ml', array['vegan', 'vegetarian'], '{}', 'pantry', 365, 'Refrigerate after opening.', 1.0, null),
  ('chicken-stock', 'Chicken stock', 'ml', '{}', '{}', 'pantry', 365, 'Refrigerate after opening.', 1.0, null),
  ('sesame-seeds', 'Sesame seeds', 'g', array['vegan', 'vegetarian'], array['sesame'], 'pantry', 180, 'Store sealed away from heat.', null, null)
on conflict (slug) do nothing;

insert into public.ingredient_storage_rules (
  ingredient_id, storage_state, recommended_storage_location,
  shelf_life_days, freezer_shelf_life_days, storage_instructions
)
select i.id, 'as_purchased', coalesce(i.recommended_storage_location, 'pantry'),
       i.typical_shelf_life_days,
       case when i.slug in ('ground-beef', 'chicken-thigh', 'beef-steak', 'prawns') then 90 else null end,
       coalesce(i.storage_instructions, 'Follow package guidance.')
from public.ingredients i
where not exists (
  select 1 from public.ingredient_storage_rules r
  where r.ingredient_id = i.id and r.storage_state = 'as_purchased'
);

with package(slug, label, quantity, unit, can_freeze) as (values
  ('ground-beef', '500 g pack', 500::numeric, 'g', true),
  ('chicken-breast', '500 g pack', 500, 'g', true),
  ('chicken-thigh', '600 g pack', 600, 'g', true),
  ('beef-steak', '400 g pack', 400, 'g', true),
  ('salmon', '2 fillets', 250, 'g', true),
  ('prawns', '250 g pack', 250, 'g', true),
  ('tofu', '375 g block', 375, 'g', true),
  ('rice', '1 kg bag', 1000, 'g', false),
  ('pasta', '500 g pack', 500, 'g', false),
  ('noodles', '250 g pack', 250, 'g', false),
  ('potato', '1 kg bag', 1000, 'g', false),
  ('onion', '3 onion bag', 330, 'g', false),
  ('garlic', 'bulb', 50, 'g', false),
  ('tomato', '500 g pack', 500, 'g', false),
  ('carrot', '500 g bag', 500, 'g', false),
  ('broccoli', 'head', 350, 'g', true),
  ('spinach', '200 g bag', 200, 'g', true),
  ('red-bell-pepper', '3 pepper pack', 480, 'g', true),
  ('courgette', '2 courgettes', 400, 'g', true),
  ('mushrooms', '250 g pack', 250, 'g', true),
  ('green-peas', '450 g frozen bag', 450, 'g', true),
  ('egg', '6 eggs', 6, 'each', false),
  ('milk', '1 litre carton', 1000, 'ml', false),
  ('cream', '250 ml carton', 250, 'ml', false),
  ('yogurt', '500 g tub', 500, 'g', false),
  ('cheese', '250 g pack', 250, 'g', true),
  ('parmesan', '150 g wedge', 150, 'g', true),
  ('mozzarella', '125 g ball', 125, 'g', false),
  ('bread', 'loaf', 700, 'g', true),
  ('tortilla', '8 tortillas', 8, 'each', true),
  ('soy-sauce', '150 ml bottle', 150, 'ml', false),
  ('honey', '350 g jar', 350, 'g', false),
  ('mustard', '200 g jar', 200, 'g', false),
  ('gochujang', '200 g tub', 200, 'g', false),
  ('sesame-oil', '150 ml bottle', 150, 'ml', false),
  ('ginger', '100 g piece', 100, 'g', true),
  ('spring-onion', '100 g bunch', 100, 'g', false),
  ('black-beans', '400 g can', 400, 'g', false),
  ('kidney-beans', '400 g can', 400, 'g', false),
  ('coconut-milk', '400 ml can', 400, 'ml', false),
  ('curry-paste', '200 g jar', 200, 'g', false),
  ('lime', 'single lime', 1, 'each', false),
  ('lemon', 'single lemon', 1, 'each', false),
  ('passata', '500 ml carton', 500, 'ml', true),
  ('canned-tomatoes', '400 g can', 400, 'g', false),
  ('olive-oil', '500 ml bottle', 500, 'ml', false),
  ('flour', '1 kg bag', 1000, 'g', false),
  ('breadcrumbs', '200 g pack', 200, 'g', false),
  ('vegetable-stock', '500 ml carton', 500, 'ml', true),
  ('chicken-stock', '500 ml carton', 500, 'ml', true),
  ('sesame-seeds', '100 g jar', 100, 'g', false)
)
insert into public.ingredient_package_options (
  ingredient_id, label, quantity, unit, is_default, can_freeze
)
select i.id, p.label, p.quantity, p.unit, true, p.can_freeze
from package p join public.ingredients i on i.slug = p.slug
on conflict (ingredient_id, quantity, unit) do update
set label = excluded.label, is_default = excluded.is_default, can_freeze = excluded.can_freeze;

update public.ingredient_package_options option
set estimated_price = case ingredient.slug
      when 'ground-beef' then 5.49 when 'chicken-breast' then 5.99
      when 'chicken-thigh' then 5.49 when 'beef-steak' then 7.49
      when 'salmon' then 6.49 when 'prawns' then 4.99 when 'tofu' then 2.79
      when 'rice' then 2.49 when 'pasta' then 1.39 when 'noodles' then 1.89
      when 'egg' then 2.49 when 'milk' then 1.39 when 'cream' then 1.69
      when 'cheese' then 3.29 when 'parmesan' then 3.49 when 'mozzarella' then 1.39
      when 'olive-oil' then 5.99 when 'gochujang' then 3.49
      else 2.49 end,
    currency_code = 'EUR'
from public.ingredients ingredient
where ingredient.id = option.ingredient_id
  and option.is_default
  and option.estimated_price is null;

alter table public.ingredient_package_options enable row level security;
create policy ingredient_package_options_authenticated_read
on public.ingredient_package_options for select to authenticated using (true);

alter table public.meal_plan_generation_previews enable row level security;
create policy meal_plan_generation_previews_owner_access
on public.meal_plan_generation_previews for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

revoke all on public.ingredient_package_options from anon, authenticated;
revoke all on public.meal_plan_generation_previews from anon, authenticated;
grant select on public.ingredient_package_options to authenticated;
grant select, insert, update, delete on public.meal_plan_generation_previews to authenticated;
grant usage, select on sequence public.ingredient_package_options_id_seq to authenticated;
