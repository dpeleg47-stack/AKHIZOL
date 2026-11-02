from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.orders import run_cart
from core.consents import levels_for, revoke_all, revoke_supplier, set_level
from core.permissions import DESCRIPTIONS, TITLES, Level
from services.compare import connected_suppliers
from services.scrapers.registry import title_of

# Управление доступом доступно всегда — без проверки триала/подписки.
router = Router()

ICON = {Level.NONE: "▫️", Level.PRICES: "👁", Level.CART: "🧺", Level.PAY: "💳"}
LIMITS = [1000, 3000, 10000]


def _lvl(levels: dict, key: str) -> Level:
    return max(levels.get(key, Level.NONE), Level.PRICES)


async def _valid(session: AsyncSession, uid: int, key: str) -> bool:
    return key in await connected_suppliers(session, uid)


@router.message(Command("access", "suppliers"))
async def cmd_access(message: Message, session: AsyncSession):
    uid = message.from_user.id
    keys = await connected_suppliers(session, uid)
    if not keys:
        await message.answer(
            "🔐 Пока ни один кабинет не подключён, поэтому сравнивать цены мне не у кого.\n\n"
            "/connect — подключить кабинет поставщика. Доступ будет только на чтение цен: "
            "корзину и оплату я смогу делать, только если вы разрешите отдельно."
        )
        return
    levels = await levels_for(session, uid)
    kb = InlineKeyboardBuilder()
    for k in keys:
        kb.button(text=f"{ICON[_lvl(levels, k)]} {title_of(k)}", callback_data=f"acc:{k}")
    kb.adjust(1)
    await message.answer(
        "🔐 Что я могу делать в ваших кабинетах (нажмите на поставщика, чтобы изменить):\n"
        "👁 только цены · 🧺 корзина · 💳 оплата\n\nПо умолчанию — только чтение цен.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("acc:"))
async def cb_menu(call: CallbackQuery, session: AsyncSession):
    uid, key = call.from_user.id, call.data.split(":", 1)[1]
    if not await _valid(session, uid, key):
        await call.answer("Поставщик не подключён", show_alert=True)
        return
    lvl = _lvl(await levels_for(session, uid), key)
    kb = InlineKeyboardBuilder()
    if lvl < Level.CART:
        kb.button(text="🧺 Разрешить корзину", callback_data=f"accup:{key}:2")
    if lvl < Level.PAY:
        kb.button(text="💳 Разрешить оплату", callback_data=f"accup:{key}:3")
    if lvl > Level.PRICES:
        kb.button(text="🔒 Вернуть «только цены»", callback_data=f"accdn:{key}")
    kb.button(text="🗑 Удалить доступ", callback_data=f"accdel:{key}")
    kb.adjust(1)
    await call.answer()
    await call.message.answer(
        f"{title_of(key)}\nСейчас: {TITLES[lvl]}\n\n{DESCRIPTIONS[lvl]}", reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("accup:"))
async def cb_up(call: CallbackQuery, session: AsyncSession):
    _, key, raw = call.data.split(":")
    if raw not in ("2", "3") or not await _valid(session, call.from_user.id, key):
        await call.answer("Недоступно", show_alert=True)
        return
    lvl = Level(int(raw))
    kb = InlineKeyboardBuilder()
    if lvl == Level.CART:
        kb.button(text="✅ Разрешаю", callback_data=f"accok:{key}:2")
        text = DESCRIPTIONS[Level.CART]
    else:
        for lim in LIMITS:
            kb.button(text=f"✅ Разрешаю, лимит {lim} ₪ на заказ", callback_data=f"accok:{key}:3:{lim}")
        text = DESCRIPTIONS[Level.PAY] + "\n\nВыберите максимальную сумму одного заказа:"
    kb.button(text="Отмена", callback_data=f"acc:{key}")
    kb.adjust(1)
    await call.answer()
    await call.message.answer(f"{title_of(key)}\n\n{text}", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("accok:"))
async def cb_ok(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = call.data.split(":")
    try:
        key, lvl = parts[1], Level(int(parts[2]))
        limit = float(parts[3]) if len(parts) > 3 else None
    except (ValueError, IndexError):
        await call.answer("Ошибка", show_alert=True)
        return
    ok_pay = lvl == Level.PAY and limit in [float(x) for x in LIMITS]
    if lvl not in (Level.CART, Level.PAY) or (lvl == Level.PAY and not ok_pay) \
            or not await _valid(session, call.from_user.id, key):
        await call.answer("Недоступно", show_alert=True)
        return
    await set_level(session, call.from_user.id, key, lvl, limit)
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    extra = f" (лимит {limit:.0f} ₪ на заказ)" if limit else ""
    await call.message.answer(f"✅ {title_of(key)}: разрешено «{TITLES[lvl]}»{extra}. Отозвать можно в любой момент: /access")
    # Если пользователь только что сказал «добавь в корзину» — продолжаем с того места, где остановились
    kind = (await state.get_data()).get("pending_cart")
    if kind and lvl >= Level.CART:
        await run_cart(call.message, call.from_user.id, state, session, kind)


@router.callback_query(F.data.startswith("accdn:"))
async def cb_down(call: CallbackQuery, session: AsyncSession):
    key = call.data.split(":", 1)[1]
    if not await _valid(session, call.from_user.id, key):
        await call.answer("Недоступно", show_alert=True)
        return
    await set_level(session, call.from_user.id, key, Level.PRICES)
    await call.answer()
    await call.message.answer(f"🔒 {title_of(key)}: снова только просмотр цен.")


@router.callback_query(F.data.startswith("accdel:"))
async def cb_del(call: CallbackQuery, session: AsyncSession):
    key = call.data.split(":", 1)[1]
    await revoke_supplier(session, call.from_user.id, key)
    await call.answer()
    await call.message.answer(f"🗑 Доступ к {title_of(key)} удалён: логин, пароль и разрешения стёрты.")


@router.message(Command("disconnect"))
async def cmd_disconnect(message: Message, session: AsyncSession):
    await revoke_all(session, message.from_user.id)
    await message.answer("🗑 Все сохранённые логины, пароли и разрешения удалены.")
