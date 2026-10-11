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
    captions = "allowed ✅" if settings.captions_allowed else "disabled 🚫"
    return (
        "🎧 <b>Your anonymous music inbox</b>\n\n"
        f"🔗 <b>Your link:</b> https://t.me/{me.username}?start={owner.link_code}\n"
        f"✍️ <b>Captions:</b> {captions}\n\n"
        "<b>Commands</b>\n"
        "/link — show your inbox link\n"
        "/captions on | /captions off — allow or reject captions\n"
        "/limit N — daily song limit per listener (or /limit off)\n"
        "/ban #ID — ban a sender\n"
        "/unban #ID — unban a sender\n"
        "/bans — list banned senders\n"
        "/status — settings and statistics\n"
        "/help — show this panel"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    payload = (command.args or "").strip()

    # 1) Deep link → connect the user to an owner (3.1)
    if payload:
        owner = await db.get_owner_by_link_code(payload)
        if owner is None:
            await message.answer("🔗 This link is invalid. Ask the owner for a fresh one.")
            return

        anonymous_id = await db.get_or_create_user(message.from_user.id, owner.owner_id)
        await db.set_session(message.from_user.id, owner.owner_id)

        settings = await db.get_settings(owner.owner_id)
        limit_note = (
            f"\n📊 Limit: <b>{settings.daily_limit} songs per day</b>."
            if settings.daily_limit > 0
            else ""
        )
        await message.answer(
            "🎧 <b>You're in!</b>\n\n"
            f"Your anonymous ID: <b>{anonymous_id}</b>\n\n"
            "Now just send an audio file or voice message — "
            "the owner will receive it without ever knowing who you are.\n"
            "⚠️ Music files only — text is not delivered."
            f"{limit_note}"
        )
        return

    # 2) Owner's own /start → their control panel
    if message.from_user.id == config.owner_id:
        await message.answer(await _owner_panel(message, db, config))
        return

    # 3) Everyone else → generic welcome
    await message.answer(
        "👋 Welcome!\n\n"
        "This bot lets you send music <b>anonymously</b>.\n"
        "Use the personal link you were given to get started."
    )


@router.message(Command("help"))
async def cmd_help(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id == config.owner_id:
        await message.answer(await _owner_panel(message, db, config))
        return
    await message.answer(
        "🎧 <b>How this works</b>\n\n"
        "1. Open the personal link the owner gave you.\n"
        "2. Send an audio file or voice message.\n"
        "3. Done — they receive it with your anonymous ID, never your name.\n\n"
        "Accepted: audio files, voice messages, audio documents."
    )