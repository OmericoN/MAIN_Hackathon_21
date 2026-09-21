-- Quality-first storage guidance.  Ingredients retain their existing summary
-- columns for backwards compatibility; this table is the contextual source of
-- truth for a product's condition after purchase.
create table public.ingredient_storage_rules (
  ingredient_id bigint not null references public.ingredients(id) on delete cascade,
  storage_state text not null check (
    storage_state in ('as_purchased', 'opened', 'ripe', 'cut')
  ),
  recommended_storage_location text not null check (
    recommended_storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')
  ),
  shelf_life_days integer check (shelf_life_days >= 0),
  freezer_shelf_life_days integer check (freezer_shelf_life_days >= 0),
  storage_instructions text not null,
  avoidance_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (ingredient_id, storage_state)
);

create index ingredient_storage_rules_state_idx
  on public.ingredient_storage_rules (storage_state, ingredient_id);

create trigger ingredient_storage_rules_set_updated_at
before update on public.ingredient_storage_rules
for each row execute function public.set_updated_at();

-- Every catalog ingredient has a baseline rule.  This imports the already
-- curated catalog values instead of relying on a fragile list of numeric IDs.
insert into public.ingredient_storage_rules (
  ingredient_id,
  storage_state,
  recommended_storage_location,
  shelf_life_days,
  freezer_shelf_life_days,
  storage_instructions
)
select
  i.id,
  'as_purchased',
  coalesce(i.recommended_storage_location, 'pantry'),
  i.typical_shelf_life_days,
  case
    when i.slug like 'frozen-%' or i.recommended_storage_location = 'freezer' then 365
    when i.slug in (
      'bread', 'baguette', 'sourdough-bread', 'whole-wheat-bread', 'pita-bread', 'naan',
      'burger-bun', 'butter', 'unsalted-butter', 'puff-pastry', 'filo-pastry', 'pizza-dough',
      'chicken-breast', 'chicken-thigh', 'chicken-drumstick', 'chicken-wings', 'whole-chicken',
      'ground-beef', 'beef-steak', 'beef-stewing', 'pork-chop', 'pork-belly', 'pork-tenderloin',
      'ground-pork', 'sausage', 'lamb-chop', 'ground-lamb', 'lamb-shoulder', 'turkey-breast',
      'ground-turkey', 'duck-breast', 'salmon', 'cod', 'haddock', 'sea-bass', 'mackerel',
      'sardines', 'tuna-steak', 'prawns', 'squid', 'scallops', 'crab-meat', 'tofu',
      'silken-tofu', 'tempeh'
    ) then 90
    when i.slug in (
      'tomato', 'cherry-tomato', 'carrot', 'broccoli', 'spinach', 'cauliflower', 'kale',
      'lettuce', 'rocket', 'cabbage', 'red-cabbage', 'chinese-cabbage', 'brussels-sprouts',
      'courgette', 'aubergine', 'red-bell-pepper', 'green-bell-pepper', 'yellow-bell-pepper',
      'cucumber', 'celery', 'leek', 'green-beans', 'peas', 'corn-on-the-cob', 'mushrooms',
      'portobello-mushrooms', 'shiitake-mushrooms', 'asparagus', 'fennel-bulb', 'bok-choy',
      'okra', 'red-chilli', 'green-chilli', 'jalapeno', 'fresh-basil', 'fresh-parsley',
      'fresh-coriander', 'fresh-mint', 'fresh-dill', 'fresh-chives', 'fresh-thyme',
      'fresh-rosemary', 'fresh-sage', 'fresh-oregano'
    ) then 180
    else null
  end,
  coalesce(i.storage_instructions, 'Follow the package guidance.')
from public.ingredients i
on conflict (ingredient_id, storage_state) do nothing;

-- Quality-first corrections and condition-specific guidance for products
-- whose ideal storage changes after ripening, cutting, or opening.
update public.ingredient_storage_rules rule
set recommended_storage_location = guidance.location,
    shelf_life_days = guidance.shelf_life_days,
    freezer_shelf_life_days = guidance.freezer_shelf_life_days,
    storage_instructions = guidance.instructions,
    avoidance_notes = guidance.avoidance_notes
from (values
  ('fresh-basil', 'counter', 5, 90, 'Stand unwashed stems in a glass of water at room temperature and loosely cover the leaves.', 'Do not refrigerate basil; cold damages its leaves.'),
  ('aubergine', 'counter', 5, 90, 'Keep loose at cool room temperature and use promptly.', 'Avoid the coldest part of the refrigerator; aubergine is prone to chilling injury.'),
  ('watermelon', 'counter', 7, 90, 'Keep whole at room temperature; refrigerate only after cutting.', 'Keep cut melon covered and chilled.'),
  ('melon', 'counter', 7, 90, 'Keep whole at room temperature; refrigerate only after cutting.', 'Keep cut melon covered and chilled.'),
  ('red-wine', 'pantry', 730, null, 'Store sealed in a cool, dark place until opened.', 'After opening, refrigerate and reseal.'),
  ('white-wine', 'pantry', 730, null, 'Store sealed in a cool, dark place until opened.', 'After opening, refrigerate and reseal.')
) as guidance(slug, location, shelf_life_days, freezer_shelf_life_days, instructions, avoidance_notes)
join public.ingredients i on i.slug = guidance.slug
where rule.ingredient_id = i.id and rule.storage_state = 'as_purchased';

insert into public.ingredient_storage_rules (
  ingredient_id, storage_state, recommended_storage_location, shelf_life_days,
  freezer_shelf_life_days, storage_instructions, avoidance_notes
)
select i.id, rule.storage_state, rule.location, rule.shelf_life_days,
       rule.freezer_shelf_life_days, rule.instructions, rule.avoidance_notes
from (values
  ('tomato', 'ripe', 'refrigerator', 3, 90, 'Refrigerate only once fully ripe to slow further softening.', 'Bring to room temperature before eating for best flavour.'),
  ('tomato', 'cut', 'refrigerator', 3, 90, 'Cover the cut surface and refrigerate promptly.', null),
  ('cherry-tomato', 'ripe', 'refrigerator', 3, 90, 'Refrigerate only once fully ripe to slow further softening.', 'Bring to room temperature before eating for best flavour.'),
  ('cherry-tomato', 'cut', 'refrigerator', 3, 90, 'Cover cut tomatoes and refrigerate promptly.', null),
  ('pear', 'ripe', 'refrigerator', 5, 90, 'Refrigerate when the neck yields gently to extend eating quality.', null),
  ('avocado', 'ripe', 'refrigerator', 3, 90, 'Refrigerate once ripe; keep the stone in a cut half and cover it.', null),
  ('avocado', 'cut', 'refrigerator', 2, 90, 'Cover tightly with a little citrus juice to slow browning.', null),
  ('mango', 'ripe', 'refrigerator', 5, 180, 'Refrigerate once ripe.', null),
  ('pineapple', 'cut', 'refrigerator', 4, 180, 'Store cut pieces in a covered container.', null),
  ('kiwi', 'ripe', 'refrigerator', 7, 180, 'Refrigerate once yielding slightly.', null),
  ('peach', 'ripe', 'refrigerator', 3, 180, 'Refrigerate once ripe and handle gently.', null),
  ('plum', 'ripe', 'refrigerator', 5, 180, 'Refrigerate once ripe.', null),
  ('watermelon', 'cut', 'refrigerator', 5, 90, 'Cover cut surfaces or store pieces in a sealed container.', null),
  ('melon', 'cut', 'refrigerator', 5, 90, 'Cover cut surfaces or store pieces in a sealed container.', null),
  ('cucumber', 'cut', 'refrigerator', 3, 90, 'Wrap the cut end and refrigerate.', null),
  ('pumpkin', 'cut', 'refrigerator', 5, 180, 'Wrap the cut surface and refrigerate.', null),
  ('butternut-squash', 'cut', 'refrigerator', 5, 180, 'Wrap the cut surface and refrigerate.', null),
  ('fresh-basil', 'cut', 'refrigerator', 2, 90, 'Refrigerate cut basil in a covered container with a dry paper towel.', null),
  ('red-wine', 'opened', 'refrigerator', 5, null, 'Reseal and refrigerate after opening; use for cooking within five days.', null),
  ('white-wine', 'opened', 'refrigerator', 5, null, 'Reseal and refrigerate after opening; use within five days.', null),
  ('canned-chopped-tomatoes', 'opened', 'refrigerator', 4, 90, 'Transfer from the can to a covered container and refrigerate.', null),
  ('canned-peeled-tomatoes', 'opened', 'refrigerator', 4, 90, 'Transfer from the can to a covered container and refrigerate.', null),
  ('passata', 'opened', 'refrigerator', 5, 90, 'Refrigerate after opening or freeze portions.', null),
  ('tomato-paste', 'opened', 'refrigerator', 7, 90, 'Keep covered in the refrigerator or freeze tablespoon portions.', null),
  ('pesto', 'opened', 'refrigerator', 7, 90, 'Refrigerate promptly and cover the surface with a thin layer of oil.', null),
  ('milk', 'opened', 'refrigerator', 7, null, 'Keep below 4°C and follow the earlier package date.', null),
  ('yogurt', 'opened', 'refrigerator', 7, null, 'Keep sealed and use a clean spoon.', null),
  ('mayonnaise', 'opened', 'refrigerator', 60, null, 'Keep refrigerated and use a clean utensil.', null),
  ('jam', 'opened', 'refrigerator', 60, null, 'Refrigerate after opening and use a clean spoon.', null)
) as rule(slug, storage_state, location, shelf_life_days, freezer_shelf_life_days, instructions, avoidance_notes)
join public.ingredients i on i.slug = rule.slug
on conflict (ingredient_id, storage_state) do update
set recommended_storage_location = excluded.recommended_storage_location,
    shelf_life_days = excluded.shelf_life_days,
    freezer_shelf_life_days = excluded.freezer_shelf_life_days,
    storage_instructions = excluded.storage_instructions,
    avoidance_notes = excluded.avoidance_notes;

-- For remaining shelf-stable products that already state an opening condition,
-- provide safe baseline guidance. More specific rows above take precedence.
insert into public.ingredient_storage_rules (
  ingredient_id, storage_state, recommended_storage_location, shelf_life_days,
  freezer_shelf_life_days, storage_instructions
)
select
  i.id,
  'opened',
  'refrigerator',
  least(coalesce(i.typical_shelf_life_days, 14), 30),
  null,
  'Refrigerate after opening, keep sealed, and follow the earlier package date.'
from public.ingredients i
where i.storage_instructions ilike '%after opening%'
on conflict (ingredient_id, storage_state) do nothing;

-- Preserve existing API consumers by making the old ingredient summary match
-- the audited as-purchased rule.
update public.ingredients i
set recommended_storage_location = rule.recommended_storage_location,
    typical_shelf_life_days = rule.shelf_life_days,
    storage_instructions = rule.storage_instructions
from public.ingredient_storage_rules rule
where rule.ingredient_id = i.id
  and rule.storage_state = 'as_purchased';

alter table public.pantry_items
  add column storage_state text,
  add column storage_state_changed_at timestamptz;

update public.pantry_items
set storage_state = 'as_purchased',
    storage_state_changed_at = coalesce(acquired_at, created_at, now())
where storage_state is null;

alter table public.pantry_items
  alter column storage_state set default 'as_purchased',
  alter column storage_state set not null,
  alter column storage_state_changed_at set default now(),
  alter column storage_state_changed_at set not null,
  add constraint pantry_items_storage_state_check check (
    storage_state in ('as_purchased', 'opened', 'ripe', 'cut')
  );

create index pantry_items_user_storage_state_idx
  on public.pantry_items (user_id, storage_state)
  where status = 'available';

-- A state change may shorten an estimate, but never extends a package or
-- previously computed date. The user's actual storage_location is untouched.
create or replace function public.apply_pantry_storage_state_guidance()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_rule public.ingredient_storage_rules;
  v_reference_at timestamptz;
  v_rule_best_before date;
begin
  if tg_op = 'INSERT' or new.storage_state is distinct from old.storage_state then
    v_reference_at := case
      when new.storage_state = 'opened' and new.opened_at is not null then new.opened_at
      when new.storage_state = 'as_purchased' then new.acquired_at
      else now()
    end;
    new.storage_state_changed_at := coalesce(v_reference_at, now());
  end if;

  select * into v_rule
  from public.ingredient_storage_rules
  where ingredient_id = new.ingredient_id
    and storage_state = new.storage_state;

  if not found then
    select * into v_rule
    from public.ingredient_storage_rules
    where ingredient_id = new.ingredient_id
      and storage_state = 'as_purchased';
  end if;

  if v_rule.shelf_life_days is not null then
    v_rule_best_before := new.storage_state_changed_at::date + v_rule.shelf_life_days;
    new.best_before_on := case
      when new.best_before_on is null then v_rule_best_before
      else least(new.best_before_on, v_rule_best_before)
    end;
  end if;

  return new;
end;
$$;

create trigger pantry_items_apply_storage_state_guidance
before insert or update of storage_state on public.pantry_items
for each row execute function public.apply_pantry_storage_state_guidance();

-- Receipt confirmation now uses the contextual as-purchased storage rule.
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
    user_id, ingredient_id, receipt_item_id, initial_quantity, remaining_quantity,
    unit, storage_location, storage_state, storage_state_changed_at, acquired_at,
    best_before_on, purchase_price, currency_code
  )
  select
    ri.user_id,
    ri.ingredient_id,
    ri.id,
    ri.quantity,
    ri.quantity,
    ri.unit,
    coalesce(rule.recommended_storage_location, i.recommended_storage_location, 'pantry'),
    'as_purchased',
    coalesce(v_receipt.purchased_at, now()),
    coalesce(v_receipt.purchased_at, now()),
    case
      when coalesce(rule.shelf_life_days, i.typical_shelf_life_days) is null then null
      else coalesce(v_receipt.purchased_at, now())::date
        + coalesce(rule.shelf_life_days, i.typical_shelf_life_days)
    end,
    ri.line_total,
    v_receipt.currency_code
  from public.receipt_items ri
  join public.ingredients i on i.id = ri.ingredient_id
  left join public.ingredient_storage_rules rule
    on rule.ingredient_id = i.id and rule.storage_state = 'as_purchased'
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

alter table public.ingredient_storage_rules enable row level security;
create policy ingredient_storage_rules_authenticated_read
on public.ingredient_storage_rules
for select to authenticated using (true);

grant select on public.ingredient_storage_rules to authenticated;

-- Deployment verification: this migration must never leave an ingredient
-- without its required as-purchased rule.
do $$
begin
  if exists (
    select 1
    from public.ingredients i
    left join public.ingredient_storage_rules rule
      on rule.ingredient_id = i.id and rule.storage_state = 'as_purchased'
    where rule.ingredient_id is null
  ) then
    raise exception 'Every ingredient must have an as_purchased storage rule';
  end if;
end;
$$;
