#!/usr/bin/env python3
"""Unit tests for Pixie webhook signature verification (Standard Webhooks)."""

import base64
import hashlib
import hmac
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.subathon_webhook import SignatureError, verify  # noqa: E402

GREEN, RED, NC = "\033[0;32m", "\033[0;31m", "\033[0m"
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"{GREEN}PASS{NC} {name}")
    else:
        failed += 1
        print(f"{RED}FAIL{NC} {name}: got {got!r}, want {want!r}")


KEY = secrets.token_bytes(32)
SECRET = "whsec_" + base64.b64encode(KEY).decode()
OTHER = "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()
BODY = b'{"id":"evt_1","type":"transaction.confirmed"}'
NOW = 1789043696
EVENT_ID = "evt_01H"


def sign(body, *, secret, wid, ts):
    key = base64.b64decode(secret.replace("whsec_", "", 1))
    return base64.b64encode(
        hmac.new(key, f"{wid}.{ts}.".encode() + body, hashlib.sha256).digest()
    ).decode()


def attempt(name, *, expect_ok, secret=SECRET, wid=EVENT_ID, ts=NOW, body=BODY,
            sig=None, sig_secret=SECRET, sig_body=None):
    """sig_secret/sig_body default to the request's own values so that a case can
    deliberately sign different bytes or with a different key."""
    if sig is None:
        signed_body = body if sig_body is None else sig_body
        sig = "v1," + sign(signed_body, secret=sig_secret, wid=wid, ts=ts)
    try:
        verify(secret=secret, webhook_id=wid, webhook_timestamp=str(ts),
               webhook_signature=sig, body=body, tolerance_seconds=300, now=NOW)
        got = "accepted"
    except SignatureError:
        got = "rejected"
    check(name, got, "accepted" if expect_ok else "rejected")


attempt("valid signature accepted", expect_ok=True)
attempt("rotation: second v1 value accepted", expect_ok=True, sig="v1,AAAA v1," + sign(BODY, secret=SECRET, wid=EVENT_ID, ts=NOW))
attempt("noise + valid v1 accepted", expect_ok=True, sig="garbage v1," + sign(BODY, secret=SECRET, wid=EVENT_ID, ts=NOW))
attempt("wrong key rejected", expect_ok=False, sig_secret=OTHER)
attempt("tampered body rejected", expect_ok=False, body=BODY + b" ", sig_body=BODY)
attempt("stale timestamp rejected", expect_ok=False, ts=NOW - 3600)
attempt("future timestamp rejected", expect_ok=False, ts=NOW + 3600)
attempt("missing webhook-id rejected", expect_ok=False, wid=None)
attempt("missing timestamp rejected", expect_ok=False, ts="")
attempt("missing signature rejected", expect_ok=False, sig="")
# Deliberate tolerance: the whsec_ marker is a namespace prefix, not key material,
# so a secret pasted without it still yields the same key bytes. Rejecting it would
# silently disable the endpoint on a copy-paste slip, which is worse than accepting.
attempt("secret without the whsec_ prefix is tolerated (same key bytes)",
        expect_ok=True, secret=SECRET[6:])
attempt("malformed v1 signature rejected", expect_ok=False, sig="v1")
attempt("wrong version prefix rejected", expect_ok=False, sig="v2," + sign(BODY, secret=SECRET, wid=EVENT_ID, ts=NOW))
attempt("signature for another event id rejected", expect_ok=False,
        sig_secret=SECRET, sig="v1," + sign(BODY, secret=SECRET, wid="evt_other", ts=NOW))
attempt("empty secret rejected", expect_ok=False, secret="")
attempt("tolerance boundary (exactly 300s) accepted", expect_ok=True, ts=NOW - 300)
attempt("tolerance boundary (301s) rejected", expect_ok=False, ts=NOW - 301)

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
