import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.subscription import SubscriptionMiddleware
from bot.states.connect import ConnectFlow
from core import crypto
from core.consents import audit, get_level, set_level
from core.database import SupplierCredential
from core.permissions import DESCRIPTIONS, Level
from services.scrapers.registry import SUPPLIERS

log = logging.getLogger(__name__)
router = Router()
router.message.middleware(SubscriptionMiddleware())


@router.message(Command("connect"))
async def cmd_connect(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    for s in (x for x in SUPPLIERS.values() if not x.hidden):
        kb.button(text=s.title, callback_data=f"conn:{s.key}")
    kb.adjust(1)
    await message.answer(
        "Выберите поставщика. Доступ будет только на чтение цен — расширять права или нет, решаете вы позже (/access).",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("conn:"))
async def pick_supplier(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    if key not in SUPPLIERS:
        await call.answer("Неизвестный поставщик", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Согласен: только просмотр цен", callback_data=f"connok:{key}")
    kb.button(text="Отмена", callback_data="connno")
    kb.adjust(1)
    await call.answer()
    await call.message.answer(
        f"{SUPPLIERS[key].title}\n\n{DESCRIPTIONS[Level.PRICES]}\n\n"
        "Логин и пароль хранятся в зашифрованном виде. Отозвать доступ можно в любой момент: /access.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "connno")
async def cancel(call: CallbackQuery):
    await call.answer("Отменено")
    await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("connok:"))
async def consent_ok(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    if key not in SUPPLIERS:
        await call.answer("Неизвестный поставщик", show_alert=True)
        return
    await state.set_state(ConnectFlow.login)
    await state.update_data(supplier=key)
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer("Введите логин (телефон или email), который вы используете для входа в кабинет:")


@router.message(ConnectFlow.login, F.text)
async def got_login(message: Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await state.set_state(ConnectFlow.password)
    await message.answer(
        "Теперь пароль. Я сразу удалю ваше сообщение с паролем из чата и сохраню его только в зашифрованном виде."
    )


@router.message(ConnectFlow.password, F.text)
async def got_password(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    password = message.text
    try:
        await message.delete()  # убираем пароль из истории чата
    except Exception:
        log.warning("не удалось удалить сообщение с паролем")
    try:
        login_enc, pwd_enc = crypto.encrypt(data["login"]), crypto.encrypt(password)
    except Exception:
        log.exception("encrypt failed")
        await message.answer("⚠️ Хранилище паролей не настроено (SECRET_KEY). Данные не сохранены.")
        await state.clear()
        return
    uid, key = message.from_user.id, data["supplier"]
    row = await session.scalar(
        select(SupplierCredential).where(SupplierCredential.telegram_id == uid, SupplierCredential.supplier == key)
    )
    if row:
        row.login_enc, row.password_enc = login_enc, pwd_enc
    else:
        session.add(SupplierCredential(telegram_id=uid, supplier=key, login_enc=login_enc, password_enc=pwd_enc))
    if await get_level(session, uid, key) < Level.PRICES:
        await set_level(session, uid, key, Level.PRICES)  # фиксируем согласие «только чтение»
    await audit(session, uid, key, "connect")
    await state.clear()
    await message.answer(
        f"✅ {SUPPLIERS[key].title} подключён в режиме «только цены». Пароль удалён из чата."
    )
