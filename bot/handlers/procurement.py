import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.orders import KIND_LABEL, run_cart, run_compare
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.states.order import OrderFlow
from core import ai_parser, stt
from services.intents import is_cart_intent
from services.optimizer import best_kind

log = logging.getLogger(__name__)
router = Router()
# Всё, что в этом роутере, доступно только при активном триале/подписке
router.message.middleware(SubscriptionMiddleware())


def _format(items: list[dict]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        parts = [it.get("name") or "?", it.get("brand"), it.get("size")]
        label = " · ".join(p for p in parts if p)
        lines.append(f"{i}. {label} — {it.get('quantity', 1)} {it.get('unit') or 'шт'}")
    return "\n".join(lines)


async def _process_list(message: Message, state: FSMContext, session: AsyncSession, items: list[dict]):
    """Распознали список → сразу сами собираем цены у поставщиков и сравниваем."""
    if not items:
        await message.answer("Не нашёл товаров в сообщении. Попробуйте переформулировать.")
        return
    await state.set_state(OrderFlow.confirming)
    await state.update_data(items=items, plans=None, drafts={}, carts={}, pending_cart=None)
    await message.answer(f"📋 Распознал список:\n\n{_format(items)}")
    await run_compare(message, message.from_user.id, state, session)


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext, session: AsyncSession):
    if is_cart_intent(message.text):
        kind = best_kind((await state.get_data()).get("plans"))
        if kind is None:
            await message.answer("Сначала пришлите список товаров: я сравню цены у ваших поставщиков, а потом скажете «добавь в корзину».")
            return
        await message.answer(f"Беру вариант {KIND_LABEL[kind]} — он лучший по цене.")
        await run_cart(message, message.from_user.id, state, session, kind)
        return
    try:
        items = await ai_parser.parse_text(message.text)
    except Exception:
        log.exception("parse_text failed")
        await message.answer("⚠️ Не удалось разобрать список, попробуйте ещё раз.")
        return
    await _process_list(message, state, session, items)


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        buf = await bot.download_file(file.file_path)
        items = await ai_parser.parse_image(buf.read())
    except Exception:
        log.exception("parse_image failed")
        await message.answer("⚠️ Не удалось распознать фото.")
        return
    await _process_list(message, state, session, items)


@router.message(F.voice)
async def on_voice(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    try:
        file = await bot.get_file(message.voice.file_id)
        buf = await bot.download_file(file.file_path)
        text = await stt.transcribe(buf.read())
        await message.answer(f"🎙 Распознал: {text}")
        if is_cart_intent(text):  # «добавь в корзину» можно сказать голосом
            kind = best_kind((await state.get_data()).get("plans"))
            if kind:
                await run_cart(message, message.from_user.id, state, session, kind)
                return
        items = await ai_parser.parse_text(text)
    except Exception:
        log.exception("voice failed")
        await message.answer("⚠️ Не удалось обработать голосовое.")
        return
    await _process_list(message, state, session, items)
