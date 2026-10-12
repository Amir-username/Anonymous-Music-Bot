from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.error()
async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    exception = event.exception

    # Someone blocked the bot - we can neither deliver nor notify. Just log quietly.
    if isinstance(exception, TelegramForbiddenError):
        logger.info("Delivery failed (blocked by user): %s", exception)
        return True

    logger.exception("Unhandled error while processing update", exc_info=exception)

    # Tell the sender something went wrong, if we still can reach them
    update = event.event
    chat_id = update.message.chat.id if update.message else None
    if chat_id:
        try:
            await bot.send_message(chat_id, "Something went wrong. Try again later.")
        except TelegramBadRequest:
            pass  # chat became unavailable mid-error - nothing more we can do

    return True  # mark the error as handled