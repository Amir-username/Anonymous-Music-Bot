import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    owner_id: int


def get_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    owner_id = os.getenv("OWNER_ID")

    if not token:
        raise RuntimeError("BOT_TOKEN is missing from .env")
    if not owner_id or not owner_id.isdigit():
        raise RuntimeError("OWNER_ID is missing or not a number in .env")

    return Config(bot_token=token, owner_id=int(owner_id))
