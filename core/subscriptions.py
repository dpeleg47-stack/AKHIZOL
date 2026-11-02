from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import Payment, User, utcnow


async def activate_subscription(
    session: AsyncSession,
    user: User,
    provider: str,
    external_id: str,
    amount: int,
    currency: str,
) -> bool:
    """Продлевает подписку на 30 дней. Возвращает False, если платёж уже был обработан."""
    exists = await session.scalar(
        select(Payment.id).where(Payment.provider == provider, Payment.external_id == external_id)
    )
    if exists:
        return False

    session.add(
        Payment(
            telegram_id=user.telegram_id,
            provider=provider,
            external_id=external_id,
            amount=amount,
            currency=currency,
        )
    )
    # Если подписка ещё активна — продлеваем от её конца, а не от «сейчас»
    base = user.subscription_expires_at
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=utcnow().tzinfo)
    start = base if base and base > utcnow() else utcnow()
    user.subscription_expires_at = start + timedelta(days=settings.subscription_days)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return False
    return True
