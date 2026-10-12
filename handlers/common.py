from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from config import Config
from database.db import Database

router = Router(name="common")
router.message.filter(F.chat.type == ChatType.PRIVATE)


async def _owner_panel(message: Message, db: Database, config: Config) -> str:
    owner = await db.ensure_owner(config.owner_id)
    settings = await db.get_settings(config.owner_id)
    me = await message.bot.me()
    limit = f"{settings.daily_limit} / 24h" if settings.daily_limit > 0 else "off"
    size = f"{settings.max_file_mb} MB" if settings.max_file_mb > 0 else "off"
    return (
        "Your anonymous music inbox\n\n"
        f"Link: https://t.me/{me.username}?start={owner.link_code}\n"
        f"Captions: {'on' if settings.captions_allowed else 'off'}\n"
        f"Song limit: {limit}\n"
        f"Max file size: {size}\n\n"
        "/link - show your inbox link\n"
        "/captions - allow or reject captions\n"
        "/limit - song limit per listener (24h)\n"
        "/maxsize - max file size in MB\n"
        "/ban #ID - ban a sender\n"
        "/unban #ID - unban a sender\n"
        "/bans - list banned senders\n"
        "/status - settings and statistics\n"
        "/help - show this panel\n\n"
        "Reply to any track to answer its sender."
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    payload = (command.args or "").strip()

    # 1) Deep link -> connect the user to an owner
    if payload:
        owner = await db.get_owner_by_link_code(payload)
        if owner is None:
            await message.answer("Invalid link.")
            return

        await db.get_or_create_user(message.from_user.id, owner.owner_id)
        await db.set_session(message.from_user.id, owner.owner_id)

        settings = await db.get_settings(owner.owner_id)
        limit_note = (
            f"\nLimit: {settings.daily_limit} songs every 24 hours."
            if settings.daily_limit > 0
            else ""
        )
        # The anonymous ID is deliberately not shown to the user.
        await message.answer(
            "Connected.\n"
            "Send a music file (MP3, FLAC, OGG) - your identity stays hidden."
            f"{limit_note}"
        )
        return

    # 2) Owner's own /start -> control panel
    if message.from_user.id == config.owner_id:
        await message.answer(await _owner_panel(message, db, config))
        return

    # 3) Everyone else
    await message.answer(
        "This bot delivers music anonymously.\n"
        "Open the personal link you were given."
    )


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id == config.owner_id:
        await message.answer(await _owner_panel(message, db, config))
        return
    await message.answer(
        "Send a music file (MP3, FLAC, OGG).\n"
        "Voice messages and documents are not accepted."
    )