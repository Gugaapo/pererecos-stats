"""MeiaUm public timer feed client (vinnytasso /api/v1/timer).

Primary source for ends_at / state. No auth. Do not call from request handlers —
the poller owns the upstream budget.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.services.subathon_math import Marathon, parse_dt

logger = logging.getLogger(__name__)

USER_AGENT = "pererecos-stats-subathon/1.0 (+https://tossemideia.cloud/pererecos-stats-subathon)"


class TimerFeedError(Exception):
    def __init__(self, status: int, detail: str, retry_after: int | None = None):
        super().__init__(f"timer feed {status}: {detail}")
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


@dataclass
class TimerFeedResponse:
    marathon: Marathon
    payload: dict[str, Any]
    fetched_at: datetime
    status: str | None = None
    feed_seconds: int | None = None
    feed_value: str | None = None


class TimerClient:
    """Owns one keep-alive AsyncClient for the whole process."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_timer(self) -> TimerFeedResponse:
        settings = get_settings()
        url = settings.timer_feed_url.strip()
        if not url:
            raise TimerFeedError(0, "timer feed not configured")

        attempts = 4
        for attempt in range(attempts):
            try:
                resp = await (await self._http()).get(url)
            except httpx.HTTPError as exc:
                if attempt == attempts - 1:
                    raise TimerFeedError(0, f"network error: {exc}") from exc
                await asyncio.sleep(self._backoff(attempt))
                continue

            if resp.status_code == 200:
                payload = resp.json()
                fetched_at = datetime.now(timezone.utc)
                observed = parse_dt(payload.get("observed_at")) or fetched_at
                rules_raw = payload.get("rules")
                rules = rules_raw if isinstance(rules_raw, dict) else {}
                marathon = Marathon(
                    state=str(payload.get("state") or "unavailable"),
                    direction=str(payload.get("direction") or "decrease"),
                    locked=bool(payload.get("locked")),
                    paused=bool(payload.get("paused")),
                    ends_at=parse_dt(payload.get("ends_at")),
                    paused_at=parse_dt(payload.get("paused_at")),
                    observed_at=observed,
                    rules=rules,
                )
                feed_seconds_raw = payload.get("seconds")
                try:
                    feed_seconds = (
                        int(feed_seconds_raw) if feed_seconds_raw is not None else None
                    )
                except (TypeError, ValueError):
                    feed_seconds = None
                feed_value = payload.get("value")
                status = payload.get("status")
                return TimerFeedResponse(
                    marathon=marathon,
                    payload=payload,
                    fetched_at=fetched_at,
                    status=str(status) if status is not None else None,
                    feed_seconds=feed_seconds,
                    feed_value=str(feed_value) if feed_value is not None else None,
                )

            detail = ""
            try:
                detail = str(resp.json().get("detail") or resp.text[:200])
            except Exception:
                detail = resp.text[:200]

            if resp.status_code in (401, 403, 404):
                raise TimerFeedError(resp.status_code, detail)

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = self._retry_after(resp)
                if attempt == attempts - 1:
                    raise TimerFeedError(resp.status_code, detail, retry_after)
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                logger.warning("Timer feed %s, retrying in %.1fs", resp.status_code, delay)
                await asyncio.sleep(delay)
                continue

            raise TimerFeedError(resp.status_code, detail)
        raise TimerFeedError(0, "exhausted retries")

    @staticmethod
    def _retry_after(resp: httpx.Response) -> int | None:
        try:
            return max(1, int(resp.headers.get("Retry-After", "")))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        base = min(8.0, 0.5 * (2 ** attempt))
        return base * (0.5 + random.random() / 2)


client = TimerClient()
