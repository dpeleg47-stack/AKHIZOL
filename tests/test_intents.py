from services.intents import is_cart_intent
from services.optimizer import best_kind


def test_cart_intent():
    for t in ["добавь в корзину", "Добавь всё в корзину", "собери корзину", "add to cart", "תוסיף לסל"]:
        assert is_cart_intent(t), t
    for t in ["молоко 10, хлеб 5", "корзина для белья 2 шт", "x" * 80 + " в корзину"]:
        assert not is_cart_intent(t), t


def test_best_kind():
    plans = {"single": {"missing": [], "total": 205.0}, "split": {"missing": [], "total": 195.0}}
    assert best_kind(plans) == "split"
    plans["split"]["missing"] = [1]
    assert best_kind(plans) == "single"  # меньше ненайденных важнее цены
    assert best_kind({"single": None, "split": None}) is None
    assert best_kind(None) is None
