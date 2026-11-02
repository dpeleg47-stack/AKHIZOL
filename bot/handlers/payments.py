from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_or_create_user
from core.payments import GATEWAYS, SUBSCRIPTION_PAYLOAD
from core.subscriptions import activate_subscription

router = Router()


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, bot: Bot):
    await GATEWAYS["stars"].create_checkout(bot, message.chat.id, message.from_user.id)


@router.callback_query(F.data == "pay:stars")
async def cb_pay_stars(call: CallbackQuery, bot: Bot):
    await call.answer()
    await GATEWAYS["stars"].create_checkout(bot, call.message.chat.id, call.from_user.id)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    ok = query.invoice_payload == SUBSCRIPTION_PAYLOAD
    await query.answer(ok=ok, error_message=None if ok else "Неизвестный товар")


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession):
    p = message.successful_payment
    user = await get_or_create_user(session, message.from_user.id, message.from_user.username)
    is_new = await activate_subscription(
        session,
        user,
        provider="stars",
        external_id=p.telegram_payment_charge_id,
        amount=p.total_amount,
        currency=p.currency,
    )
    if is_new:
        await message.answer(f"✅ Оплата получена. Подписка активна до {user.subscription_expires_at:%d.%m.%Y}.")
