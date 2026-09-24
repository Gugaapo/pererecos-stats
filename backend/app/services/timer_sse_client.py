"""Long-lived SSE client for MeiaUm /api/v1/timer/stream."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_settings
from app.services.timer_client import USER_AGENT, TimerFeedError

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any] | None, str | None], Awaitable[None]]


class TimerStreamClient:
    def __init__(self) -> None:
        self._last_event_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(None, connect=10.0),
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "User-Agent": USER_AGENT,
                },
                limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def run_forever(self, stop: asyncio.Event, on_event: EventHandler) -> None:
        settings = get_settings()
        url = (settings.timer_stream_url or "").strip()
        if not url or not settings.timer_stream_enabled:
            logger.warning("Timer stream disabled or empty URL")
            return

        backoff = 1.0
        logger.info("Subathon SSE starting url=%s", url)
        while not stop.is_set():
            try:
                await self._one_connection(url, stop, on_event)
                backoff = 1.0
            except TimerFeedError as exc:
                logger.warning("SSE feed error: %s", exc)
                if exc.status == 429 and exc.retry_after:
                    backoff = float(exc.retry_after)
                else:
                    backoff = min(60.0, backoff * 1.5)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("SSE unexpected error")
                backoff = min(60.0, backoff * 1.5)

            if stop.is_set():
                break
            delay = backoff * (0.8 + random.random() * 0.4)
            logger.info("SSE reconnecting in %.1fs (last_id=%s)", delay, self._last_event_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                continue
        logger.info("Subathon SSE stopped")

    async def _one_connection(
        self,
        url: str,
        stop: asyncio.Event,
        on_event: EventHandler,
    ) -> None:
        headers: dict[str, str] = {}
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id

        client = await self._http()
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code != 200:
                detail = ""
                try:
                    detail = (await resp.aread()).decode("utf-8", errors="replace")[:200]
                except Exception:
                    detail = f"HTTP {resp.status_code}"
                retry = None
                try:
                    retry = max(1, int(resp.headers.get("Retry-After", "")))
                except (TypeError, ValueError):
                    retry = None
                raise TimerFeedError(resp.status_code, detail, retry)

            event_name: str | None = None
            data_lines: list[str] = []
            event_id: str | None = None
            buffer = ""

            async for chunk in resp.aiter_text():
                if stop.is_set():
                    return
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if line.startswith(":"):
                        continue
                    if line.startswith("id:"):
                        event_id = line[3:].strip()
                        if event_id:
                            self._last_event_id = event_id
                    elif line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line == "":
                        if event_name or data_lines:
                            raw = "\n".join(data_lines)
                            payload: dict[str, Any] | None
                            if not raw:
                                payload = None
                            else:
                                try:
                                    parsed = json.loads(raw)
                                    payload = parsed if isinstance(parsed, dict) else {"_raw": parsed}
                                except json.JSONDecodeError:
                                    payload = {"_raw": raw}
                            name = event_name or "message"
                            try:
                                await on_event(name, payload, event_id)
                            except Exception:
                                logger.exception("SSE handler failed for %s", name)
                        event_name = None
                        data_lines = []
                        event_id = None


stream_client = TimerStreamClient()
