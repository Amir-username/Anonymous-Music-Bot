import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    owner_id: int
    hash_secret: str
    db_path: str = "bot.db"


def get_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    owner_id = os.getenv("OWNER_ID")
    hash_secret = os.getenv("HASH_SECRET")
    db_path = os.getenv("DB_PATH", "bot.db")

    if not token:
        raise RuntimeError("BOT_TOKEN is missing from .env")
    if not owner_id or not owner_id.isdigit():
        raise RuntimeError("OWNER_ID is missing or not a number in .env")
    if not hash_secret:
        raise RuntimeError(
            'HASH_SECRET is missing. Generate one with: '
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    return Config(
        bot_token=token,
        owner_id=int(owner_id),
        hash_secret=hash_secret,
        db_path=db_path,
    )
