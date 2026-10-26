from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Invoice(BaseModel):
    """Normalized fields extracted from an invoice."""

    model_config = ConfigDict(extra="forbid", strict=True)

    invoice_number: Annotated[str, Field(description="Invoice identifier as text; preserve leading zeros.")]
    date: Annotated[str | None, Field(description="Invoice date in ISO YYYY-MM-DD format, or null when missing.")]
    total_amount: Annotated[float | None, Field(description="Numeric amount only, without currency symbol or thousands separators.")]
    currency: Annotated[str | None, Field(description="ISO 4217 currency code, or null when missing or ambiguous.")]

    @field_validator("invoice_number", mode="before")
    @classmethod
    def invoice_number_must_be_string(cls, value):
        # Do not coerce numbers to strings: doing so would silently lose leading zeroes.
        if not isinstance(value, str):
            raise ValueError("invoice_number must be a string; numeric values are rejected")
        return value

    @field_validator("date")
    @classmethod
    def validate_iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("date must be a valid ISO date YYYY-MM-DD or null") from exc
        if parsed.isoformat() != value:
            raise ValueError("date must use exactly YYYY-MM-DD")
        return value

    @field_validator("total_amount", mode="before")
    @classmethod
    def amount_is_numeric(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("total_amount must be a JSON number or null")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 3 or not value.isascii() or not value.isalpha() or value.upper() != value:
            raise ValueError("currency must be a three-letter uppercase ISO currency code or null")
        return value
