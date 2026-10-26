from evaluate import field_errors, percentile95


def test_field_errors_reports_only_mismatched_fields():
    expected = {"invoice_number": "001", "date": None, "total_amount": 12.5, "currency": None}
    actual = {"invoice_number": "1", "date": None, "total_amount": 12.5, "currency": "USD"}
    assert field_errors(expected, actual) == [
        "invoice_number: expected='001', actual='1'",
        "currency: expected=None, actual='USD'",
    ]


def test_field_errors_reports_extraction_exception():
    assert field_errors({}, None, "ValueError: bad JSON") == ["extraction_error: ValueError: bad JSON"]


def test_p95_nearest_rank():
    assert percentile95([1, 2, 3, 4, 5]) == 5
    assert percentile95([]) is None
