from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ingredient(TimestampMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("base_unit in ('g', 'ml', 'each')", name="ingredients_base_unit_check"),
        CheckConstraint("typical_shelf_life_days >= 0", name="ingredients_typical_shelf_life_days_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    base_unit: Mapped[str] = mapped_column(Text)
    dietary_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    allergens: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    recommended_storage_location: Mapped[str | None] = mapped_column(Text)
    typical_shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    storage_instructions: Mapped[str | None] = mapped_column(Text)
    density_g_per_ml: Mapped[Decimal | None] = mapped_column(Numeric)
    average_unit_weight_g: Mapped[Decimal | None] = mapped_column(Numeric)


class IngredientStorageRule(TimestampMixin, Base):
    __tablename__ = "ingredient_storage_rules"
    __table_args__ = (
        CheckConstraint(
            "storage_state in ('as_purchased', 'opened', 'ripe', 'cut')",
            name="ingredient_storage_rules_storage_state_check",
        ),
        CheckConstraint(
            "recommended_storage_location in ('pantry', 'refrigerator', 'freezer', 'counter', 'other')",
            name="ingredient_storage_rules_location_check",
        ),
        CheckConstraint("shelf_life_days >= 0", name="ingredient_storage_rules_shelf_life_check"),
        CheckConstraint(
            "freezer_shelf_life_days >= 0", name="ingredient_storage_rules_freezer_shelf_life_check"
        ),
    )

    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="CASCADE"), primary_key=True
    )
    storage_state: Mapped[str] = mapped_column(Text, primary_key=True)
    recommended_storage_location: Mapped[str] = mapped_column(Text)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    freezer_shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    storage_instructions: Mapped[str] = mapped_column(Text)
    avoidance_notes: Mapped[str | None] = mapped_column(Text)


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "daily_calorie_target between 500 and 10000",
            name="profiles_daily_calorie_target_check",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    display_name: Mapped[str | None] = mapped_column(Text)
    dietary_preferences: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    allergies: Mapped[list[str]] = mapped_column(JSONB, default=list)
    preferred_cuisines: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    preferred_tastes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    daily_calorie_target: Mapped[int | None] = mapped_column(Integer)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(Text, default="en-NL")
    timezone: Mapped[str] = mapped_column(Text, default="Europe/Amsterdam")
    currency_code: Mapped[str] = mapped_column(String(3), default="EUR")


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="recipes_id_user_id_key"),
        CheckConstraint("source in ('manual', 'generated')", name="recipes_source_check"),
        CheckConstraint("servings > 0", name="recipes_servings_check"),
        CheckConstraint("prep_minutes >= 0", name="recipes_prep_minutes_check"),
        CheckConstraint("cook_minutes >= 0", name="recipes_cook_minutes_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=False
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    cuisine: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    servings: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("1"))
    prep_minutes: Mapped[int] = mapped_column(Integer, default=0)
    cook_minutes: Mapped[int] = mapped_column(Integer, default=0)
    instructions: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    nutrition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", lazy="raise", order_by="RecipeIngredient.position"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        ForeignKeyConstraint(
            ["recipe_id", "user_id"],
            ["recipes.id", "recipes.user_id"],
            ondelete="CASCADE",
            name="recipe_ingredients_recipe_id_user_id_fkey",
        ),
        UniqueConstraint("recipe_id", "position", name="recipe_ingredients_recipe_id_position_key"),
        CheckConstraint("position > 0", name="recipe_ingredients_position_check"),
        CheckConstraint("quantity > 0", name="recipe_ingredients_quantity_check"),
        CheckConstraint("unit in ('g', 'ml', 'each')", name="recipe_ingredients_unit_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    recipe_id: Mapped[int] = mapped_column(BigInteger)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    position: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    preparation_note: Mapped[str | None] = mapped_column(Text)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients", lazy="raise")
    ingredient: Mapped[Ingredient] = relationship(lazy="raise")


class MealPlan(TimestampMixin, Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="meal_plans_id_user_id_key"),
        CheckConstraint("end_date >= start_date and end_date <= start_date + 31", name="meal_plans_check"),
        CheckConstraint("checkout_budget >= 0", name="meal_plans_checkout_budget_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    checkout_budget: Mapped[Decimal | None] = mapped_column(Numeric)
    currency_code: Mapped[str] = mapped_column(String(3))
    selected_meal_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=lambda: ["dinner"])
    status: Mapped[str] = mapped_column(Text, default="draft")

    meals: Mapped[list[MealPlanMeal]] = relationship(
        back_populates="meal_plan",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="MealPlanMeal.meal_date, MealPlanMeal.id",
    )


class MealPlanMeal(TimestampMixin, Base):
    __tablename__ = "meal_plan_meals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_plan_id", "user_id"],
            ["meal_plans.id", "meal_plans.user_id"],
            ondelete="CASCADE",
            name="meal_plan_meals_meal_plan_id_user_id_fkey",
        ),
        ForeignKeyConstraint(
            ["recipe_id", "user_id"],
            ["recipes.id", "recipes.user_id"],
            ondelete="RESTRICT",
            name="meal_plan_meals_recipe_id_user_id_fkey",
        ),
        UniqueConstraint("id", "user_id", name="meal_plan_meals_id_user_id_key"),
        UniqueConstraint(
            "meal_plan_id", "meal_date", "meal_type", name="meal_plan_meals_meal_plan_id_meal_date_meal_type_key"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    meal_plan_id: Mapped[int] = mapped_column(BigInteger)
    meal_date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[str] = mapped_column(Text)
    requested_cuisine: Mapped[str | None] = mapped_column(Text)
    requested_category: Mapped[str | None] = mapped_column(Text)
    recipe_id: Mapped[int | None] = mapped_column(BigInteger)
    servings: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("1"))
    status: Mapped[str] = mapped_column(Text, default="requested")

    meal_plan: Mapped[MealPlan] = relationship(back_populates="meals", lazy="raise")


class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="receipts_id_user_id_key"),
        CheckConstraint(
            "status in ('uploaded', 'processing', 'review', 'confirmed', 'failed')",
            name="receipts_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    merchant_name: Mapped[str | None] = mapped_column(Text)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric)
    currency_code: Mapped[str] = mapped_column(String(3))
    image_path: Mapped[str | None] = mapped_column(Text)
    image_delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="uploaded")
    raw_ocr: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[ReceiptItem]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="raise", order_by="ReceiptItem.line_number"
    )


class ReceiptItem(TimestampMixin, Base):
    __tablename__ = "receipt_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "user_id"],
            ["receipts.id", "receipts.user_id"],
            ondelete="CASCADE",
            name="receipt_items_receipt_id_user_id_fkey",
        ),
        UniqueConstraint("id", "user_id", name="receipt_items_id_user_id_key"),
        UniqueConstraint("receipt_id", "line_number", name="receipt_items_receipt_id_line_number_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    receipt_id: Mapped[int] = mapped_column(BigInteger)
    line_number: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    ingredient_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric)
    line_total: Mapped[Decimal | None] = mapped_column(Numeric)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    review_status: Mapped[str] = mapped_column(Text, default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    receipt: Mapped[Receipt] = relationship(back_populates="items", lazy="raise")


class PantryItem(TimestampMixin, Base):
    __tablename__ = "pantry_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_item_id", "user_id"],
            ["receipt_items.id", "receipt_items.user_id"],
            ondelete="RESTRICT",
            name="pantry_items_receipt_item_id_user_id_fkey",
        ),
        UniqueConstraint("id", "user_id", name="pantry_items_id_user_id_key"),
        UniqueConstraint("receipt_item_id", name="pantry_items_receipt_item_id_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    receipt_item_id: Mapped[int | None] = mapped_column(BigInteger)
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    storage_location: Mapped[str] = mapped_column(Text, default="pantry")
    storage_state: Mapped[str] = mapped_column(Text, default="as_purchased")
    storage_state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    best_before_on: Mapped[date | None] = mapped_column(Date)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(Text, default="available")

    ingredient: Mapped[Ingredient] = relationship(lazy="raise")


class ShoppingList(TimestampMixin, Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meal_plan_id", "user_id"],
            ["meal_plans.id", "meal_plans.user_id"],
            ondelete="CASCADE",
            name="shopping_lists_meal_plan_id_user_id_fkey",
        ),
        UniqueConstraint("id", "user_id", name="shopping_lists_id_user_id_key"),
        UniqueConstraint("meal_plan_id", name="shopping_lists_meal_plan_id_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.user_id", ondelete="CASCADE")
    )
    meal_plan_id: Mapped[int] = mapped_column(BigInteger)
    currency_code: Mapped[str] = mapped_column(String(3))
    estimated_total: Mapped[Decimal | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, default="active")
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[ShoppingListItem]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan", lazy="raise", order_by="ShoppingListItem.id"
    )


class ShoppingListItem(TimestampMixin, Base):
    __tablename__ = "shopping_list_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shopping_list_id", "user_id"],
            ["shopping_lists.id", "shopping_lists.user_id"],
            ondelete="CASCADE",
            name="shopping_list_items_shopping_list_id_user_id_fkey",
        ),
        CheckConstraint("source in ('generated', 'manual')", name="shopping_list_items_source_check"),
        CheckConstraint("status in ('pending', 'bought', 'skipped')", name="shopping_list_items_status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    shopping_list_id: Mapped[int] = mapped_column(BigInteger)
    ingredient_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    custom_label: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="generated")
    required_quantity: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    pantry_quantity: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    to_buy_quantity: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    unit: Mapped[str | None] = mapped_column(Text)
    needed_by_date: Mapped[date | None] = mapped_column(Date)
    estimated_price: Mapped[Decimal | None] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(Text, default="pending")

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items", lazy="raise")


class WasteEvent(Base):
    __tablename__ = "waste_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pantry_item_id", "user_id"],
            ["pantry_items.id", "pantry_items.user_id"],
            ondelete="RESTRICT",
            name="waste_events_pantry_item_id_user_id_fkey",
        ),
        CheckConstraint("reason in ('expired', 'spoiled', 'unused', 'other')", name="waste_events_reason_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    pantry_item_id: Mapped[int] = mapped_column(BigInteger)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric)
    estimated_weight_g: Mapped[Decimal | None] = mapped_column(Numeric)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
