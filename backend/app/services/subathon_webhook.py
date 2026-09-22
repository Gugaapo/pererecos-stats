"""Pixie webhook verification (Standard Webhooks, HMAC-SHA256, raw body)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Iterable


class SignatureError(Exception):
    pass


def verify(
    *,
    secret: str,
    webhook_id: str | None,
    webhook_timestamp: str | None,
    webhook_signature: str | None,
    body: bytes,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    """Raise SignatureError unless the delivery is authentic and fresh.

    The `whsec_` marker is a namespace prefix, not key material, so a secret pasted
    without it still verifies (identical key bytes). That tolerance is deliberate:
    hard-failing on it would silently disable the endpoint after a copy-paste slip.
    """
    if not secret:
        raise SignatureError("webhook secret not configured")
    if not webhook_id or not webhook_timestamp or not webhook_signature:
        raise SignatureError("missing webhook headers")
    try:
        ts = int(webhook_timestamp)
    except (TypeError, ValueError) as exc:
        raise SignatureError("bad webhook-timestamp") from exc

    current = int(time.time()) if now is None else now
    if abs(current - ts) > tolerance_seconds:
        raise SignatureError("timestamp outside tolerance")

    key = base64.b64decode(secret.replace("whsec_", "", 1))
    signed = f"{webhook_id}.{webhook_timestamp}.".encode() + body
    expected = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()
    ).decode()

    candidates: Iterable[str] = webhook_signature.split(" ")
    for value in candidates:
        version, _, encoded = value.partition(",")
        if version != "v1" or not encoded:
            continue
        if hmac.compare_digest(encoded, expected):
            return
    raise SignatureError("signature mismatch")
