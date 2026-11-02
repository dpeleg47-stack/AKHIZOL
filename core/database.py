from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    trial_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @staticmethod
    def _aware(dt: datetime | None) -> datetime | None:
        # SQLite возвращает naive datetime — приводим к UTC
        if dt is not None and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @property
    def subscription_active(self) -> bool:
        exp = self._aware(self.subscription_expires_at)
        return exp is not None and exp > utcnow()

    @property
    def trial_active(self) -> bool:
        return self._aware(self.trial_expires_at) > utcnow()

    def has_access(self) -> bool:
        return self.trial_active or self.subscription_active


class Payment(Base):
    """Журнал платежей. provider = 'stars' | 'tranzila' | 'meshulam' ..."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_provider_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(255))  # charge id (защита от дублей)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None) -> User:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            trial_expires_at=utcnow() + timedelta(days=settings.trial_days),
        )
        session.add(user)
        await session.flush()
    return user


class SupplierCredential(Base):
    """Логин/пароль пользователя от кабинета поставщика (хранятся только зашифрованными)."""

    __tablename__ = "supplier_credentials"
    __table_args__ = (UniqueConstraint("telegram_id", "supplier", name="uq_user_supplier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier: Mapped[str] = mapped_column(String(64))
    login_enc: Mapped[str] = mapped_column(String(512))
    password_enc: Mapped[str] = mapped_column(String(512))


class SupplierContact(Base):
    """Куда отправлять заказ, если поставщик принимает его через менеджера."""

    __tablename__ = "supplier_contacts"
    __table_args__ = (UniqueConstraint("telegram_id", "supplier", name="uq_contact_user_supplier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier: Mapped[str] = mapped_column(String(64))
    whatsapp: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 9725XXXXXXXX
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Order(Base):
    """История заказов."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))  # whatsapp | email
    total: Mapped[float] = mapped_column(Float)
    items_json: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Consent(Base):
    """Выданное пользователем разрешение для конкретного поставщика (см. core.permissions.Level)."""

    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("telegram_id", "supplier", name="uq_consent_user_supplier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(Integer, default=1)
    order_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # макс. сумма одного заказа (₪) для PAY
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Журнал значимых действий: кто что разрешил/отозвал и что бот делал в кабинетах."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    supplier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

