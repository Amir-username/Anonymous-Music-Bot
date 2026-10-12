from __future__ import annotations

from dataclasses import dataclass

# PostgreSQL schema — executed statement-by-statement on startup
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS owners (
        owner_id   BIGINT PRIMARY KEY,
        link_code  TEXT    NOT NULL UNIQUE,
        created_at TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id           BIGSERIAL PRIMARY KEY,
        id_hash      TEXT    NOT NULL,
        owner_id     BIGINT NOT NULL REFERENCES owners(owner_id),
        anonymous_id TEXT    NOT NULL UNIQUE,
        created_at   TEXT    NOT NULL,
        UNIQUE (id_hash, owner_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id_hash      TEXT PRIMARY KEY,
        owner_id     BIGINT NOT NULL REFERENCES owners(owner_id),
        connected_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bans (
        owner_id     BIGINT NOT NULL REFERENCES owners(owner_id),
        anonymous_id TEXT    NOT NULL,
        banned_at    TEXT    NOT NULL,
        PRIMARY KEY (owner_id, anonymous_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        owner_id         BIGINT PRIMARY KEY REFERENCES owners(owner_id),
        captions_allowed INTEGER NOT NULL DEFAULT 1,
        daily_limit      INTEGER NOT NULL DEFAULT 5,
        max_file_mb      INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id           BIGSERIAL PRIMARY KEY,
        owner_id     BIGINT NOT NULL REFERENCES owners(owner_id),
        anonymous_id TEXT,
        kind         TEXT    NOT NULL DEFAULT 'track',
        sent_at      TEXT    NOT NULL
    )
    """,
)


@dataclass
class Owner:
    owner_id: int
    link_code: str
    created_at: str


@dataclass
class OwnerSettings:
    owner_id: int
    captions_allowed: bool
    daily_limit: int
    max_file_mb: int


@dataclass
class AnonymousUser:
    id_hash: str
    owner_id: int
    anonymous_id: str
    created_at: str


@dataclass
class OwnerStats:
    users: int
    tracks: int
    tracks_today: int
    replies: int
    bans: int
