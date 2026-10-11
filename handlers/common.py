from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from database.db import Database

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database) -> None:
    payload = (command.args or "").strip()

    if not payload:
        await message.answer(
            "👋 Welcome!\n\n"
            "This bot lets you send music <b>anonymously</b>.\n"
            "Use the personal link you were given to get started."
        )
        return

    owner = await db.get_owner_by_link_code(payload)
    if owner is None:
        await message.answer("🔗 This link is invalid. Ask the owner for a fresh one.")
        return

    anonymous_id = await db.get_or_create_user(message.from_user.id, owner.owner_id)
    await db.set_session(message.from_user.id, owner.owner_id)

    await message.answer(
        "🎧 <b>You're in!</b>\n\n"
        f"Your anonymous ID: <b>{anonymous_id}</b>\n\n"
        "Now just send an audio file or voice message — "
        "the owner will receive it without ever knowing who you are.\n\n"
        "⚠️ Music files only — text is not delivered."
    )
