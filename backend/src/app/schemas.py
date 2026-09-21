from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


T = TypeVar("T")


class Page(APIModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    total: int


class ErrorResponse(APIModel):
    code: str
    message: str
    details: Any = None


class Unit(StrEnum):
    GRAM = "g"
    MILLILITER = "ml"
    EACH = "each"


class StorageLocation(StrEnum):
    PANTRY = "pantry"
    REFRIGERATOR = "refrigerator"
    FREEZER = "freezer"
    COUNTER = "counter"
    OTHER = "other"


class AllergenCode(StrEnum):
    GLUTEN = "gluten"
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    SOYBEANS = "soybeans"
    MILK = "milk"
    NUTS = "nuts"
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SULPHITES = "sulphites"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"


def _normalize_preferences(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Preference values must be a list")
    values = cast(list[object], value)
    if len(values) > 50:
        raise ValueError("Preference lists may contain at most 50 values")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            raise ValueError("Preference values must be strings")
        cleaned = item.strip().casefold()
        if not cleaned:
            raise ValueError("Preference values cannot be blank")
        if len(cleaned) > 100:
            raise ValueError("Preference values may contain at most 100 characters")
        if cleaned in seen:
            raise ValueError("Preference values must be unique")
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _normalize_allergies(value: object) -> list[str]:
    normalized = _normalize_preferences(value)
    if len(normalized) > len(AllergenCode):
        raise ValueError("Too many allergy values")
    return normalized


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class MealPlanStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    FAILED = "failed"


class MealStatus(StrEnum):
    REQUESTED = "requested"
    GENERATED = "generated"
    ACCEPTED = "accepted"
    COOKED = "cooked"
    SKIPPED = "skipped"


class PantryStatus(StrEnum):
    AVAILABLE = "available"
    DEPLETED = "depleted"
    DISCARDED = "discarded"


class ReceiptStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    REVIEW = "review"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ReceiptItemReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    IGNORED = "ignored"


class ShoppingListStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ShoppingItemStatus(StrEnum):
    PENDING = "pending"
    BOUGHT = "bought"
    SKIPPED = "skipped"


class WasteReason(StrEnum):
    EXPIRED = "expired"
    SPOILED = "spoiled"
    UNUSED = "unused"
    OTHER = "other"


class ProfileRead(APIModel):
    display_name: str | None
    dietary_preferences: list[str]
    allergies: list[AllergenCode]
    preferred_cuisines: list[str]
    preferred_tastes: list[str]
    daily_calorie_target: int | None
    onboarding_completed_at: datetime | None
    locale: str
    timezone: str
    currency_code: str
    created_at: datetime
    updated_at: datetime


class ProfilePatch(APIModel):
    display_name: str | None = Field(default=None, max_length=200)
    dietary_preferences: list[str] | None = None
    allergies: list[AllergenCode] | None = None
    preferred_cuisines: list[str] | None = None
    preferred_tastes: list[str] | None = None
    daily_calorie_target: int | None = Field(default=None, ge=500, le=10_000)
    locale: str | None = Field(default=None, min_length=2, max_length=35)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @field_validator(
        "dietary_preferences", "preferred_cuisines", "preferred_tastes", mode="before"
    )
    @classmethod
    def normalize_optional_preferences(cls, value: object):
        if value is None:
            raise ValueError("Preference lists cannot be null")
        return _normalize_preferences(value)

    @field_validator("allergies", mode="before")
    @classmethod
    def normalize_optional_allergies(cls, value: object):
        if value is None:
            raise ValueError("Allergies cannot be null")
        return _normalize_allergies(value)


class OnboardingPut(APIModel):
    display_name: str | None = Field(default=None, max_length=200)
    dietary_preferences: list[str] = Field(default_factory=list)
    allergies: list[AllergenCode] = Field(default_factory=list)
    preferred_cuisines: list[str] = Field(default_factory=list)
    preferred_tastes: list[str] = Field(default_factory=list)
    daily_calorie_target: int | None = Field(default=None, ge=500, le=10_000)

    @field_validator(
        "dietary_preferences", "preferred_cuisines", "preferred_tastes", mode="before"
    )
    @classmethod
    def normalize_preferences(cls, value: object):
        if value is None:
            raise ValueError("Preference lists cannot be null")
        return _normalize_preferences(value)

    @field_validator("allergies", mode="before")
    @classmethod
    def normalize_allergies(cls, value: object):
        if value is None:
            raise ValueError("Allergies cannot be null")
        return _normalize_allergies(value)


class IngredientRead(APIModel):
    id: int
    slug: str
    name: str
    base_unit: Unit
    dietary_tags: list[str]
    allergens: list[str]
    recommended_storage_location: StorageLocation | None
    typical_shelf_life_days: int | None
    storage_instructions: str | None


class PantryItemBase(APIModel):
    ingredient_id: int
    initial_quantity: Decimal = Field(gt=0)
    remaining_quantity: Decimal | None = Field(default=None, ge=0)
    unit: Unit
    storage_location: StorageLocation = StorageLocation.PANTRY
    acquired_at: datetime | None = None
    best_before_on: date | None = None
    opened_at: datetime | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_quantities_and_price(self) -> PantryItemBase:
        remaining = self.remaining_quantity if self.remaining_quantity is not None else self.initial_quantity
        if remaining > self.initial_quantity:
            raise ValueError("remaining_quantity cannot exceed initial_quantity")
        if (self.purchase_price is None) != (self.currency_code is None):
            raise ValueError("purchase_price and currency_code must be supplied together")
        return self


class PantryItemCreate(PantryItemBase):
    pass


class PantryItemPatch(APIModel):
    remaining_quantity: Decimal | None = Field(default=None, ge=0)
    storage_location: StorageLocation | None = None
    best_before_on: date | None = None
    opened_at: datetime | None = None
    status: PantryStatus | None = None


class PantryItemRead(APIModel):
    id: int
    ingredient_id: int
    initial_quantity: Decimal
    remaining_quantity: Decimal
    unit: Unit
    storage_location: StorageLocation
    acquired_at: datetime
    best_before_on: date | None
    opened_at: datetime | None
    purchase_price: Decimal | None
    currency_code: str | None
    status: PantryStatus
    created_at: datetime
    updated_at: datetime
    ingredient: IngredientRead


class RecipeIngredientInput(APIModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0)
    unit: Unit
    preparation_note: str | None = Field(default=None, max_length=500)
    optional: bool = False


class RecipeIngredientRead(RecipeIngredientInput):
    id: int
    position: int


class RecipeCreate(APIModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    source: str = Field(default="manual", pattern=r"^(manual|generated)$")
    cuisine: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    servings: Decimal = Field(default=Decimal("1"), gt=0)
    prep_minutes: int = Field(default=0, ge=0)
    cook_minutes: int = Field(default=0, ge=0)
    instructions: list[Any] = Field(default_factory=list)
    nutrition: dict[str, Any] = Field(default_factory=dict)
    saved_at: datetime | None = None
    ingredients: list[RecipeIngredientInput] = Field(default_factory=list)


class RecipePatch(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    cuisine: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    servings: Decimal | None = Field(default=None, gt=0)
    prep_minutes: int | None = Field(default=None, ge=0)
    cook_minutes: int | None = Field(default=None, ge=0)
    instructions: list[Any] | None = None
    nutrition: dict[str, Any] | None = None
    saved_at: datetime | None = None
    ingredients: list[RecipeIngredientInput] | None = None


class RecipeRead(APIModel):
    id: int
    title: str
    description: str | None
    source: str
    cuisine: str | None
    category: str | None
    servings: Decimal
    prep_minutes: int
    cook_minutes: int
    instructions: list[Any]
    nutrition: dict[str, Any]
    saved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ingredients: list[RecipeIngredientRead]


class MealPlanCreate(APIModel):
    name: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date
    checkout_budget: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    selected_meal_types: list[MealType] = Field(default_factory=lambda: [MealType.DINNER], min_length=1)

    @model_validator(mode="after")
    def validate_date_range(self) -> MealPlanCreate:
        day_count = (self.end_date - self.start_date).days
        if day_count < 0 or day_count > 31:
            raise ValueError("meal plan must span between 1 and 32 calendar days")
        if len(set(self.selected_meal_types)) != len(self.selected_meal_types):
            raise ValueError("selected_meal_types cannot contain duplicates")
        return self


class MealPlanPatch(APIModel):
    name: str | None = Field(default=None, max_length=200)
    checkout_budget: Decimal | None = Field(default=None, ge=0)
    status: MealPlanStatus | None = None


class MealSlotPatch(APIModel):
    requested_cuisine: str | None = Field(default=None, max_length=100)
    requested_category: str | None = Field(default=None, max_length=100)
    recipe_id: int | None = None
    servings: Decimal | None = Field(default=None, gt=0)
    status: MealStatus | None = None


class MealSlotRead(APIModel):
    id: int
    meal_date: date
    meal_type: MealType
    requested_cuisine: str | None
    requested_category: str | None
    recipe_id: int | None
    servings: Decimal
    status: MealStatus
    created_at: datetime
    updated_at: datetime


class MealPlanRead(APIModel):
    id: int
    name: str | None
    start_date: date
    end_date: date
    checkout_budget: Decimal | None
    currency_code: str
    selected_meal_types: list[MealType]
    status: MealPlanStatus
    created_at: datetime
    updated_at: datetime
    meals: list[MealSlotRead]


class ShoppingListItemPatch(APIModel):
    status: ShoppingItemStatus | None = None
    estimated_price: Decimal | None = Field(default=None, ge=0)


class ShoppingListItemRead(APIModel):
    id: int
    ingredient_id: int | None
    custom_label: str | None
    source: str
    required_quantity: Decimal
    pantry_quantity: Decimal
    to_buy_quantity: Decimal
    unit: Unit | None
    needed_by_date: date | None
    estimated_price: Decimal | None
    status: ShoppingItemStatus
    created_at: datetime
    updated_at: datetime


class ShoppingListRead(APIModel):
    id: int
    meal_plan_id: int
    currency_code: str
    estimated_total: Decimal | None
    status: ShoppingListStatus
    calculated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[ShoppingListItemRead]


class ReceiptCreate(APIModel):
    merchant_name: str | None = Field(default=None, max_length=300)
    purchased_at: datetime | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    image_path: str | None = Field(default=None, max_length=1000)


class ReceiptPatch(APIModel):
    merchant_name: str | None = Field(default=None, max_length=300)
    purchased_at: datetime | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    image_path: str | None = Field(default=None, max_length=1000)
    status: ReceiptStatus | None = None
    failure_reason: str | None = None


class ReceiptItemInput(APIModel):
    line_number: int = Field(gt=0)
    raw_text: str = Field(min_length=1)
    ingredient_id: int | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: Unit | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    line_total: Decimal | None = Field(default=None, ge=0)
    match_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    review_status: ReceiptItemReviewStatus = ReceiptItemReviewStatus.PENDING
    reviewed_at: datetime | None = None


class ReceiptExtraction(APIModel):
    merchant_name: str | None = Field(default=None, max_length=300)
    purchased_at: datetime | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    raw_ocr: dict[str, Any] = Field(default_factory=dict)
    items: list[ReceiptItemInput]

    @model_validator(mode="after")
    def unique_line_numbers(self) -> ReceiptExtraction:
        line_numbers = [item.line_number for item in self.items]
        if len(line_numbers) != len(set(line_numbers)):
            raise ValueError("receipt line numbers must be unique")
        return self


class ReceiptItemRead(ReceiptItemInput):
    id: int
    created_at: datetime
    updated_at: datetime


class ReceiptRead(APIModel):
    id: int
    merchant_name: str | None
    purchased_at: datetime | None
    total_amount: Decimal | None
    currency_code: str
    image_path: str | None
    image_delete_after: datetime | None
    status: ReceiptStatus
    raw_ocr: dict[str, Any]
    failure_reason: str | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[ReceiptItemRead]


class WasteEventCreate(APIModel):
    pantry_item_id: int
    quantity: Decimal = Field(gt=0)
    reason: WasteReason
    occurred_at: datetime | None = None


class WasteEventRead(APIModel):
    id: int
    pantry_item_id: int
    ingredient_id: int
    quantity: Decimal
    unit: Unit
    reason: WasteReason
    estimated_value: Decimal | None
    estimated_weight_g: Decimal | None
    occurred_at: datetime
    created_at: datetime


class HealthResponse(APIModel):
    status: str
    database: str
