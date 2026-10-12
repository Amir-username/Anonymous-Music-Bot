from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from config import Config
from database.db import Database
from utils.replies import ReplyRegistry

router = Router(name="user")
router.message.filter(F.chat.type == ChatType.PRIVATE)

# The "daily" limit is a rolling 24h window anchored to each user's own sends.
# Temporarily set this to e.g. 0.05 (about 3 min) to test quota expiry quickly.
QUOTA_WINDOW_HOURS = 24


def _format_wait(oldest_iso: str | None) -> str:
    """Human-readable time until the oldest track in the window leaves it."""
    if oldest_iso:
        anchor = datetime.fromisoformat(oldest_iso)
    else:
        anchor = datetime.now(timezone.utc)
    seconds = (
        anchor + timedelta(hours=QUOTA_WINDOW_HOURS) - datetime.now(timezone.utc)
    ).total_seconds()
    if seconds <= 0:
        return "moments"
    total_min = max(1, math.ceil(seconds / 60))
    h, m = divmod(total_min, 60)
    if h == 0:
        return f"{m} min"
    return f"{h}h {m:02d}m"


@router.message(F.audio)
async def handle_music(
    message: Message, bot: Bot, db: Database, replies: ReplyRegistry
) -> None:
    # 1) Must be connected via a deep link
    owner_id = await db.get_session_owner(message.from_user.id)
    if owner_id is None:
        await message.answer("Open the owner's personal link first.")
        return

    anonymous_id = await db.get_or_create_user(message.from_user.id, owner_id)

    # 2) Ban check
    if await db.is_banned(owner_id, anonymous_id):
        await message.answer("You are banned.")
        return

    # 3) Owner's settings (quota + captions + size)
    settings = await db.get_settings(owner_id)

    # 4) Rolling 24h limit - tracks only, replies never consume the sender's quota
    limit = settings.daily_limit
    sent_recent = 0
    oldest = None
    if limit > 0:
        sent_recent, oldest = await db.get_track_quota(
            owner_id, anonymous_id, QUOTA_WINDOW_HOURS
        )
        if sent_recent >= limit:
            await message.answer(
                f"Limit reached. The next song unlocks in {_format_wait(oldest)}."
            )
            return

    # 5) Owner-configured file size limit
    if settings.max_file_mb > 0 and message.audio.file_size:
        if message.audio.file_size > settings.max_file_mb * 1024 * 1024:
            await message.answer(
                f"File too large. Maximum is {settings.max_file_mb} MB."
            )
            return

    # 6) Caption policy
    if not settings.captions_allowed and message.caption:
        await message.answer("Captions are off here. Send the file without a caption.")
        return

    # 7) Deliver: ID first, then the track in the next message.
    #    No caption override - the original caption (if allowed) is copied as-is.
    header = await bot.send_message(owner_id, anonymous_id)
    sent = await bot.copy_message(
        chat_id=owner_id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    replies.record(owner_id, header.message_id, anonymous_id,
                   message.from_user.id, message.message_id)
    replies.record(owner_id, sent.message_id, anonymous_id,
                   message.from_user.id, message.message_id)

    await db.log_message(owner_id, anonymous_id, kind="track")

    # 8) No success message on purpose - silence means delivered.


@router.message(F.text)
async def handle_text(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id == config.owner_id:
        await message.answer("This is your own inbox. Send /help for commands.")
        return
    if await db.get_session_owner(message.from_user.id) is None:
        await message.answer("Open the owner's personal link first.")
    else:
        await message.answer("Text isn't delivered. Send a music file.")


@router.message()
async def handle_other(message: Message) -> None:
    await message.answer("Music files only (MP3, FLAC, OGG).")