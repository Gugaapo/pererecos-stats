"""Minimal Pixie.gg public-API client (one endpoint, one connection, jittered backoff)."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PixieError(Exception):
    def __init__(self, status: int, detail: str, retry_after: int | None = None):
        super().__init__(f"pixie {status}: {detail}")
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


@dataclass
class MarathonResponse:
    payload: dict[str, Any]
    fetched_at: datetime


class PixieClient:
    """Owns one keep-alive AsyncClient for the whole process."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=get_settings().pixie_base_url.rstrip("/"),
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={"Accept": "application/json"},
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_marathon(self) -> MarathonResponse:
        settings = get_settings()
        token = settings.pixie_api_token.strip()
        if not token or not settings.pixie_creator_id:
            raise PixieError(0, "pixie not configured")

        url = f"/v1/creators/{settings.pixie_creator_id}/marathon"
        headers = {"Authorization": f"Bearer {token}"}
        attempts = 4
        for attempt in range(attempts):
            try:
                resp = await (await self._http()).get(url, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == attempts - 1:
                    raise PixieError(0, f"network error: {exc}") from exc
                await asyncio.sleep(self._backoff(attempt))
                continue

            if resp.status_code == 200:
                return MarathonResponse(payload=resp.json(),
                                        fetched_at=datetime.now(timezone.utc))

            detail = ""
            try:
                detail = str(resp.json().get("detail") or "")
            except Exception:
                detail = resp.text[:200]

            # 401/403/404 are terminal: fixing them needs a human, not a retry.
            if resp.status_code in (401, 403, 404):
                raise PixieError(resp.status_code, detail)

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = self._retry_after(resp)
                if attempt == attempts - 1:
                    raise PixieError(resp.status_code, detail, retry_after)
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                logger.warning("Pixie %s, retrying in %.1fs", resp.status_code, delay)
                await asyncio.sleep(delay)
                continue

            raise PixieError(resp.status_code, detail)
        raise PixieError(0, "exhausted retries")

    @staticmethod
    def _retry_after(resp: httpx.Response) -> int | None:
        try:
            return max(1, int(resp.headers.get("Retry-After", "")))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        # exponential + full jitter, capped — Pixie asks for jittered backoff
        base = min(8.0, 0.5 * (2 ** attempt))
        return base * (0.5 + random.random() / 2)


client = PixieClient()
