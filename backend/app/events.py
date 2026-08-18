"""Event bus: Redis pub/sub when configured, in-memory fan-out otherwise.

Services publish events (scan/devices/alerts/bandwidth/stats) and WebSocket
clients subscribe to receive real-time updates.
"""

import asyncio
import json

import redis.asyncio as aioredis

from .config import get_settings

_broker: "EventBroker | None" = None
CHANNEL = "netwatch"


def init_broker() -> "EventBroker":
    global _broker
    _broker = EventBroker(get_settings().redis_url)
    return _broker


def get_broker() -> "EventBroker | None":
    return _broker


class EventBroker:
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url) if redis_url else None
        self._subs: set[asyncio.Queue] = set()

    async def publish(self, event: dict) -> None:
        if self._redis is not None:
            try:
                await self._redis.publish(CHANNEL, json.dumps(event))
            except Exception:
                pass
        for queue in list(self._subs):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self):
        """Async generator of events for a single client."""
        if self._redis is not None:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(CHANNEL)
            try:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message:
                        try:
                            yield json.loads(message["data"])
                        except (TypeError, json.JSONDecodeError):
                            continue
                    else:
                        await asyncio.sleep(0.25)
            finally:
                await pubsub.unsubscribe(CHANNEL)
        else:
            queue: asyncio.Queue = asyncio.Queue(maxsize=500)
            self._subs.add(queue)
            try:
                while True:
                    yield await queue.get()
            finally:
                self._subs.discard(queue)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
