from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.subscription import SubscriptionMiddleware
from bot.states.contact import ContactFlow
from core.database import SupplierContact
from services import messenger
from services.scrapers.registry import SUPPLIERS, title_of
import services.scrapers  # noqa: F401

router = Router()
router.message.middleware(SubscriptionMiddleware())


@router.message(Command("contact"))
async def cmd_contact(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for s in SUPPLIERS.values():
        kb.button(text=s.title, callback_data=f"cont:{s.key}")
    kb.adjust(1)
    await message.answer("Для какого поставщика указать контакт менеджера (куда слать заказы)?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("cont:"))
async def pick(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    if key not in SUPPLIERS:
        await call.answer("Неизвестный поставщик", show_alert=True)
        return
    await state.set_state(ContactFlow.value)
    await state.update_data(supplier=key)
    await call.answer()
    await call.message.answer(f"{title_of(key)}\nПришлите номер WhatsApp менеджера (например 0501234567) или email:")


@router.message(ContactFlow.value, F.text)
async def got_value(message: Message, state: FSMContext, session: AsyncSession):
    raw = message.text.strip()
    phone = None if "@" in raw else messenger.normalize_phone(raw)
    email = raw if "@" in raw and "." in raw.split("@")[-1] else None
    if not phone and not email:
        await message.answer("Не похоже на номер или email. Попробуйте ещё раз.")
        return
    key = (await state.get_data())["supplier"]
    row = await session.scalar(
        select(SupplierContact).where(
            SupplierContact.telegram_id == message.from_user.id, SupplierContact.supplier == key
        )
    )
    if row is None:
        row = SupplierContact(telegram_id=message.from_user.id, supplier=key)
        session.add(row)
    if phone:
        row.whatsapp = phone
    if email:
        row.email = email
    await state.clear()
    await message.answer(f"✅ Контакт для {title_of(key)} сохранён.")
