from __future__ import annotations

import logging
from datetime import datetime, timezone

import asyncpg
from asyncpg.exceptions import UniqueViolationError

from database.models import (
    AnonymousUser,
    Owner,
    OwnerSettings,
    OwnerStats,
    SCHEMA_STATEMENTS,
)
from utils.anonymous_id import generate_anonymous_id, generate_link_code, hash_telegram_id

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, dsn: str, hash_secret: str, default_daily_limit: int = 5) -> None:
        self.dsn = dsn
        self._hash_secret = hash_secret
        self._default_daily_limit = default_daily_limit
        self._pool: asyncpg.Pool | None = None

    def _hash(self, telegram_id: int) -> str:
        """Raw Telegram IDs never reach the database — only this keyed hash does."""
        return hash_telegram_id(telegram_id, self._hash_secret)

    # ---------- lifecycle ----------

    async def connect(self) -> None:
        kwargs = {}
        if "sslmode=" not in self.dsn:
            kwargs["ssl"] = "require"  # hosted Postgres requires TLS
        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5, **kwargs)
        logger.info("Database pool connected")

    async def initialize(self) -> None:
        for statement in SCHEMA_STATEMENTS:
            await self._pool.execute(statement)
        logger.info("Database schema ready")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            logger.info("Database pool closed")

    # ---------- owners ----------

    async def get_owner(self, owner_id: int) -> Owner | None:
        row = await self._pool.fetchrow(
            "SELECT owner_id, link_code, created_at FROM owners WHERE owner_id = $1",
            owner_id,
        )
        return Owner(row["owner_id"], row["link_code"], row["created_at"]) if row else None

    async def get_owner_by_link_code(self, link_code: str) -> Owner | None:
        row = await self._pool.fetchrow(
            "SELECT owner_id, link_code, created_at FROM owners WHERE link_code = $1",
            link_code,
        )
        return Owner(row["owner_id"], row["link_code"], row["created_at"]) if row else None

    async def ensure_owner(self, owner_id: int) -> Owner:
        """Create the owner + default settings row if they don't exist yet."""
        owner = await self.get_owner(owner_id)
        if owner:
            return owner

        await self._pool.execute(
            "INSERT INTO owners (owner_id, link_code, created_at) "
            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            owner_id, generate_link_code(), _now(),
        )
        await self._pool.execute(
            "INSERT INTO settings (owner_id, captions_allowed, daily_limit) "
            "VALUES ($1, 1, $2) ON CONFLICT DO NOTHING",
            owner_id, self._default_daily_limit,
        )
        logger.info("New owner registered: %s", owner_id)
        return await self.get_owner(owner_id)

    # ---------- users (anonymous identities) ----------

    async def get_or_create_user(self, telegram_id: int, owner_id: int) -> str:
        """Return the anonymous_id for this (telegram_id, owner_id) pair, creating it if new.

        The telegram_id is used only in RAM for the hash lookup — it is never stored.
        """
        id_hash = self._hash(telegram_id)

        row = await self._pool.fetchrow(
            "SELECT anonymous_id FROM users WHERE id_hash = $1 AND owner_id = $2",
            id_hash, owner_id,
        )
        if row:
            return row["anonymous_id"]

        while True:  # retry in the (unlikely) event of an ID collision
            anonymous_id = generate_anonymous_id()
            try:
                await self._pool.execute(
                    "INSERT INTO users (id_hash, owner_id, anonymous_id, created_at) "
                    "VALUES ($1, $2, $3, $4)",
                    id_hash, owner_id, anonymous_id, _now(),
                )
                logger.info("New anonymous user %s for owner %s", anonymous_id, owner_id)
                return anonymous_id
            except UniqueViolationError:
                # Either an ID collision, or the user was created by a parallel update
                row = await self._pool.fetchrow(
                    "SELECT anonymous_id FROM users WHERE id_hash = $1 AND owner_id = $2",
                    id_hash, owner_id,
                )
                if row:
                    return row["anonymous_id"]

    async def get_user_by_anonymous_id(self, owner_id: int, anonymous_id: str) -> AnonymousUser | None:
        row = await self._pool.fetchrow(
            "SELECT id_hash, owner_id, anonymous_id, created_at "
            "FROM users WHERE owner_id = $1 AND anonymous_id = $2",
            owner_id, anonymous_id,
        )
        return AnonymousUser(**dict(row)) if row else None

    # ---------- sessions ----------

    async def set_session(self, telegram_id: int, owner_id: int) -> None:
        """Remember which owner's inbox this user is currently connected to."""
        await self._pool.execute(
            "INSERT INTO sessions (id_hash, owner_id, connected_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (id_hash) DO UPDATE SET owner_id = $2, connected_at = $3",
            self._hash(telegram_id), owner_id, _now(),
        )

    async def get_session_owner(self, telegram_id: int) -> int | None:
        return await self._pool.fetchval(
            "SELECT owner_id FROM sessions WHERE id_hash = $1",
            self._hash(telegram_id),
        )

    # ---------- bans ----------

    async def ban_user(self, owner_id: int, anonymous_id: str) -> bool:
        """Returns True if the ban was newly applied."""
        tag = await self._pool.execute(
            "INSERT INTO bans (owner_id, anonymous_id, banned_at) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING",
            owner_id, anonymous_id, _now(),
        )
        return tag == "INSERT 0 1"

    async def unban_user(self, owner_id: int, anonymous_id: str) -> bool:
        """Returns True if a ban actually existed and was removed."""
        tag = await self._pool.execute(
            "DELETE FROM bans WHERE owner_id = $1 AND anonymous_id = $2",
            owner_id, anonymous_id,
        )
        return tag != "DELETE 0"

    async def is_banned(self, owner_id: int, anonymous_id: str) -> bool:
        val = await self._pool.fetchval(
            "SELECT 1 FROM bans WHERE owner_id = $1 AND anonymous_id = $2 LIMIT 1",
            owner_id, anonymous_id,
        )
        return val is not None

    async def list_bans(self, owner_id: int) -> list[str]:
        rows = await self._pool.fetch(
            "SELECT anonymous_id FROM bans WHERE owner_id = $1 ORDER BY banned_at DESC",
            owner_id,
        )
        return [row["anonymous_id"] for row in rows]

    # ---------- settings ----------

    async def get_settings(self, owner_id: int) -> OwnerSettings:
        row = await self._pool.fetchrow(
            "SELECT owner_id, captions_allowed, daily_limit FROM settings WHERE owner_id = $1",
            owner_id,
        )
        if row:
            return OwnerSettings(row["owner_id"], bool(row["captions_allowed"]), row["daily_limit"])
        # Row missing — self-heal with defaults
        await self.set_captions_allowed(owner_id, True)
        return OwnerSettings(owner_id, True, self._default_daily_limit)

    async def set_captions_allowed(self, owner_id: int, allowed: bool) -> None:
        await self._pool.execute(
            "INSERT INTO settings (owner_id, captions_allowed, daily_limit) VALUES ($1, $2, $3) "
            "ON CONFLICT (owner_id) DO UPDATE SET captions_allowed = $2",
            owner_id, int(allowed), self._default_daily_limit,
        )

    async def set_daily_limit(self, owner_id: int, limit: int) -> None:
        """limit = 0 means unlimited."""
        await self._pool.execute(
            "INSERT INTO settings (owner_id, captions_allowed, daily_limit) VALUES ($1, 1, $2) "
            "ON CONFLICT (owner_id) DO UPDATE SET daily_limit = $2",
            owner_id, limit,
        )

    # ---------- messages (for future stats/replies) ----------

    async def log_message(self, owner_id: int, anonymous_id: str | None) -> None:
        await self._pool.execute(
            "INSERT INTO messages (owner_id, anonymous_id, sent_at) VALUES ($1, $2, $3)",
            owner_id, anonymous_id, _now(),
        )

    async def count_messages(self, owner_id: int) -> int:
        return await self._pool.fetchval(
            "SELECT COUNT(*) FROM messages WHERE owner_id = $1",
            owner_id,
        )

    async def count_messages_today(self, owner_id: int, anonymous_id: str) -> int:
        """Deliveries since UTC midnight for this anonymous ID.

        Works via string comparison because sent_at is ISO-8601:
        everything from today starts with today's date prefix.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        return await self._pool.fetchval(
            "SELECT COUNT(*) FROM messages "
            "WHERE owner_id = $1 AND anonymous_id = $2 AND sent_at >= $3",
            owner_id, anonymous_id, today,
        )

    # ---------- stats ----------

    async def get_stats(self, owner_id: int) -> OwnerStats:
        row = await self._pool.fetchrow(
            "SELECT "
            "(SELECT COUNT(*) FROM users WHERE owner_id = $1)    AS users, "
            "(SELECT COUNT(*) FROM messages WHERE owner_id = $1) AS messages, "
            "(SELECT COUNT(*) FROM bans WHERE owner_id = $1)     AS bans",
            owner_id,
        )
        return OwnerStats(users=row["users"], messages=row["messages"], bans=row["bans"])