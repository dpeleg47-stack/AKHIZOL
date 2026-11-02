import pytest

from core.permissions import Level, PermissionDenied, require
from services.matching import Candidate
from services.optimizer import Supplier
from services.scrapers.base import CartResult, CheckoutResult, SupplierScraper


class Fake(SupplierScraper):
    name = "fake"
    calls: list[str]

    async def login(self): ...
    async def terms(self): return Supplier("fake")
    async def search(self, query): return [Candidate(query, 1.0)]

    async def _add_to_cart(self, lines):
        self.__dict__.setdefault("calls", []).append("cart")
        return CartResult(10.0)

    async def _checkout(self, expected_total):
        self.__dict__.setdefault("calls", []).append("pay")
        return CheckoutResult(expected_total, "OK")


def test_require():
    require(Level.CART, Level.PRICES, "x")
    with pytest.raises(PermissionDenied):
        require(Level.PRICES, Level.CART, "x")


async def test_prices_only_cannot_write():
    s = Fake("", "", Level.PRICES)
    with pytest.raises(PermissionDenied):
        await s.add_to_cart([])
    with pytest.raises(PermissionDenied):
        await s.checkout(10, 100)
    assert not s.__dict__.get("calls")  # записывающий код не вызывался


async def test_cart_level_cannot_pay():
    s = Fake("", "", Level.CART)
    assert (await s.add_to_cart([])).total == 10.0
    with pytest.raises(PermissionDenied):
        await s.checkout(10, 100)


async def test_pay_respects_limit():
    s = Fake("", "", Level.PAY)
    with pytest.raises(PermissionDenied):
        await s.checkout(expected_total=500, max_total=100)
    assert (await s.checkout(50, 100)).confirmation == "OK"
