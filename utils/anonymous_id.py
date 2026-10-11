import hashlib
import hmac
import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_anonymous_id() -> str:
    return "#" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def generate_link_code() -> str:
    return secrets.token_urlsafe(9)


def hash_telegram_id(telegram_id: int, secret: str) -> str:
    """Keyed one-way hash. Raw Telegram ID never touches the database."""
    return hmac.new(
        secret.encode(), str(telegram_id).encode(), hashlib.sha256
    ).hexdigest()[:32]
