from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AuditLog, Consent, SupplierCredential, utcnow
from core.permissions import Level


async def audit(session: AsyncSession, uid: int, supplier: str | None, action: str, detail: str = "") -> None:
    session.add(AuditLog(telegram_id=uid, supplier=supplier, action=action, detail=detail[:255]))


async def get_consent(session: AsyncSession, uid: int, supplier: str) -> Consent | None:
    return await session.scalar(
        select(Consent).where(Consent.telegram_id == uid, Consent.supplier == supplier)
    )


async def get_level(session: AsyncSession, uid: int, supplier: str) -> Level:
    c = await get_consent(session, uid, supplier)
    return Level(c.level) if c else Level.NONE


async def levels_for(session: AsyncSession, uid: int) -> dict[str, Level]:
    rows = (await session.scalars(select(Consent).where(Consent.telegram_id == uid))).all()
    return {r.supplier: Level(r.level) for r in rows}


async def set_level(
    session: AsyncSession, uid: int, supplier: str, level: Level, order_limit: float | None = None
) -> None:
    c = await get_consent(session, uid, supplier)
    if c is None:
        c = Consent(telegram_id=uid, supplier=supplier, level=int(level))
        session.add(c)
    c.level = int(level)
    c.updated_at = utcnow()
    c.order_limit = order_limit if level >= Level.PAY else None
    await audit(session, uid, supplier, "consent", f"level={level.name} limit={c.order_limit}")


async def revoke_supplier(session: AsyncSession, uid: int, supplier: str) -> None:
    await session.execute(
        delete(SupplierCredential).where(SupplierCredential.telegram_id == uid, SupplierCredential.supplier == supplier)
    )
    await session.execute(delete(Consent).where(Consent.telegram_id == uid, Consent.supplier == supplier))
    await audit(session, uid, supplier, "revoke")


async def revoke_all(session: AsyncSession, uid: int) -> None:
    await session.execute(delete(SupplierCredential).where(SupplierCredential.telegram_id == uid))
    await session.execute(delete(Consent).where(Consent.telegram_id == uid))
    await audit(session, uid, None, "revoke_all")
