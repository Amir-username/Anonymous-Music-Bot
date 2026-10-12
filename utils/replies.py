from __future__ import annotations

import time
from dataclasses import dataclass

TTL_SECONDS = 24 * 60 * 60  # replies possible for 24h after delivery
MAX_PER_OWNER = 1000        # hard cap per owner (oldest evicted)


@dataclass
class DeliveryRecord:
    anonymous_id: str
    sender_telegram_id: int
    sender_message_id: int  # the user's original track message, for threading
    delivered_at: float


class ReplyRegistry:
    """In-RAM mapping of delivered tracks → their anonymous senders.

    Deliberately memory-only: raw Telegram IDs never touch the disk, so a
    restart wipes the mapping and replies to older tracks are refused
    (fail closed). This is the price of the anonymity model.
    """

    def __init__(self) -> None:
        self._records: dict[int, dict[int, DeliveryRecord]] = {}

    def record(
        self,
        owner_id: int,
        delivered_message_id: int,
        anonymous_id: str,
        sender_telegram_id: int,
        sender_message_id: int,
    ) -> None:
        book = self._records.setdefault(owner_id, {})
        now = time.time()

        # Lazy TTL eviction
        for mid in [m for m, r in book.items() if now - r.delivered_at > TTL_SECONDS]:
            del book[mid]

        # Hard cap — evict the oldest
        overflow = len(book) - MAX_PER_OWNER + 1
        if overflow > 0:
            oldest = sorted(book.items(), key=lambda kv: kv[1].delivered_at)[:overflow]
            for mid, _ in oldest:
                del book[mid]

        book[delivered_message_id] = DeliveryRecord(
            anonymous_id, sender_telegram_id, sender_message_id, now
        )

    def lookup(self, owner_id: int, delivered_message_id: int) -> DeliveryRecord | None:
        rec = self._records.get(owner_id, {}).get(delivered_message_id)
        if rec is None or time.time() - rec.delivered_at > TTL_SECONDS:
            return None
        return rec
