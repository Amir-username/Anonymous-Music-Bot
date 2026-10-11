from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.types import Message, ReplyParameters

from config import Config
from database.db import Database
from utils.filters import extract_audio

router = Router(name="user")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(F.audio | F.voice | F.document)
async def handle_music(message: Message, bot: Bot, db: Database, config: Config) -> None:
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

    # 3) Owner's settings (limit + captions)
    settings = await db.get_settings(owner_id)

    # 4) Daily rate limit — per-owner, only successful deliveries consume quota
    limit = settings.daily_limit
    sent_today = 0
    if limit > 0:
        sent_today = await db.count_messages_today(owner_id, anonymous_id)
        if sent_today >= limit:
            await message.answer(
                "⏳ <b>Daily limit reached.</b>\n"
                f"You can send {limit} songs per day — try again tomorrow. 🌙"
            )
            return

    # 5) Strict music-only filter
    audio = extract_audio(message)
    if audio is None:
        await message.answer(
            "🎵 I accept music only:\n"
            "• audio files\n"
            "• voice messages\n"
            "• documents with an audio file type"
        )
        return

    # 6) Caption policy
    if not settings.captions_allowed and message.caption:
        await message.answer(
            "✍️🚫 The owner disabled captions.\n"
            "Resend the music file without any text attached."
        )
        return

    # 7) Deliver to the owner
    prefix = f"🎧 <b>{anonymous_id}</b>"

    if message.voice:
        copied = await bot.copy_message(
            chat_id=owner_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await bot.send_message(
            owner_id,
            prefix,
            reply_parameters=ReplyParameters(message_id=copied.message_id),
        )
    else:
        original = message.caption or ""
        if settings.captions_allowed and original:
            escaped = html.escape(original)
            room = 1024 - len(prefix) - 1  # Telegram caption limit
            caption = f"{prefix}\n{escaped[:room]}"
        else:
            caption = prefix
        await bot.copy_message(
            chat_id=owner_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            caption=caption,
        )

    await db.log_message(owner_id, anonymous_id)

    # 8) Friendly confirmation with remaining quota
    if limit > 0:
        remaining = limit - sent_today - 1
        if remaining > 0:
            await message.answer(f"✅ Sent anonymously — {remaining} left today.")
        else:
            await message.answer("✅ Sent anonymously — that was your last song for today. 🌙")
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