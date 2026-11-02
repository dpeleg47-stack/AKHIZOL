from services.messenger import fallback_hebrew_order, normalize_phone


def test_phone():
    assert normalize_phone("050-123-4567") == "972501234567"
    assert normalize_phone("+972 50 123 4567") == "972501234567"
    assert normalize_phone("12345") is None


def test_fallback_has_items():
    t = fallback_hebrew_order([{"name_he": "חלב", "brand": "תנובה", "quantity": 10}])
    assert "חלב" in t and "10" in t
