from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Config
from database.db import Database

router = Router(name="owner")


@router.message(Command("link"))
async def cmd_link(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id != config.owner_id:
        await message.answer("⛔ This command is only for the bot owner.")
        return

    owner = await db.ensure_owner(config.owner_id)
    me = await message.bot.me()
    await message.answer(
        "🔗 <b>Your anonymous inbox link:</b>\n\n"
        f"https://t.me/{me.username}?start={owner.link_code}\n\n"
        "Share this link — anyone who opens it can send you music anonymously."
    )
