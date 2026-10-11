from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

import aiosqlite

from database.models import AnonymousUser, Owner, OwnerSettings, OwnerStats, SCHEMA
from utils.anonymous_id import generate_anonymous_id, generate_link_code, hash_telegram_id

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str, hash_secret: str, default_daily_limit: int = 5) -> None:
        self.path = path
        self._hash_secret = hash_secret
        self._default_daily_limit = default_daily_limit
        self._conn: aiosqlite.Connection | None = None

    def _hash(self, telegram_id: int) -> str:
        """Raw Telegram IDs never reach the database — only this keyed hash does."""
        return hash_telegram_id(telegram_id, self._hash_secret)

    # ---------- lifecycle ----------

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.commit()
        logger.info("Database connected: %s", self.path)

    async def initialize(self) -> None:
        await self._conn.executescript(SCHEMA)
        # Migration: databases created before the per-owner limit don't have the column
        async with self._conn.execute("PRAGMA table_info(settings)") as cur:
            columns = {row["name"] for row in await cur.fetchall()}
        if "daily_limit" not in columns:
            await self._conn.execute("ALTER TABLE settings ADD COLUMN daily_limit INTEGER")
            logger.info("Migrated settings: added daily_limit column")
        # Backfill rows created before this feature existed
        await self._conn.execute(
            "UPDATE settings SET daily_limit = ? WHERE daily_limit IS NULL",
            (self._default_daily_limit,),
        )
        await self._conn.commit()
        logger.info("Database schema ready")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("Database closed")

    # ---------- owners ----------

    async def get_owner(self, owner_id: int) -> Owner | None:
        async with self._conn.execute(
            "SELECT owner_id, link_code, created_at FROM owners WHERE owner_id = ?",
            (owner_id,),
        ) as cur:
            row = await cur.fetchone()
        return Owner(row["owner_id"], row["link_code"], row["created_at"]) if row else None

    async def get_owner_by_link_code(self, link_code: str) -> Owner | None:
        async with self._conn.execute(
            "SELECT owner_id, link_code, created_at FROM owners WHERE link_code = ?",
            (link_code,),
        ) as cur:
            row = await cur.fetchone()
        return Owner(row["owner_id"], row["link_code"], row["created_at"]) if row else None

    async def ensure_owner(self, owner_id: int) -> Owner:
        """Create the owner + default settings row if they don't exist yet."""
        owner = await self.get_owner(owner_id)
        if owner:
            return owner

        await self._conn.execute(
            "INSERT OR IGNORE INTO owners (owner_id, link_code, created_at) VALUES (?, ?, ?)",
            (owner_id, generate_link_code(), _now()),
        )
        await self._conn.execute(
            "INSERT OR IGNORE INTO settings (owner_id, captions_allowed, daily_limit) "
            "VALUES (?, 1, ?)",
            (owner_id, self._default_daily_limit),
        )
        await self._conn.commit()
        logger.info("New owner registered: %s", owner_id)
        return await self.get_owner(owner_id)

    # ---------- users (anonymous identities) ----------

    async def get_or_create_user(self, telegram_id: int, owner_id: int) -> str:
        """Return the anonymous_id for this (telegram_id, owner_id) pair, creating it if new.

        The telegram_id is used only in RAM for the hash lookup — it is never stored.
        """
        id_hash = self._hash(telegram_id)

        async with self._conn.execute(
            "SELECT anonymous_id FROM users WHERE id_hash = ? AND owner_id = ?",
            (id_hash, owner_id),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row["anonymous_id"]

        while True:  # retry in the (unlikely) event of an ID collision
            anonymous_id = generate_anonymous_id()
            try:
                await self._conn.execute(
                    "INSERT INTO users (id_hash, owner_id, anonymous_id, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (id_hash, owner_id, anonymous_id, _now()),
                )
                await self._conn.commit()
                logger.info("New anonymous user %s for owner %s", anonymous_id, owner_id)
                return anonymous_id
            except sqlite3.IntegrityError:
                # Either an ID collision, or the user was created by a parallel update
                async with self._conn.execute(
                    "SELECT anonymous_id FROM users WHERE id_hash = ? AND owner_id = ?",
                    (id_hash, owner_id),
                ) as cur:
                    row = await cur.fetchone()
                if row:
                    return row["anonymous_id"]

    async def get_user_by_anonymous_id(self, owner_id: int, anonymous_id: str) -> AnonymousUser | None:
        async with self._conn.execute(
            "SELECT id_hash, owner_id, anonymous_id, created_at "
            "FROM users WHERE owner_id = ? AND anonymous_id = ?",
            (owner_id, anonymous_id),
        ) as cur:
            row = await cur.fetchone()
        return AnonymousUser(**dict(row)) if row else None

    # ---------- sessions ----------

    async def set_session(self, telegram_id: int, owner_id: int) -> None:
        """Remember which owner's inbox this user is currently connected to."""
        await self._conn.execute(
            "INSERT INTO sessions (id_hash, owner_id, connected_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id_hash) DO UPDATE SET owner_id = excluded.owner_id, "
            "connected_at = excluded.connected_at",
            (self._hash(telegram_id), owner_id, _now()),
        )
        await self._conn.commit()

    async def get_session_owner(self, telegram_id: int) -> int | None:
        async with self._conn.execute(
            "SELECT owner_id FROM sessions WHERE id_hash = ?",
            (self._hash(telegram_id),),
        ) as cur:
            row = await cur.fetchone()
        return row["owner_id"] if row else None

    # ---------- bans ----------

    async def ban_user(self, owner_id: int, anonymous_id: str) -> bool:
        """Returns True if the ban was newly applied."""
        cur = await self._conn.execute(
            "INSERT OR IGNORE INTO bans (owner_id, anonymous_id, banned_at) VALUES (?, ?, ?)",
            (owner_id, anonymous_id, _now()),
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def unban_user(self, owner_id: int, anonymous_id: str) -> bool:
        """Returns True if a ban actually existed and was removed."""
        cur = await self._conn.execute(
            "DELETE FROM bans WHERE owner_id = ? AND anonymous_id = ?",
            (owner_id, anonymous_id),
        )
        await self._conn.commit()
        return cur.rowcount > 0

    async def is_banned(self, owner_id: int, anonymous_id: str) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM bans WHERE owner_id = ? AND anonymous_id = ? LIMIT 1",
            (owner_id, anonymous_id),
        ) as cur:
            return await cur.fetchone() is not None

    async def list_bans(self, owner_id: int) -> list[str]:
        async with self._conn.execute(
            "SELECT anonymous_id FROM bans WHERE owner_id = ? ORDER BY banned_at DESC",
            (owner_id,),
        ) as cur:
            return [row["anonymous_id"] for row in await cur.fetchall()]

    # ---------- settings ----------

    async def get_settings(self, owner_id: int) -> OwnerSettings:
        async with self._conn.execute(
            "SELECT owner_id, captions_allowed, daily_limit FROM settings WHERE owner_id = ?",
            (owner_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return OwnerSettings(row["owner_id"], bool(row["captions_allowed"]), row["daily_limit"])
        # Row missing — self-heal with defaults
        await self.set_captions_allowed(owner_id, True)
        return OwnerSettings(owner_id, True, self._default_daily_limit)

    async def set_captions_allowed(self, owner_id: int, allowed: bool) -> None:
        await self._conn.execute(
            "INSERT INTO settings (owner_id, captions_allowed, daily_limit) VALUES (?, ?, ?) "
            "ON CONFLICT(owner_id) DO UPDATE SET captions_allowed = excluded.captions_allowed",
            (owner_id, int(allowed), self._default_daily_limit),
        )
        await self._conn.commit()

    async def set_daily_limit(self, owner_id: int, limit: int) -> None:
        """limit = 0 means unlimited."""
        await self._conn.execute(
            "INSERT INTO settings (owner_id, captions_allowed, daily_limit) VALUES (?, 1, ?) "
            "ON CONFLICT(owner_id) DO UPDATE SET daily_limit = excluded.daily_limit",
            (owner_id, limit),
        )
        await self._conn.commit()

    # ---------- messages (for future stats/replies) ----------

    async def log_message(self, owner_id: int, anonymous_id: str | None) -> None:
        await self._conn.execute(
            "INSERT INTO messages (owner_id, anonymous_id, sent_at) VALUES (?, ?, ?)",
            (owner_id, anonymous_id, _now()),
        )
        await self._conn.commit()

    async def count_messages(self, owner_id: int) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE owner_id = ?",
            (owner_id,),
        ) as cur:
            row = await cur.fetchone()
        return row["c"]

    async def count_messages_today(self, owner_id: int, anonymous_id: str) -> int:
        """Deliveries since UTC midnight for this anonymous ID.

        Works via string comparison because sent_at is ISO-8601:
        everything from today starts with today's date prefix.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        async with self._conn.execute(
            "SELECT COUNT(*) AS c FROM messages "
            "WHERE owner_id = ? AND anonymous_id = ? AND sent_at >= ?",
            (owner_id, anonymous_id, today),
        ) as cur:
            row = await cur.fetchone()
        return row["c"]

    # ---------- stats ----------

    async def get_stats(self, owner_id: int) -> OwnerStats:
        async with self._conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM users WHERE owner_id = ?)    AS users, "
            "(SELECT COUNT(*) FROM messages WHERE owner_id = ?) AS messages, "
            "(SELECT COUNT(*) FROM bans WHERE owner_id = ?)     AS bans",
            (owner_id, owner_id, owner_id),
        ) as cur:
            row = await cur.fetchone()
        return OwnerStats(users=row["users"], messages=row["messages"], bans=row["bans"])