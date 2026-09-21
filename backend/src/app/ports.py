from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ParsedReceipt:
    merchant_name: str | None
    purchased_at: datetime | None
    total_amount: Decimal | None
    currency_code: str | None
    raw_ocr: dict[str, Any]
    lines: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class GeneratedRecipe:
    title: str
    servings: Decimal
    instructions: list[Any]
    nutrition: dict[str, Any]
    ingredients: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DiscountOffer:
    ingredient_id: int
    merchant_name: str
    price: Decimal
    currency_code: str


class ReceiptParser(Protocol):
    async def parse(self, image_path: str) -> ParsedReceipt: ...


class RecipeGenerator(Protocol):
    async def generate(self, request: dict[str, Any]) -> list[GeneratedRecipe]: ...


class DiscountProvider(Protocol):
    async def find_offers(self, ingredient_ids: list[int], location: str | None) -> list[DiscountOffer]: ...


class NotificationPublisher(Protocol):
    async def schedule_expiry(self, pantry_item_id: int, notify_at: datetime) -> None: ...
