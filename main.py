import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import get_config
from database.db import Database
from handlers import common, errors, owner, user

async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    config = get_config()

    db = Database(config.db_path, config.hash_secret)
    await db.connect()
    await db.initialize()
    await db.ensure_owner(config.owner_id)  # bootstrap the primary owner

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_routers(errors.router, owner.router, common.router, user.router)
    dp["db"] = db        # injected into handlers that request `db`
    dp["config"] = config  # injected into handlers that request `config`

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
