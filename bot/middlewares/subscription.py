from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.keyboards.payment import pay_keyboard
from core.database import get_or_create_user


class SubscriptionMiddleware(BaseMiddleware):
    """Пропускает дальше, только если активен триал ИЛИ подписка."""

    async def __call__(self, handler, event: Message, data):
        session = data["session"]
        tg = event.from_user
        user = await get_or_create_user(session, tg.id, tg.username)
        if not user.has_access():
            await event.answer(
                "⏳ Бесплатный период закончился. Чтобы продолжить закупки, оформите подписку "
                "на 30 дней.",
                reply_markup=pay_keyboard(),
            )
            return None
        data["db_user"] = user
        return await handler(event, data)
