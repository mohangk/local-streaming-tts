from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator


class EventBroker:
    def __init__(self):
        self._history: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self._subscribers: dict[int, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, generation_id: int, event: dict[str, Any]) -> None:
        self._history[generation_id].append(event)
        for queue in list(self._subscribers[generation_id]):
            await queue.put(event)

    async def subscribe(self, generation_id: int) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        replay_events = list(self._history[generation_id])
        replayed_count = len(replay_events)
        try:
            for event in replay_events:
                yield event

            self._subscribers[generation_id].append(queue)
            missed_events = list(self._history[generation_id][replayed_count:])
            for event in missed_events:
                yield event

            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers[generation_id]:
                self._subscribers[generation_id].remove(queue)
