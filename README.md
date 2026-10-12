# Anonymous Music Bot

A privacy-first Telegram bot that lets people send music to one person — anonymously.

Listeners open the owner's personal link, send an audio file, and the owner receives it labeled only with a random ID like `#A7K9P2`. The owner can reply to any track, and the reply reaches the sender without either side ever learning who the other is.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![aiogram](https://img.shields.io/badge/aiogram-3.x-green)
![PostgreSQL](https://img.shields.io/badge/postgresql-required-blue)

---

## How it works

**For listeners (senders)**

1. Open the owner's personal link — `https://t.me/<your_bot>?start=<code>`
2. Send any music file to the bot (MP3, FLAC, OGG — plain audio files)
3. Done. The owner never sees your name, username, or profile — only your anonymous ID

**For the owner**

- Each delivery arrives as two messages: a short header with the sender's anonymous ID, then the track itself
- To answer a listener, swipe-reply to the header or the track with text, voice, or audio — the bot routes it back anonymously
- Everything is controlled from Telegram commands: quota, captions, file size, bans

**Guardrails**

- Non-audio messages are rejected (text is never delivered)
- Captions can be disabled globally by the owner; when allowed, the original caption is forwarded as-is
- A per-listener rolling 24-hour quota protects the owner's inbox
- Banned senders are rejected silently by ID

---

## Features

- **Real anonymity** — Telegram user IDs are never written to the database; only keyed one-way hashes are stored
- **Anonymous replies** — the owner answers by replying to a delivered track; routing data lives in RAM only and expires in 24 h
- **Rolling quota** — each listener gets N tracks per rolling 24-hour window, anchored to their own sends (not calendar days)
- **Owner controls** — toggle captions, set per-listener limits, cap file size, ban/unban by anonymous ID
- **Statistics** — listeners, tracks delivered, replies sent, bans
- **Zero-dependency hosting** — a single Python process plus any PostgreSQL; ships with a health endpoint for platforms like Render

---

## Privacy model

This bot is designed so that anonymity survives even if the database leaks.

- **No raw IDs on disk.** A listener's Telegram ID is transformed with `HMAC-SHA256(secret)` and only the first 32 hex characters are stored. Reversing this requires the `HASH_SECRET`, which never leaves your environment.
- **Random anonymous IDs.** Each listener gets a 6-character ID from an unambiguous alphabet (no `0/O`, no `1/I`), so the owner can ban or reply to a sender without ever knowing who they are. The ID is deliberately not shown to the sender themselves.
- **Memory-only reply routing.** The mapping from a delivered track to its sender exists only in the bot's RAM, with a 24-hour TTL and a hard cap of 1,000 records per owner. A restart wipes it — the bot then *refuses* to route replies to older tracks rather than guessing. This is fail-closed by design.
- **No content storage.** The database holds only counters (who sent how many tracks, replies, bans, settings). Media is relayed by Telegram and never stored by the bot.

> Trade-off: because reply routing is memory-only, the owner cannot reply to tracks that arrived before the last restart. The bot will say so explicitly.

---

## Quick start (local)

**Prerequisites:** Python 3.11+, a PostgreSQL database (local or hosted), a Telegram bot token.

```bash
git clone https://github.com/Amir-username/Anonymous-Music-Bot.git
cd Anonymous-Music-Bot

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file next to `main.py`:

```env
BOT_TOKEN=123456789:AA...your-token-from-BotFather
OWNER_ID=123456789
HASH_SECRET=generate-one-see-below
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
RATE_LIMIT_DAILY=5
```

| Variable | Where to get it |
|---|---|
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` |
| `OWNER_ID` | Your numeric Telegram ID (e.g. from [@userinfobot](https://t.me/userinfobot)) |
| `HASH_SECRET` | Any long random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | Your PostgreSQL connection string (must start with `postgres://` or `postgresql://`) |
| `RATE_LIMIT_DAILY` | Default per-listener quota applied when the owner's settings row is first created (`0` = unlimited) |

Run it:

```bash
python main.py
```

The schema is created automatically on first start. Open your bot in Telegram and send `/start` — as the owner you'll get your control panel and personal inbox link.

---

## Owner commands

| Command | Description |
|---|---|
| `/link` | Show your personal inbox link to share |
| `/captions on` / `/captions off` | Allow or reject captions on incoming tracks |
| `/limit N` | Songs each listener may send per rolling 24 h (1–100); `/limit off` for unlimited |
| `/maxsize N` | Reject files larger than N MB (1–2000); `/maxsize off` for unlimited |
| `/ban #A7K9P2` | Ban a sender by their anonymous ID |
| `/unban #A7K9P2` | Lift a ban |
| `/bans` | List all banned IDs |
| `/status` | Current settings + statistics |
| `/help` | Show the control panel |

**Replying to a listener:** swipe-reply to the `#ID` header or to the delivered track. Text, voice messages, and audio files all work. Every other reply target is ignored, so normal messages you send to the bot are never forwarded to anyone.

---

## Deploying to Render

The bot is a long-polling process, so it runs happily as a Render **Background Worker** — but it also serves a small HTTP health endpoint on `$PORT` (default `8000`) if you prefer a **Web Service**.

1. **Database** — create a PostgreSQL instance on Render and copy the *Internal Database URL*.
2. **Service** — create a new service from this repo:
   - *Background Worker* (recommended), or *Web Service* with health check path `/`
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
3. **Environment** — add the five variables from the table above. `DATABASE_URL` is the Internal Database URL; Render injects `PORT` automatically.
4. Deploy. The first boot creates the schema and registers you as the owner.

Two operational notes:

- **Deploys reset reply routing.** Render restarts the process on every deploy, so replies to tracks delivered before the restart are refused (the bot explains this to the owner). Track delivery itself is never lost — pending Telegram updates are pulled on startup.
- **Scale to one instance.** The RAM reply registry is per-process; running two instances will break reply routing. One instance comfortably serves a single owner's inbox.

---

## Project structure

```
├── main.py                 # entry point: DB pool, dispatcher, health server, polling
├── config.py               # env validation (fails fast with helpful messages)
├── handlers/
│   ├── common.py           # /start deep-link connect, owner panel, /help
│   ├── user.py             # music intake pipeline + quota
│   ├── owner.py            # owner commands + anonymous reply routing
│   └── errors.py           # global error handler
├── database/
│   ├── models.py           # SQL schema + dataclasses
│   └── db.py               # asyncpg pool wrapper (all queries live here)
└── utils/
    ├── anonymous_id.py     # ID/link-code generation, HMAC hashing
    ├── replies.py          # in-RAM delivery → sender registry (24 h TTL)
    └── filters.py          # media extraction helpers
```

**Tech stack:** [aiogram 3.x](https://docs.aiogram.dev/) · [asyncpg](https://magicstack.github.io/asyncpg/) · [aiohttp](https://docs.aiohttp.org/) · PostgreSQL

---

## FAQ

**When does the send limit reset?**
It doesn't "reset" at a fixed time. Each listener's quota is a rolling 24-hour window: a track stops counting exactly 24 hours after it was sent. If you hit the limit, the bot tells you the exact wait time. Replies from the owner never consume your quota.

**Why can't the owner reply to my older track?**
Reply routing is kept in RAM only, for privacy, and is wiped on every restart. Tracks delivered after the latest restart can be answered normally.

**Does the sender know their own anonymous ID?**
No — by design. Only the owner sees the `#ID`, which is all that's needed for banning or replying.

**Can the owner find out who sent a track?**
Not through the bot. The database stores only a keyed hash of Telegram IDs, and the plaintext mapping never touches disk.

**What file types are accepted?**
Plain audio files — MP3, FLAC, OGG, etc. Voice messages and documents are rejected with a hint.

---

## License

Released under the [MIT License](LICENSE).
