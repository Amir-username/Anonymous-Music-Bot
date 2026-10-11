from __future__ import annotations

from aiogram.types import Message


def extract_audio(message: Message):
    """Return the media object if the message carries acceptable music, else None.

    Accepts: audio files, voice messages, documents with an audio/* MIME type.
    """
    if message.audio:
        return message.audio, "audio"
    if message.voice:
        return message.voice, "voice"
    if (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("audio/")
    ):
        return message.document, "audio file"
    return None
