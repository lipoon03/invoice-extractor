import pytest
from pydantic import ValidationError

from extractor.models import Invoice


def test_valid_invoice():
    invoice = Invoice(invoice_number="001042", date="2026-10-01", total_amount=3500, currency="EGP")
    assert invoice.invoice_number == "001042"
    assert invoice.total_amount == 3500


def test_leading_zeroes_are_preserved():
    assert Invoice(invoice_number="0007", date=None, total_amount=None, currency=None).invoice_number == "0007"


@pytest.mark.parametrize("value", [1042, None, 10.42])
def test_invoice_number_rejects_non_string(value):
    with pytest.raises(ValidationError):
        Invoice(invoice_number=value, date=None, total_amount=None, currency=None)


@pytest.mark.parametrize("value", ["01/02/2026", "2026-2-01", "not-a-date"])
def test_date_must_be_iso(value):
    with pytest.raises(ValidationError):
        Invoice(invoice_number="A1", date=value, total_amount=1, currency="USD")


def test_missing_date_is_null():
    assert Invoice(invoice_number="A1", date=None, total_amount=1, currency="USD").date is None


@pytest.mark.parametrize("value", ["3500 جنيه", "1,200", True])
def test_amount_rejects_text_and_bool(value):
    with pytest.raises(ValidationError):
        Invoice(invoice_number="A1", date=None, total_amount=value, currency="EGP")


@pytest.mark.parametrize("value", ["egp", "US", "دولار", "US1"])
def test_currency_must_be_iso_style_code(value):
    with pytest.raises(ValidationError):
        Invoice(invoice_number="A1", date=None, total_amount=1, currency=value)


def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        Invoice(invoice_number="A1", date=None, total_amount=1, currency=None, extra="no")
