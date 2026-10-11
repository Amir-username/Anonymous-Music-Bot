from __future__ import annotations

from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS owners (
    owner_id   INTEGER PRIMARY KEY,
    link_code  TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_hash      TEXT    NOT NULL,
    owner_id     INTEGER NOT NULL REFERENCES owners(owner_id),
    anonymous_id TEXT    NOT NULL UNIQUE,
    created_at   TEXT    NOT NULL,
    UNIQUE (id_hash, owner_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id_hash      TEXT PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES owners(owner_id),
    connected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bans (
    owner_id     INTEGER NOT NULL REFERENCES owners(owner_id),
    anonymous_id TEXT    NOT NULL,
    banned_at    TEXT    NOT NULL,
    PRIMARY KEY (owner_id, anonymous_id)
);

CREATE TABLE IF NOT EXISTS settings (
    owner_id         INTEGER PRIMARY KEY REFERENCES owners(owner_id),
    captions_allowed INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES owners(owner_id),
    anonymous_id TEXT,
    sent_at      TEXT    NOT NULL
);
"""


@dataclass
class Owner:
    owner_id: int
    link_code: str
    created_at: str


@dataclass
class OwnerSettings:
    owner_id: int
    captions_allowed: bool


@dataclass
class AnonymousUser:
    id_hash: str
    owner_id: int
    anonymous_id: str
    created_at: str
