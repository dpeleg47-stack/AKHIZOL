from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.payment import pay_keyboard
from core.config import settings
from core.database import get_or_create_user

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    await message.answer(
        f"👋 Привет! Я помогу сравнить оптовые цены и собрать закупку.\n\n"
        f"🎁 У вас {settings.trial_days} дней бесплатного доступа "
        f"(до {user.trial_expires_at:%d.%m.%Y}).\n\n"
        "Пришлите список товаров текстом, голосом или фото накладной — я сам соберу цены у ваших поставщиков и выберу лучший вариант. "
        "Потом скажите «добавь в корзину».\n\n"
        "🔒 Сначала я только смотрю цены и ничего не покупаю. "
        "Больше прав (корзина, оплата) я получу, только если вы сами разрешите — /access."
    )


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    if user.subscription_active:
        text = f"✅ Подписка активна до {user.subscription_expires_at:%d.%m.%Y}"
    elif user.trial_active:
        text = f"🎁 Триал активен до {user.trial_expires_at:%d.%m.%Y}"
    else:
        await message.answer("⛔ Доступ закончился.", reply_markup=pay_keyboard())
        return
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")
