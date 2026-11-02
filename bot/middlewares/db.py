from aiogram import BaseMiddleware

from core.database import SessionLocal


class DbSessionMiddleware(BaseMiddleware):
    """Открывает сессию БД на каждый апдейт и коммитит после обработчика."""

    async def __call__(self, handler, event, data):
        async with SessionLocal() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result
