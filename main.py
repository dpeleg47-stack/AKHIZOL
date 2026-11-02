import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.handlers import access, connect, contact, orders, payments, procurement, start
from bot.middlewares.db import DbSessionMiddleware
from core.config import settings
from core.database import init_db

logging.basicConfig(level=logging.INFO)

WEBHOOK_PATH = "/webhook"


def build_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url) if settings.redis_url else MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(DbSessionMiddleware())
    # Порядок важен: открытые роутеры (старт/оплата) раньше платного
    dp.include_routers(start.router, payments.router, access.router, connect.router, contact.router, orders.router, procurement.router)
    return dp


async def run_polling(bot: Bot, dp: Dispatcher):
    await bot.delete_webhook()
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def run_webhook(bot: Bot, dp: Dispatcher):
    async def on_startup() -> None:  # aiogram передаёт данные по именам, поэтому без позиционных аргументов
        await bot.set_webhook(
            f"{settings.base_url}{WEBHOOK_PATH}",
            secret_token=settings.webhook_secret,
            allowed_updates=dp.resolve_used_update_types(),
        )

    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="ok"))  # health check для Render
    SimpleRequestHandler(dp, bot, secret_token=settings.webhook_secret).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=settings.port)


def main():
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан")
    asyncio.run(init_db())
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = build_dispatcher()
    if settings.base_url:
        run_webhook(bot, dp)
    else:
        asyncio.run(run_polling(bot, dp))


if __name__ == "__main__":
    main()
