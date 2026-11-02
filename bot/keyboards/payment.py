from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.config import settings


def pay_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"⭐ Оплатить {settings.subscription_price_stars} Stars", callback_data="pay:stars")
    return kb.as_markup()
