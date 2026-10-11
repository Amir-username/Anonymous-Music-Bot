from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.types import Message, ReplyParameters

from database.db import Database
from utils.filters import extract_audio

from config import Config

router = Router(name="user")


@router.message(F.audio | F.voice | F.document)
async def handle_music(message: Message, bot: Bot, db: Database) -> None:
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

    # 3) Strict music-only filter
    audio = extract_audio(message)
    if audio is None:
        await message.answer(
            "🎵 I accept music only:\n"
            "• audio files\n"
            "• voice messages\n"
            "• documents with an audio file type"
        )
        return

    # 4) Caption policy
    settings = await db.get_settings(owner_id)
    if not settings.captions_allowed and message.caption:
        await message.answer(
            "✍️🚫 The owner disabled captions.\n"
            "Send the music file without any text."
        )
        return

    # 5) Deliver to the owner
    prefix = f"🎧 <b>{anonymous_id}</b>"

    if message.voice:
        # Voice messages can't carry captions → send ID as a reply underneath
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
