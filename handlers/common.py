from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    payload = command.args  # the deep-link code will arrive here in Phase 3

    if payload:
        # Phase 3: look up owner by payload and connect the user
        await message.answer("🔗 Link code detected — owner connection arrives in Phase 3!")
    else:
        await message.answer(
            "👋 Welcome!\n\n"
            "This bot lets you send music <b>anonymously</b>.\n"
            "Use the personal link you were given to get started."
        )
