"""In-process pub/sub event bus that fans agent activity out to WebSocket clients.

The orchestrator publishes events keyed by chat id; each connected WebSocket
subscribes to a chat and drains its own queue. This keeps the pipeline decoupled
from the transport and lets multiple viewers watch the same chat live.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, chat_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[chat_id].add(queue)
        return queue

    def unsubscribe(self, chat_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(chat_id)
        if subs:
            subs.discard(queue)
            if not subs:
                self._subscribers.pop(chat_id, None)

    async def publish(self, chat_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(chat_id, ())):
            await queue.put(event)

    async def stream(self, chat_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield events for a chat until the consumer stops iterating."""
        queue = self.subscribe(chat_id)
        try:
            while True:
                yield await queue.get()
        finally:
            self.unsubscribe(chat_id, queue)


# Single process-wide bus.
event_bus = EventBus()
