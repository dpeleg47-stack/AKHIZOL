"""Платёжные шлюзы. Логика подписки (core/subscriptions.py) от шлюза не зависит —
чтобы добавить Tranzila/Meshulam, достаточно реализовать PaymentGateway и
зарегистрировать его в GATEWAYS."""
from abc import ABC, abstractmethod

from aiogram import Bot
from aiogram.types import LabeledPrice

from core.config import settings

SUBSCRIPTION_PAYLOAD = "sub_30d"


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    async def create_checkout(self, bot: Bot, chat_id: int, user_id: int) -> None:
        """Показать пользователю платёжную форму/ссылку."""


class TelegramStarsGateway(PaymentGateway):
    name = "stars"

    async def create_checkout(self, bot: Bot, chat_id: int, user_id: int) -> None:
        await bot.send_invoice(
            chat_id=chat_id,
            title="B2B Procurement Bot — 30 дней",
            description=f"Подписка на {settings.subscription_days} дней: сравнение цен и автозакупка.",
            payload=SUBSCRIPTION_PAYLOAD,
            provider_token="",  # для Stars всегда пустой
            currency="XTR",
            prices=[LabeledPrice(label="Подписка 30 дней", amount=settings.subscription_price_stars)],
        )


class TranzilaGateway(PaymentGateway):
    """Заглушка под израильский эквайринг (Tranzila / Meshulam).
    Реализовать: создание платёжной ссылки + webhook, который вызывает
    core.subscriptions.activate_subscription(provider='tranzila', ...)."""

    name = "tranzila"

    async def create_checkout(self, bot: Bot, chat_id: int, user_id: int) -> None:
        raise NotImplementedError("Tranzila ещё не подключена")


GATEWAYS: dict[str, PaymentGateway] = {
    "stars": TelegramStarsGateway(),
    # "tranzila": TranzilaGateway(),
}
