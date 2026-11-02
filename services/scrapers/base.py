"""Базовый класс скрейпера B2B-портала. Для поставщика реализуйте login(), terms(), search();
для записи в кабинет — _add_to_cart() и _checkout(). Публичные add_to_cart()/checkout() сами
проверяют разрешение пользователя, так что «записывающий» код невозможно вызвать без согласия."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.permissions import Level, PermissionDenied, require
from services.matching import Candidate
from services.optimizer import Supplier


@dataclass
class CartResult:
    total: float          # сумма товаров БЕЗ доставки
    url: str | None = None
    note: str = ""


@dataclass
class CheckoutResult:
    total: float
    confirmation: str     # номер заказа / подтверждение портала


class SupplierScraper(ABC):
    name: str  # ключ из registry.SUPPLIERS
    demo: bool = False

    def __init__(self, login: str, password: str, granted: Level = Level.PRICES):
        self.login_ = login
        self.password = password
        self.granted = granted

    # --- чтение (Level.PRICES) ---
    @abstractmethod
    async def login(self) -> None: ...

    @abstractmethod
    async def terms(self) -> Supplier:
        """Доставка: плата, порог бесплатной доставки, минимальный заказ."""

    @abstractmethod
    async def search(self, query: str) -> list[Candidate]:
        """Поиск в каталоге; цена — за единицу товара."""

    # --- запись (нужно отдельное разрешение) ---
    async def add_to_cart(self, lines: list[dict]) -> CartResult:
        require(self.granted, Level.CART, "сбор корзины")
        return await self._add_to_cart(lines)

    async def checkout(self, expected_total: float, max_total: float) -> CheckoutResult:
        require(self.granted, Level.PAY, "оплата заказа")
        if expected_total > max_total:
            raise PermissionDenied(f"Сумма {expected_total:.2f} ₪ выше вашего лимита {max_total:.2f} ₪")
        return await self._checkout(expected_total)

    async def _add_to_cart(self, lines: list[dict]) -> CartResult:
        raise NotImplementedError("сбор корзины для этого поставщика ещё не реализован")

    async def _checkout(self, expected_total: float) -> CheckoutResult:
        raise NotImplementedError("оформление заказа для этого поставщика ещё не реализовано")

    async def close(self) -> None:  # закрыть браузер
        return None


SCRAPERS: dict[str, type[SupplierScraper]] = {}  # key -> класс, регистрировать по мере добавления
