"""Small Redis Pub/Sub wrapper for best-effort realtime delivery."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class RedisEventBus:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Any | None = None
        self._stats: dict[str, Any] = {
            "connected": False,
            "connect_success_count": 0,
            "connect_failure_count": 0,
            "reconnect_count": 0,
            "publish_success_count": 0,
            "publish_failure_count": 0,
            "publish_fallback_count": 0,
            "subscribe_error_count": 0,
            "handler_error_count": 0,
            "invalid_payload_count": 0,
            "last_connected_at": None,
            "last_connect_error": None,
            "last_publish_error": None,
            "last_subscribe_error": None,
            "subscribed_events": {},
        }

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            from redis.asyncio import Redis
        except Exception as e:
            logger.warning("[redis_bus] redis package unavailable: %s", e)
            return None
        try:
            self._client = Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=None,
                socket_connect_timeout=10,
                health_check_interval=30,
            )
            await self._client.ping()
            self._stats["connected"] = True
            self._stats["connect_success_count"] += 1
            self._stats["reconnect_count"] = max(0, self._stats["connect_success_count"] - 1)
            self._stats["last_connected_at"] = self._utc_now_iso()
            self._stats["last_connect_error"] = None
            logger.info(
                "[redis_bus] connected url=%s connect_success=%s reconnect=%s",
                self._safe_url(),
                self._stats["connect_success_count"],
                self._stats["reconnect_count"],
            )
            return self._client
        except Exception as e:
            self._stats["connected"] = False
            self._stats["connect_failure_count"] += 1
            self._stats["last_connect_error"] = str(e)
            logger.warning("[redis_bus] connect failed url=%s: %s", self._safe_url(), e)
            self._client = None
            return None

    def _safe_url(self) -> str:
        if "@" not in self.redis_url:
            return self.redis_url
        scheme, rest = self.redis_url.split("://", 1) if "://" in self.redis_url else ("", self.redis_url)
        tail = rest.split("@", 1)[1]
        return f"{scheme}://***@{tail}" if scheme else f"***@{tail}"

    async def publish(self, event: str, payload: dict[str, Any]) -> bool:
        client = await self._get_client()
        if client is None:
            self.record_fallback(event)
            return False
        message = {"event": event, "payload": payload}
        try:
            await client.publish(event, json.dumps(message, default=str))
            self._stats["publish_success_count"] += 1
            logger.debug("[redis_bus] published event=%s", event)
            return True
        except Exception as e:
            self._stats["connected"] = False
            self._stats["publish_failure_count"] += 1
            self._stats["last_publish_error"] = str(e)
            self.record_fallback(event)
            self._client = None
            logger.warning("[redis_bus] publish failed event=%s: %s", event, e)
            return False

    async def subscribe_forever(self, event: str, handler: EventHandler) -> None:
        self._stats["subscribed_events"].setdefault(event, {"messages": 0, "errors": 0, "last_message_at": None})
        while True:
            client = await self._get_client()
            if client is None:
                await asyncio.sleep(5)
                continue
            pubsub = client.pubsub()
            try:
                await pubsub.subscribe(event)
                self._stats["subscribed_events"][event]["active"] = True
                logger.info("[redis_bus] subscribed event=%s", event)
                while True:
                    raw = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=5.0,
                    )
                    if raw is None:
                        continue
                    if raw.get("type") != "message":
                        continue
                    try:
                        self._stats["subscribed_events"][event]["messages"] += 1
                        self._stats["subscribed_events"][event]["last_message_at"] = self._utc_now_iso()
                        body = json.loads(raw.get("data") or "{}")
                        payload = body.get("payload") if isinstance(body, dict) else None
                        if not isinstance(payload, dict):
                            self._stats["invalid_payload_count"] += 1
                            logger.warning("[redis_bus] invalid payload event=%s", event)
                            continue
                        await handler(payload)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        self._stats["handler_error_count"] += 1
                        self._stats["subscribed_events"][event]["errors"] += 1
                        logger.warning("[redis_bus] handler failed event=%s: %s", event, e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._stats["connected"] = False
                self._stats["subscribe_error_count"] += 1
                self._stats["last_subscribe_error"] = str(e)
                self._stats["subscribed_events"][event]["active"] = False
                logger.warning("[redis_bus] subscribe loop failed event=%s: %s", event, e)
                self._client = None
                await asyncio.sleep(5)
            finally:
                try:
                    await pubsub.unsubscribe(event)
                    await pubsub.close()
                except Exception:
                    pass

    def record_fallback(self, event: str) -> None:
        self._stats["publish_fallback_count"] += 1
        event_stats = self._stats["subscribed_events"].setdefault(
            event,
            {"messages": 0, "errors": 0, "last_message_at": None},
        )
        event_stats["fallbacks"] = int(event_stats.get("fallbacks") or 0) + 1
        logger.info(
            "[redis_bus] publish fallback event=%s fallback_count=%s event_fallback_count=%s",
            event,
            self._stats["publish_fallback_count"],
            event_stats["fallbacks"],
        )

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "redis_url": self._safe_url(),
        }

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.close()
        except Exception:
            pass
        self._stats["connected"] = False
        self._client = None


redis_event_bus = RedisEventBus()
