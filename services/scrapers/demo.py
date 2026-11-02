"""Демо-поставщики с детерминированными ценами (DEMO_MODE=1) — для проверки всей цепочки без порталов."""
import time
import zlib

from core.config import settings
from services.matching import Candidate
from services.optimizer import Supplier
from services.scrapers.base import SCRAPERS, CartResult, CheckoutResult, SupplierScraper
from services.scrapers.registry import SUPPLIERS, SupplierInfo


def _make(key: str, title: str, fee: float, free_from: float | None, min_order: float):
    class _Demo(SupplierScraper):
        name = key
        demo = True

        async def login(self) -> None:
            return None

        async def terms(self) -> Supplier:
            return Supplier(key, fee, free_from, min_order)

        async def search(self, query: str) -> list[Candidate]:
            h = zlib.crc32(f"{key}|{query}".encode())
            if h % 7 == 0:  # у поставщика нет этого товара
                return []
            return [Candidate(title=query, unit_price=round(5 + (h % 4000) / 100, 2))]

        async def _add_to_cart(self, lines: list[dict]) -> CartResult:
            return CartResult(total=round(sum(ln["line_total"] for ln in lines), 2), url=f"https://demo.invalid/{key}/cart")

        async def _checkout(self, expected_total: float) -> CheckoutResult:
            return CheckoutResult(total=expected_total, confirmation=f"DEMO-{key}-{int(time.time())}")

    _Demo.__name__ = f"Demo_{key}"
    SCRAPERS[key] = _Demo
    SUPPLIERS[key] = SupplierInfo(key, title, scraper_ready=True, hidden=True)


if settings.demo_mode:
    _make("demo_a", "Demo A (доставка 30₪, бесплатно от 300₪)", 30, 300, 0)
    _make("demo_b", "Demo B (доставка 20₪, мин. заказ 50₪)", 20, 150, 50)
    _make("demo_c", "Demo C (бесплатная доставка)", 0, None, 0)
