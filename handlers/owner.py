from __future__ import annotations

import html
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message, ReplyParameters

from config import Config
from database.db import Database
from utils.replies import ReplyRegistry

router = Router(name="owner")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# Matches the alphabet in anonymous_id.py (no 0/O, no 1/I)
ANON_ID_RE = re.compile(r"^#[A-HJ-NP-Z2-9]{6}$")
LIMIT_MAX = 100
MAX_FILE_MAX = 2000  # MB; Telegram itself allows up to 2 GB


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


@router.message(Command("limit"))
async def cmd_limit(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    arg = (command.args or "").strip().lower()
    settings = await db.get_settings(config.owner_id)

    if not arg:
        current = (
            f"<b>{settings.daily_limit} songs every 24 hours</b>"
            if settings.daily_limit > 0
            else "<b>unlimited</b>"
        )
        await message.answer(
            f"📊 Song limit: {current}.\n"
            "Usage: <code>/limit 10</code> (1–100) or <code>/limit off</code>"
        )
        return

    if arg in ("off", "unlimited"):
        await db.set_daily_limit(config.owner_id, 0)
        await message.answer("✅ Limit removed — your inbox now accepts unlimited songs.")
        return

    if not arg.isdigit() or int(arg) > LIMIT_MAX or int(arg) < 1:
        await message.answer(
            f"⚠️ Give me a number from 1 to {LIMIT_MAX}, or <code>off</code>.\n"
            "Example: <code>/limit 3</code>"
        )
        return

    await db.set_daily_limit(config.owner_id, int(arg))
    await message.answer(
        f"📊 Done — your inbox now accepts <b>{arg} song(s) every 24 hours</b> from each listener."
    )


@router.message(Command("maxsize"))
async def cmd_maxsize(message: Message, command: CommandObject, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return

    arg = (command.args or "").strip().lower()
    settings = await db.get_settings(config.owner_id)

    if not arg:
        current = (
            f"<b>{settings.max_file_mb} MB</b>"
            if settings.max_file_mb > 0
            else "<b>unlimited</b>"
        )
        await message.answer(
            f"📦 Max file size: {current}.\n"
            f"Usage: <code>/maxsize 50</code> (1–{MAX_FILE_MAX} MB) or <code>/maxsize off</code>"
        )
        return

    if arg in ("off", "unlimited"):
        await db.set_max_file_size(config.owner_id, 0)
        await message.answer("✅ Size limit removed — Telegram's own limits apply (up to 2 GB).")
        return

    if not arg.isdigit() or int(arg) > MAX_FILE_MAX or int(arg) < 1:
        await message.answer(
            f"⚠️ Give me a number from 1 to {MAX_FILE_MAX} (MB), or <code>off</code>.\n"
            "Example: <code>/maxsize 50</code>"
        )
        return

    await db.set_max_file_size(config.owner_id, int(arg))
    await message.answer(f"📦 Done — tracks bigger than <b>{arg} MB</b> will be rejected.")


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


@router.message(Command("status"))
async def cmd_status(message: Message, db: Database, config: Config) -> None:
    if not await _ensure_owner(message, config):
        return
    stats = await db.get_stats(config.owner_id)
    settings = await db.get_settings(config.owner_id)
    limit = f"{settings.daily_limit} songs / 24h" if settings.daily_limit > 0 else "unlimited"
    size = f"{settings.max_file_mb} MB" if settings.max_file_mb > 0 else "unlimited"
    await message.answer(
        "📊 <b>Status</b>\n\n"
        f"✍️ Captions: {'allowed ✅' if settings.captions_allowed else 'disabled 🚫'}\n"
        f"🎵 Song limit: {limit}\n"
        f"📦 Max file size: {size}\n"
        f"👥 Anonymous listeners: <b>{stats.users}</b>\n"
        f"🎧 Tracks delivered: <b>{stats.tracks}</b> (<b>{stats.tracks_today}</b> today)\n"
        f"💬 Replies sent: <b>{stats.replies}</b>\n"
        f"🚫 Banned: <b>{stats.bans}</b>"
    )


# ---------- anonymous replies ----------

def _is_delivery_message(m: Message) -> bool:
    """The delivered audio itself, or its '🎧 #ID' caption header."""
    if m.audio:
        return True
    return (m.text or m.caption or "").startswith("🎧")


class OwnerReplyToDelivery(Filter):
    """Matches messages the owner sent as a reply to a delivered track."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        target = message.reply_to_message
        if not (target and target.from_user and target.from_user.id == bot.id):
            return False
        return _is_delivery_message(target)


@router.message(OwnerReplyToDelivery())
async def handle_owner_reply(
    message: Message, bot: Bot, db: Database, replies: ReplyRegistry
) -> None:
    rec = replies.lookup(message.from_user.id, message.reply_to_message.message_id)
    if rec is None:
        await message.answer(
            "⚠️ I can't route replies to this one — I was restarted after it arrived. "
            "The sender's mapping is kept in memory only, for privacy."
        )
        return

    note = "💬 <b>Reply about your track:</b>"
    reply_params = ReplyParameters(
        message_id=rec.sender_message_id, allow_sending_without_reply=True
    )
    try:
        if message.text:
            await bot.send_message(
                rec.sender_telegram_id,
                f"{note}\n\n{html.escape(message.text)}",
                reply_parameters=reply_params,
            )
        elif message.voice:
            await bot.send_message(
                rec.sender_telegram_id, note, reply_parameters=reply_params
            )
            await bot.copy_message(rec.sender_telegram_id, message.chat.id, message.message_id)
        elif message.audio or (
            message.document
            and message.document.mime_type
            and message.document.mime_type.startswith("audio/")
        ):
            await bot.copy_message(
                rec.sender_telegram_id,
                message.chat.id,
                message.message_id,
                caption=note,
            )
        else:
            await message.answer("⚠️ I can deliver text, voice, or audio as a reply — nothing else.")
            return
    except TelegramForbiddenError:
        await message.answer("⚠️ Couldn't deliver — this listener has blocked the bot.")
        return

    await db.log_message(message.from_user.id, rec.anonymous_id, kind="reply")
    await message.answer(f"✅ Delivered to {rec.anonymous_id}.")
