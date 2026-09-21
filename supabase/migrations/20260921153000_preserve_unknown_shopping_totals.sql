-- A shopping list with unpriced required items must not be represented as free.
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
  set estimated_total = case
        when exists (
          select 1
          from public.shopping_list_items
          where shopping_list_id = v_list_id
            and user_id = v_user_id
            and to_buy_quantity > 0
            and estimated_price is null
        ) then null
        else (
          select coalesce(sum(estimated_price), 0)
          from public.shopping_list_items
          where shopping_list_id = v_list_id and user_id = v_user_id
        )
      end,
      calculated_at = now()
  where id = v_list_id;

  return v_list_id;
end;
$$;
