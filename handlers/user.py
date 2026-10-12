from __future__ import annotations

import html
import math
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Message, ReplyParameters

from config import Config
from database.db import Database
from utils.filters import extract_audio
from utils.replies import ReplyRegistry

router = Router(name="user")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# The "daily" limit is a rolling 24h window anchored to each user's own sends.
# Temporarily set this to e.g. 0.05 (≈3 min) to test quota expiry quickly.
QUOTA_WINDOW_HOURS = 24


def _format_wait(oldest_iso: str | None) -> str:
    """Human-readable time until the oldest track in the window leaves it."""
    if oldest_iso:
        anchor = datetime.fromisoformat(oldest_iso)
    else:
        anchor = datetime.now(timezone.utc)  # the track we just sent
    seconds = (
        anchor + timedelta(hours=QUOTA_WINDOW_HOURS) - datetime.now(timezone.utc)
    ).total_seconds()
    if seconds <= 0:
        return "a few seconds"
    total_min = max(1, math.ceil(seconds / 60))
    h, m = divmod(total_min, 60)
    if h == 0:
        return f"{m} min"
    return f"{h}h {m:02d}m"


@router.message(F.audio | F.voice | F.document)
async def handle_music(
    message: Message, bot: Bot, db: Database, replies: ReplyRegistry
) -> None:
    # 1) Must be connected via a deep link
    owner_id = await db.get_session_owner(message.from_user.id)
    if owner_id is None:
        await message.answer(
            "👋 I deliver music anonymously to a specific person.\n"
            "Open their personal link first — then send your music here."
        )
        return

    anonymous_id = await db.get_or_create_user(message.from_user.id, owner_id)

    # 2) Ban check
    if await db.is_banned(owner_id, anonymous_id):
        await message.answer("🚫 You are banned from sending music to this owner.")
        return

    # 3) Owner's settings (quota + captions + size)
    settings = await db.get_settings(owner_id)

    # 4) Rolling 24h limit — tracks only, replies never consume the sender's quota
    limit = settings.daily_limit
    sent_recent = 0
    oldest = None
    if limit > 0:
        sent_recent, oldest = await db.get_track_quota(
            owner_id, anonymous_id, QUOTA_WINDOW_HOURS
        )
        if sent_recent >= limit:
            wait = _format_wait(oldest)
            await message.answer(
                "⏳ <b>Limit reached.</b>\n"
                f"You can send {limit} songs every 24 hours — "
                f"the next one unlocks in <b>{wait}</b>."
            )
            return

    # 5) Strict music-only filter
    media, _kind = extract_audio(message)
    if media is None:
        await message.answer(
            "🎵 I accept music only:\n"
            "• audio files\n"
            "• voice messages\n"
            "• documents with an audio file type"
        )
        return

    # 6) Owner-configured file size limit
    if settings.max_file_mb > 0 and media.file_size:
        if media.file_size > settings.max_file_mb * 1024 * 1024:
            await message.answer(
                "📦 This file is too big.\n"
                f"The owner accepts tracks up to <b>{settings.max_file_mb} MB</b>."
            )
            return

    # 7) Caption policy
    if not settings.captions_allowed and message.caption:
        await message.answer(
            "✍️🚫 The owner disabled captions.\n"
            "Resend the music file without any text attached."
        )
        return

    # 8) Deliver to the owner and remember the sender for anonymous replies
    prefix = f"🎧 <b>{anonymous_id}</b>"

    if message.voice:
        copied = await bot.copy_message(
            chat_id=owner_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        header = await bot.send_message(
            owner_id,
            prefix,
            reply_parameters=ReplyParameters(message_id=copied.message_id),
        )
        replies.record(owner_id, copied.message_id, anonymous_id,
                       message.from_user.id, message.message_id)
        replies.record(owner_id, header.message_id, anonymous_id,
                       message.from_user.id, message.message_id)
    else:
        original = message.caption or ""
        if settings.captions_allowed and original:
            escaped = html.escape(original)
            room = 1024 - len(prefix) - 1  # Telegram caption limit
            caption = f"{prefix}\n{escaped[:room]}"
        else:
            caption = prefix
        sent = await bot.copy_message(
            chat_id=owner_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            caption=caption,
        )
        replies.record(owner_id, sent.message_id, anonymous_id,
                       message.from_user.id, message.message_id)

    await db.log_message(owner_id, anonymous_id, kind="track")

    # 9) Friendly confirmation with remaining quota
    if limit > 0:
        remaining = limit - sent_recent - 1
        if remaining > 0:
            await message.answer(
                f"✅ Sent anonymously — {remaining} more in the next 24 hours."
            )
        else:
            wait = _format_wait(oldest)
            await message.answer(
                "✅ Sent anonymously — that was your last song for now. 🌙\n"
                f"The next one unlocks in <b>{wait}</b>."
            )
    else:
        await message.answer("✅ Sent anonymously.")


@router.message(F.text)
async def handle_text(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id == config.owner_id:
        await message.answer("🤖 That's your own inbox! Send /help to see your commands.")
        return
    if await db.get_session_owner(message.from_user.id) is None:
        await message.answer("👋 Open the owner's personal link first — then send music here.")
    else:
        await message.answer("🎵 Text isn't delivered. Send an audio file or voice message.")


@router.message()
async def handle_other(message: Message) -> None:
    await message.answer("🎵 I accept music only: audio files or voice messages.")
