from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import Config
from database.db import Database

router = Router(name="owner")

# Matches the alphabet in anonymous_id.py (no 0/O, no 1/I)
ANON_ID_RE = re.compile(r"^#[A-HJ-NP-Z2-9]{6}$")


async def _ensure_owner(message: Message, config: Config) -> bool:
    if message.from_user.id != config.owner_id:
        await message.answer("⛔ This command is only for the bot owner.")
        return False
    return True


@router.message(Command("link"))
async def cmd_link(message: Message, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return
    owner = await db.ensure_owner(config.owner_id)
    me = await message.bot.me()
    await message.answer(
        "🔗 <b>Your anonymous inbox link:</b>\n\n"
        f"https://t.me/{me.username}?start={owner.link_code}\n\n"
        "Share this link — anyone who opens it can send you music anonymously."
    )


@router.message(Command("captions"))
async def cmd_captions(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    arg = (command.args or "").strip().lower()
    if arg == "on":
        await db.set_captions_allowed(config.owner_id, True)
        await message.answer("✅ Captions <b>allowed</b> — music may include a text caption.")
    elif arg == "off":
        await db.set_captions_allowed(config.owner_id, False)
        await message.answer("✅ Captions <b>disabled</b> — music with a caption will be rejected.")
    else:
        settings = await db.get_settings(config.owner_id)
        state = "allowed" if settings.captions_allowed else "disabled"
        await message.answer(
            f"Captions are currently <b>{state}</b>.\n"
            "Usage: <code>/captions on</code> or <code>/captions off</code>"
        )


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    arg = (command.args or "").strip().upper()
    if not ANON_ID_RE.match(arg):
        await message.answer("Usage: <code>/ban #A7K9P2</code>")
        return
    if await db.get_user_by_anonymous_id(config.owner_id, arg) is None:
        await message.answer(f"Unknown ID {arg} — it must belong to someone who contacted you before.")
        return

    if await db.ban_user(config.owner_id, arg):
        await message.answer(f"🚫 {arg} is now banned.")
    else:
        await message.answer(f"{arg} was already banned.")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    arg = (command.args or "").strip().upper()
    if not ANON_ID_RE.match(arg):
        await message.answer("Usage: <code>/unban #A7K9P2</code>")
        return

    if await db.unban_user(config.owner_id, arg):
        await message.answer(f"✅ {arg} was unbanned and can send music again.")
    else:
        await message.answer(f"{arg} wasn't banned.")


@router.message(Command("bans"))
async def cmd_bans(message: Message, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    bans = await db.list_bans(config.owner_id)
    if not bans:
        await message.answer("Nobody is banned. 🎉")
    else:
        await message.answer("🚫 <b>Banned users:</b>\n" + "\n".join(bans))
