"""Scan a grocery receipt image into English product lines and a total.

OCR is handled by Veryfi. Dutch names are normalized, then batch-translated
with MarianMT so either side can be replaced later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ReceiptItem:
    product_name: str
    quantity: float | None
    unit_price: float | None


@dataclass
class ReceiptResult:
    items: list[ReceiptItem]
    total_price: float | None


# ---------------------------------------------------------------------------
# Environment / Veryfi client
# ---------------------------------------------------------------------------


def _load_env() -> None:
    here = Path(__file__).resolve().parent
    candidates = (
        Path.cwd() / ".env",
        here / ".env",
        here.parent / ".env",
        here.parent.parent / ".env",
    )
    loaded = False
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            loaded = True
    if not loaded:
        load_dotenv()


def _veryfi_client():
    _load_env()
    client_id = os.getenv("VERYFI_CLIENT_ID", "").strip()
    client_secret = os.getenv("VERYFI_CLIENT_SECRET", "").strip()
    username = os.getenv("VERYFI_USERNAME", "").strip()
    api_key = os.getenv("VERYFI_API_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("VERYFI_CLIENT_ID", client_id),
            ("VERYFI_CLIENT_SECRET", client_secret),
            ("VERYFI_USERNAME", username),
            ("VERYFI_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Missing Veryfi credentials in .env: " + ", ".join(missing))

    from veryfi import Client

    return Client(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        api_key=api_key,
        timeout=120,
    )


def fetch_veryfi_receipt(image_path: str) -> dict[str, Any]:
    """Call Veryfi and return the raw document JSON. Swap this for another OCR later."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Receipt image not found: {image_path}")

    client = _veryfi_client()
    return client.process_document(
        file_path=str(path),
        document_type="receipt",
        boost_mode=True,
    )


# ---------------------------------------------------------------------------
# Non-product filtering
# ---------------------------------------------------------------------------

NON_PRODUCT_TYPES = {
    "discount",
    "payment",
    "fee",
    "giftcard",
    "donation",
    "lottery",
    "toll",
    "refund",
}

# Whole-line / leading-token noise typical of Dutch supermarket receipts.
NON_PRODUCT_PATTERNS = (
    re.compile(
        r"^(totaal|total|subtotal|subtotaal|te\s+betalen|tebetalen|eindbedrag|"
        r"btw|vat|pin|contant|contactloos|contact|betaald|paid\s+by|"
        r"wisselgeld|korting|kortingen|voordeel|actie|gratis|spaar|bonuskaart|bonus|"
        r"statiegeld|emballage|munt|visa|mastercard|maestro|ideal|"
        r"creditcard|debit|kaart|pas\b|chipknip|bancontact|"
        r"kassa|kassier|kassière|medewerker|bedankt|welkom|"
        r"bonnr|bonnummer|transactie|terminal|merchant|"
        r"ah\s*bonus|jumbo\s*extra|lidl\s*plus|"
        r"uw\s+(voordeel|korting|aankoop)|aantal\s+artikelen|"
        r"klant|lidl\s*pluskaart|pluskaart)\b",
        re.IGNORECASE,
    ),
)

STORE_PREFIXES = re.compile(
    r"^(ah|albert\s*heijn|jumbo|lidl|plus|dirk|dekamarkt|aldi|spar)\b[\s.\-]*",
    re.IGNORECASE,
)

QUANTITY_PREFIX = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*[x×]\s+",
    re.IGNORECASE,
)

PRICE_IN_NAME = re.compile(r"\s+\d+[.,]\d{2}\s*$")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_non_product_line(description: str, line_type: str | None = None) -> bool:
    if line_type and line_type.lower() in NON_PRODUCT_TYPES:
        return True
    text = _normalize_text(description)
    if not text:
        return True
    return any(pattern.search(text) for pattern in NON_PRODUCT_PATTERNS)


# ---------------------------------------------------------------------------
# Quantity / unit price
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _money(value: Any) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, 2)


def quantity_from_description(description: str) -> float | None:
    match = QUANTITY_PREFIX.match(description)
    if not match:
        return None
    return _as_float(match.group(1))


def derive_unit_price(
    quantity: float | None,
    unit_price: float | None,
    line_total: float | None,
) -> tuple[float | None, float | None]:
    """Return (quantity, unit_price), filling gaps from line total when possible."""
    qty = quantity if quantity and quantity > 0 else None
    price = unit_price

    if price is None and line_total is not None and qty:
        price = round(line_total / qty, 2)
    elif (
        price is not None
        and line_total is not None
        and qty
        and qty > 1
        and abs(price - line_total) < 0.005
    ):
        # OCR sometimes puts the line total in `price`.
        price = round(line_total / qty, 2)
    elif price is None and line_total is not None and qty is None:
        price = line_total
        qty = 1.0
    elif price is not None and qty is None:
        qty = 1.0

    return qty, _money(price)


# ---------------------------------------------------------------------------
# Translation (independent of OCR)
# ---------------------------------------------------------------------------

MARIAN_MODEL_NAME = "Helsinki-NLP/opus-mt-nl-en"

# Receipt shorthand -> full Dutch. Lookups are case-insensitive.
# Keep this dictionary easy to extend later.
ABBREVIATIONS = {
    "HALFVL": "halfvolle",
    "HALFVOL": "halfvolle",
    "HALFV": "halfvolle",
    "MLK": "melk",
    "VOL": "volle",
    "KIP": "kip",
    "KIPFILET": "kipfilet",
    "GEH": "gehakt",
    "RUNDGEH": "rundgehakt",
    "RUNDGEHAKT": "rundgehakt",
    "GR": "gram",
    "ST": "stuk",
    "YH": "yoghurt",
    "DIEPV": "diepvries",
}

# Prefer grocery meaning over a literal MarianMT rendering.
# Only applied when the Dutch source actually contained that term.
_FOOD_MEANING_FIXES = (
    ("half-full", "semi-skimmed"),
    ("half full", "semi-skimmed"),
    ("half-milk", "semi-skimmed milk"),
    ("half milk", "semi-skimmed milk"),
    ("half-fat", "semi-skimmed"),
    ("semi-full", "semi-skimmed"),
    ("chicken fillet", "chicken breast"),
    ("chicken filet", "chicken breast"),
    ("minced beef", "ground beef"),
    ("beef mince", "ground beef"),
    ("minced meat", "ground beef"),
    ("beef and veal", "ground beef"),
    ("full milk", "whole milk"),
    ("whole-fat", "whole"),
)

_DUTCH_FOOD_MEANING = {
    "halfvolle": "semi-skimmed",
    "volle": "whole",
    "magere": "skimmed",
    "mager": "skimmed",
    "kipfilet": "chicken breast",
    "rundgehakt": "ground beef",
    "rundergehakt": "ground beef",
    "diepvries": "frozen",
    "lactosevrij": "lactose-free",
    "vetarm": "low-fat",
    "pittig": "spicy",
}

_SIZE_OR_PERCENT = re.compile(
    r"\d+(?:[.,]\d+)?\s*%|\d+(?:[.,]\d+)?\s*(?:ml|cl|dl|l|g|gr|kg|st)\b",
    re.IGNORECASE,
)

_marian_tokenizer = None
_marian_model = None
_marian_device = None
_marian_load_failed = False
_marian_load_error: str | None = None


def clean_dutch_product_name(name: str) -> str:
    """Strip receipt noise while keeping product wording, flavours, and sizes."""
    cleaned = _normalize_text(name)
    cleaned = PRICE_IN_NAME.sub("", cleaned)
    cleaned = QUANTITY_PREFIX.sub("", cleaned)
    cleaned = STORE_PREFIXES.sub("", cleaned)
    return _normalize_text(cleaned)


def _is_size_token(token: str) -> bool:
    compact = token.replace(" ", "")
    return bool(
        re.fullmatch(
            r"\d+(?:[.,]\d+)?%|\d+(?:[.,]\d+)?(?:ml|cl|dl|l|g|gr|kg|st)",
            compact,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_unknown_abbreviation(token: str) -> bool:
    """Keep opaque receipt codes. All-caps Dutch words are not codes."""
    core = token.strip(".,;:()[]")
    if not core.isalpha():
        return False
    if not core.isupper():
        return False
    key = core.upper()
    if key in ABBREVIATIONS or key == "BIO":
        return False
    vowels = sum(character in "AEIOU" for character in key)
    return 2 <= len(core) <= 5 and vowels == 0


def _format_size_token(token: str) -> str | None:
    match = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)(%|ml|cl|dl|l|g|gr|kg|st)",
        token.replace(" ", ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    amount, unit = match.group(1), match.group(2).lower()
    if unit == "l":
        unit = "L"
    elif unit in {"gr", "g"}:
        unit = "g"
    elif unit == "st":
        unit = "ST"
    elif unit == "%":
        unit = "%"
    return f"{amount}{unit}"


def expand_abbreviations(name: str) -> str:
    """Expand known supermarket shorthand; leave unknown codes unchanged."""
    parts: list[str] = []
    for token in name.split():
        stripped = token.strip(".,;:()")
        if not stripped:
            continue
        if _is_size_token(stripped):
            parts.append(_format_size_token(stripped) or stripped)
            continue
        key = stripped.upper()
        if key in ABBREVIATIONS:
            parts.append(ABBREVIATIONS[key])
            continue
        if key == "BIO":
            parts.append("BIO")
            continue
        if _looks_like_unknown_abbreviation(stripped):
            parts.append(stripped)
            continue
        parts.append(stripped.lower())
    return _normalize_text(" ".join(parts))


def _split_preserved_tokens(name: str) -> tuple[str, list[str]]:
    """Pull sizes, percentages, BIO, and unknown codes out of the MT input."""
    preserved: list[str] = []

    def _keep_size(match: re.Match[str]) -> str:
        token = match.group(0).replace(" ", "")
        preserved.append(_format_size_token(token) or token)
        return " "

    remainder = _SIZE_OR_PERCENT.sub(_keep_size, name)
    words: list[str] = []
    for token in remainder.split():
        if token.upper() == "BIO" or _looks_like_unknown_abbreviation(token):
            preserved.append("BIO" if token.upper() == "BIO" else token)
        else:
            words.append(token)
    return _normalize_text(" ".join(words)), preserved


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _reattach_preserved(english: str, preserved: list[str]) -> str:
    prefixes: list[str] = []
    suffixes: list[str] = []
    compact_result = _compact(english)
    for token in preserved:
        if _compact(token) in compact_result or token.lower() in english.lower():
            continue
        if _format_size_token(token) or _is_size_token(token):
            suffixes.append(token)
        else:
            prefixes.append(token)
        compact_result = _compact(" ".join(prefixes + [english] + suffixes))
    return _normalize_text(" ".join(prefixes + [english] + suffixes))


def _apply_food_meaning(dutch: str, english: str) -> str:
    result = english
    dutch_tokens = [
        token.lower() for token in dutch.split() if not _is_size_token(token)
    ]
    dutch_set = set(dutch_tokens)
    lowered = result.lower()
    for literal, preferred in _FOOD_MEANING_FIXES:
        if literal in lowered:
            result = re.sub(re.escape(literal), preferred, result, flags=re.IGNORECASE)
            lowered = result.lower()
    for source, preferred in _DUTCH_FOOD_MEANING.items():
        if source not in dutch_set or preferred in lowered:
            continue
        if re.search(rf"\b{re.escape(source)}\b", result, flags=re.IGNORECASE):
            result = re.sub(
                rf"\b{re.escape(source)}\b", preferred, result, flags=re.IGNORECASE
            )
            lowered = result.lower()
            continue
        content = [token for token in dutch_tokens if token != "bio"]
        if content == [source]:
            result = preferred
            lowered = result.lower()
    if "melk" in dutch_set and "milk" not in lowered:
        result = _normalize_text(f"{result} milk")
    return _normalize_text(result)


def _format_product_name(name: str) -> str:
    parts: list[str] = []
    for index, token in enumerate(name.split()):
        size = _format_size_token(token)
        if size:
            parts.append(size)
        elif token.upper() == "BIO":
            parts.append("BIO")
        elif token.isupper() and _looks_like_unknown_abbreviation(token):
            parts.append(token)
        elif index == 0:
            parts.append(token[:1].upper() + token[1:].lower())
        else:
            parts.append(token.lower())
    return " ".join(parts)


def _translation_unreliable(source: str, translated: str) -> bool:
    text = translated.strip()
    if not text:
        return True
    if len(text) > max(48, len(source) * 4):
        return True
    return False


def _load_marian(debug: bool = False):
    """Load tokenizer + model once and reuse them for later scans."""
    global _marian_tokenizer, _marian_model, _marian_device
    global _marian_load_failed, _marian_load_error

    if _marian_model is not None and _marian_tokenizer is not None:
        return _marian_tokenizer, _marian_model
    if _marian_load_failed:
        if debug and _marian_load_error:
            print(f"MarianMT unavailable: {_marian_load_error}", file=sys.stderr)
        return None, None

    try:
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tokenizer = MarianTokenizer.from_pretrained(MARIAN_MODEL_NAME)
        model = MarianMTModel.from_pretrained(MARIAN_MODEL_NAME)
        model.to(device)
        model.eval()
        _marian_tokenizer = tokenizer
        _marian_model = model
        _marian_device = device
        return tokenizer, model
    except Exception as exc:
        _marian_load_failed = True
        _marian_load_error = str(exc)
        if debug:
            print(f"MarianMT failed to load: {exc}", file=sys.stderr)
        return None, None


def _marian_generate(texts: list[str], debug: bool = False) -> list[str] | None:
    tokenizer, model = _load_marian(debug=debug)
    if tokenizer is None or model is None:
        return None

    import torch

    try:
        inputs = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=48,
        )
        inputs = {key: value.to(_marian_device) for key, value in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=False,
                num_beams=1,
                max_new_tokens=24,
                max_length=None,
            )
        return tokenizer.batch_decode(generated, skip_special_tokens=True)
    except Exception as exc:
        if debug:
            print(f"MarianMT batch translation failed: {exc}", file=sys.stderr)
        return None


def _translate_batch_conservatively(
    texts: list[str],
    fallbacks: list[str],
    debug: bool = False,
) -> list[str]:
    """Translate all names in one batch; fall back per item on failure."""
    if not texts:
        return []

    translated = _marian_generate(texts, debug=debug)
    if translated is not None and len(translated) == len(texts):
        results: list[str] = []
        for item, source, fallback in zip(translated, texts, fallbacks):
            cleaned = item.strip()
            if _translation_unreliable(source, cleaned):
                results.append(fallback)
            else:
                results.append(cleaned)
        return results

    results = []
    for text, fallback in zip(texts, fallbacks):
        single = _marian_generate([text], debug=False)
        if single and not _translation_unreliable(text, single[0]):
            results.append(single[0].strip())
        else:
            results.append(fallback)
    return results


_DUTCH_LEXICON = {
    *(key.lower() for key in ABBREVIATIONS),
    *(value.lower() for value in ABBREVIATIONS.values()),
    *_DUTCH_FOOD_MEANING.keys(),
    "melk",
    "bananen",
    "brood",
    "kaas",
    "yoghurt",
    "uien",
    "tomaten",
    "aardappelen",
    "aardappels",
    "kip",
    "gehakt",
    "volle",
    "halfvolle",
    "diepvries",
    "biologisch",
}


def _needs_dutch_translation(text: str) -> bool:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z]+", text)}
    return bool(tokens & _DUTCH_LEXICON)


def translate_product_names(
    product_names: list[str],
    *,
    debug: bool = False,
) -> list[str]:
    """Batch-translate cleaned Dutch grocery names into English."""
    if not product_names:
        return []

    normalized_names = [
        expand_abbreviations(clean_dutch_product_name(name)) for name in product_names
    ]
    split_names = [_split_preserved_tokens(name) for name in normalized_names]
    to_translate: list[str] = []
    translate_indexes: list[int] = []
    english_names: list[str] = [""] * len(normalized_names)

    for index, (normalized, (words, preserved)) in enumerate(
        zip(normalized_names, split_names)
    ):
        source = words or normalized
        if not _needs_dutch_translation(source):
            english_names[index] = _format_product_name(
                _reattach_preserved(normalized, preserved)
            ) or normalized
            continue
        translate_indexes.append(index)
        to_translate.append(source)

    translated = _translate_batch_conservatively(
        to_translate,
        fallbacks=[normalized_names[index] for index in translate_indexes],
        debug=debug,
    )

    for index, raw_english in zip(translate_indexes, translated):
        dutch = normalized_names[index]
        _words, preserved = split_names[index]
        try:
            english = raw_english.strip() or dutch
            english = _apply_food_meaning(dutch, english)
            english = _reattach_preserved(english, preserved)
            formatted = _format_product_name(english)
            english_names[index] = formatted or dutch
        except Exception:
            english_names[index] = _format_product_name(dutch) or dutch
    return english_names


def translate_product_name(product_name: str, *, debug: bool = False) -> str:
    """Translate a single product name. Prefer translate_product_names() for receipts."""
    return translate_product_names([product_name], debug=debug)[0]


# ---------------------------------------------------------------------------
# Veryfi response parsing (provider-specific)
# ---------------------------------------------------------------------------


def parse_veryfi_response(
    data: dict[str, Any],
    *,
    debug: bool = False,
) -> ReceiptResult:
    """Turn a Veryfi document payload into a ReceiptResult.

    Other OCR providers can implement a similar parser without touching
    translation or the public scan_receipt() API.
    """
    raw_items = data.get("line_items") or []
    if debug:
        print("--- raw Veryfi line items ---")
        print(json.dumps(raw_items, indent=2, ensure_ascii=False, default=str))
        print()

    kept: list[dict[str, Any]] = []
    for raw in raw_items:
        description = _normalize_text(
            str(raw.get("description") or raw.get("text") or "")
        )
        sku = _normalize_text(str(raw.get("sku") or ""))
        if sku and _is_size_token(sku) and sku.lower() not in description.lower():
            description = _normalize_text(f"{description} {sku}")
        line_type = raw.get("type")
        reason = None
        if is_non_product_line(
            description, line_type if isinstance(line_type, str) else None
        ):
            reason = f"filtered non-product (type={line_type!r})"
        if reason:
            if debug:
                print(f"FILTERED: {description!r} - {reason}")
            continue

        qty = _as_float(raw.get("quantity"))
        if qty is None:
            qty = quantity_from_description(description)
        from_text = quantity_from_description(description)
        if from_text and (qty is None or qty == 1) and from_text != qty:
            qty = from_text

        qty, unit_price = derive_unit_price(
            qty,
            _money(raw.get("price")),
            _money(raw.get("total")),
        )

        kept.append(
            {
                "raw": description,
                "quantity": qty,
                "unit_price": unit_price,
            }
        )

    english_names = translate_product_names(
        [item["raw"] for item in kept],
        debug=debug,
    )
    items = [
        ReceiptItem(
            product_name=english,
            quantity=row["quantity"],
            unit_price=row["unit_price"],
        )
        for row, english in zip(kept, english_names)
    ]

    if debug:
        for row, english in zip(kept, english_names):
            normalized = expand_abbreviations(clean_dutch_product_name(row["raw"]))
            print(f"Raw:        {row['raw']}")
            print(f"Normalized: {normalized}")
            print(f"English:    {english}")
            print()

    return ReceiptResult(
        items=items,
        total_price=_money(data.get("total")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_receipt(image_path: str, debug: bool = False) -> ReceiptResult:
    data = fetch_veryfi_receipt(image_path)
    if debug:
        print("--- Veryfi document totals ---")
        print(
            json.dumps(
                {
                    "total": data.get("total"),
                    "subtotal": data.get("subtotal"),
                    "tax": data.get("tax"),
                    "vendor": (data.get("vendor") or {}).get("name")
                    if isinstance(data.get("vendor"), dict)
                    else data.get("vendor"),
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        print()
    return parse_veryfi_response(data, debug=debug)


def result_to_json_dict(result: ReceiptResult) -> dict[str, Any]:
    return {
        "items": [
            {
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in result.items
        ],
        "total_price": result.total_price,
    }


# ---------------------------------------------------------------------------
# Sample receipt test
# ---------------------------------------------------------------------------

SAMPLE_RECEIPT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "receipts" / "receipt1.png"
)


def test_scan_sample_receipt(debug: bool = True) -> ReceiptResult:
    """Run the scanner against data/receipts/receipt1.png."""
    if not SAMPLE_RECEIPT_PATH.is_file():
        raise FileNotFoundError(
            f"Sample receipt not found: {SAMPLE_RECEIPT_PATH}"
        )
    return scan_receipt(str(SAMPLE_RECEIPT_PATH), debug=debug)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a grocery receipt image into English product lines."
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        help="Path to a receipt image",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Scan data/receipts/receipt1.png",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw Veryfi lines, keep/filter decisions, and translations",
    )
    args = parser.parse_args(argv)

    if args.test:
        result = test_scan_sample_receipt(debug=args.debug)
    elif args.image_path:
        result = scan_receipt(args.image_path, debug=args.debug)
    else:
        parser.error("Provide an image path or use --test")

    print(json.dumps(result_to_json_dict(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
