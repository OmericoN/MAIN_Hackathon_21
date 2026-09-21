-- Keep storage guidance complete after recipe catalog inserts and the later
-- expanded ingredient catalog. Recipe planning reads freezer_shelf_life_days
-- from these same rows.

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
      'ground-beef', 'chicken-thigh', 'beef-steak', 'prawns',
      'chicken-breast', 'salmon', 'tofu'
    ) then 90
    else null
  end,
  coalesce(i.storage_instructions, 'Follow the package guidance.')
from public.ingredients i
on conflict (ingredient_id, storage_state) do nothing;
