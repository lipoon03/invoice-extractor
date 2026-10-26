
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Literal, Any

from extractor.models import Invoice
from extractor.prompt import build_prompt
from extractor.providers import Provider, ProviderResponse

Mode = Literal["prompt_only", "schema_enforced"]


@dataclass
class ExtractionResult:
    invoice: Invoice
    raw_text: str
    seconds: float
    total_tokens: int | None = None
    thinking_tokens: int | None = None


# A generic currency name is insufficient to identify one ISO currency.
_AMBIGUOUS_CURRENCY_PATTERNS = (
    re.compile(r"ريال", re.IGNORECASE),
    re.compile(r"دينار", re.IGNORECASE),
)

# Explicit qualifiers that can disambiguate Arabic currency names.
_CURRENCY_QUALIFIERS = re.compile(
    r"(?:"
    r"سعودي|السعودي|السعودية|"
    r"قطري|القطري|قطرية|"
    r"يمني|اليمني|"
    r"عماني|العماني|"
    r"كويتي|الكويتي|"
    r"أردني|اردني|الأردني|الاردني|"
    r"عراقي|العراقي|"
    r"بحريني|البحريني|"
    r"ليبي|الليبي|"
    r"تونسي|التونسي|"
    r"جزائري|الجزائري|"
    r"كويتي|الكويتي|"
    r"saudi|qatari|yemeni|omani|kuwaiti|jordanian|"
    r"iraqi|bahraini|libyan|tunisian|algerian"
    r")",
    re.IGNORECASE,
)

# Explicit ISO codes in the source text.
_ISO_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:SAR|QAR|YER|OMR|KWD|JOD|IQD|BHD|"
    r"LYD|TND|DZD|USD|EUR|GBP|AED)(?![A-Za-z])",
    re.IGNORECASE,
)


def _validate_currency_from_source(text: str, invoice: Invoice) -> Invoice:
    """Avoid retaining a guessed currency for ambiguous Arabic names."""
    source = text.lower()

    has_ambiguous_name = any(
        pattern.search(source)
        for pattern in _AMBIGUOUS_CURRENCY_PATTERNS
    )
    if not has_ambiguous_name or invoice.currency is None:
        return invoice

    # An explicit ISO code or a country-specific qualifier provides
    # evidence that the currency may be identifiable.
    if _ISO_CODE_PATTERN.search(text) or _CURRENCY_QUALIFIERS.search(text):
        return invoice

    # Generic "riyal" or "dinar" alone cannot identify a unique currency.
    invoice.currency = None
    return invoice


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    # Accept fenced JSON from prompt-only models, but validate the parsed object strictly.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Recover a single JSON object if the model added surrounding prose.
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def extract(text: str, provider: Provider, mode: Mode) -> ExtractionResult:
    """Extract an invoice, validate its schema, and check currency evidence."""
    if mode not in ("prompt_only", "schema_enforced"):
        raise ValueError("mode must be 'prompt_only' or 'schema_enforced'")

    prompt = build_prompt(text)
    start = time.perf_counter()
    response: ProviderResponse = provider.generate(
        prompt,
        schema_enforced=(mode == "schema_enforced"),
    )
    seconds = time.perf_counter() - start

    payload = _parse_json(response.raw_text)
    invoice = Invoice.model_validate(payload)
    invoice = _validate_currency_from_source(text, invoice)

    return ExtractionResult(
        invoice=invoice,
        raw_text=response.raw_text,
        seconds=seconds,
        total_tokens=response.total_tokens,
        thinking_tokens=response.thinking_tokens,
    )
