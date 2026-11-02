from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database import Base, get_or_create_user, utcnow
from core.subscriptions import activate_subscription


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


async def test_trial_then_subscription_and_idempotency(session):
    u = await get_or_create_user(session, 1, "x")
    assert u.trial_active and u.has_access()
    u.trial_expires_at = utcnow() - timedelta(days=1)
    assert not u.has_access()

    assert await activate_subscription(session, u, "stars", "ch1", 500, "XTR") is True
    assert u.subscription_active and u.has_access()
    first = u.subscription_expires_at
    assert await activate_subscription(session, u, "stars", "ch1", 500, "XTR") is False  # дубль
    assert u.subscription_expires_at == first
