import json
import pytest
from pydantic import ValidationError

from extractor.extract import extract
from extractor.providers import Provider, ProviderResponse


class FakeProvider(Provider):
    name = "fake"
    model = "fake-model"

    def __init__(self, output):
        self.output = output
        self.last_schema_enforced = None
        self.last_prompt = None

    def generate(self, prompt, *, schema_enforced):
        self.last_schema_enforced = schema_enforced
        self.last_prompt = prompt
        return ProviderResponse(raw_text=self.output, total_tokens=17, thinking_tokens=0)


def test_extract_validates_and_returns_invoice():
    provider = FakeProvider(json.dumps({
        "invoice_number": "0001", "date": "2026-10-01",
        "total_amount": 12.5, "currency": "EGP"
    }))
    result = extract("Invoice 0001 total 12.5 EGP", provider, "prompt_only")
    assert result.invoice.invoice_number == "0001"
    assert result.total_tokens == 17
    assert provider.last_schema_enforced is False


def test_schema_mode_passed_to_provider():
    provider = FakeProvider('{"invoice_number":"1","date":null,"total_amount":null,"currency":null}')
    extract("Invoice 1", provider, "schema_enforced")
    assert provider.last_schema_enforced is True


def test_invalid_json_fails():
    with pytest.raises(Exception):
        extract("Invoice 1", FakeProvider("not json"), "prompt_only")


def test_invalid_schema_fails_pydantic_validation():
    provider = FakeProvider('{"invoice_number":1,"date":null,"total_amount":"12 EGP","currency":null}')
    with pytest.raises(ValidationError):
        extract("Invoice 1", provider, "prompt_only")


def test_shared_prompt_contains_rules_for_both_modes():
    p1, p2 = FakeProvider('{"invoice_number":"1","date":null,"total_amount":null,"currency":null}'), FakeProvider('{"invoice_number":"1","date":null,"total_amount":null,"currency":null}')
    extract("Invoice 1", p1, "prompt_only")
    extract("Invoice 1", p2, "schema_enforced")
    assert p1.last_prompt == p2.last_prompt
    assert "ISO 4217" in p1.last_prompt
    assert "leading zero" in p1.last_prompt.lower()


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        extract("Invoice 1", FakeProvider("{}"), "other")
