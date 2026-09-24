"""Correlate Twitch/Pixie SSE events with marathon_increases using feed rules."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.database import db
from app.services.subathon_math import parse_dt

logger = logging.getLogger(__name__)

UTC = timezone.utc

TIER_KEYS = {
    "prime": "prime_sub",
    1: "tier_1_sub",
    2: "tier_2_sub",
    3: "tier_3_sub",
}


def _as_utc(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return parse_dt(dt)
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return None


def _tags(payload: dict[str, Any]) -> dict[str, Any]:
    tags = payload.get("tags")
    return tags if isinstance(tags, dict) else {}


def detect_sub_tier(payload: dict[str, Any]) -> str | int:
    tags = _tags(payload)
    plan = str(tags.get("msg-param-sub-plan") or tags.get("msg_param_sub_plan") or "").strip()
    if plan.lower() == "prime":
        return "prime"
    if plan in ("1000", "1"):
        return 1
    if plan in ("2000", "2"):
        return 2
    if plan in ("3000", "3"):
        return 3
    text = " ".join(
        str(x)
        for x in (payload.get("system_message"), payload.get("message"), payload.get("type"))
        if x
    )
    if re.search(r"\bprime\b", text, re.I):
        return "prime"
    m = re.search(r"tier\s*([123])", text, re.I)
    if m:
        return int(m.group(1))
    return 1


def detect_gift_count(payload: dict[str, Any]) -> int:
    tags = _tags(payload)
    for key in ("msg-param-mass-gift-count", "msg_param_mass_gift_count"):
        raw = tags.get(key)
        if raw is not None:
            try:
                n = int(raw)
                if n > 0:
                    return n
            except (TypeError, ValueError):
                pass
    text = str(payload.get("system_message") or "")
    m = re.search(r"gifting\s+(\d+)", text, re.I)
    if m:
        return max(1, int(m.group(1)))
    return 1


def tier_seconds(rules: dict[str, Any], tier: str | int) -> int | None:
    twitch = (rules or {}).get("twitch") or {}
    key = TIER_KEYS.get(tier) or TIER_KEYS.get(1)
    item = twitch.get(key) or {}
    try:
        secs = int(item.get("seconds"))
    except (TypeError, ValueError):
        return None
    return secs if secs > 0 else None


def cheer_seconds(rules: dict[str, Any], bits: int) -> int | None:
    twitch = (rules or {}).get("twitch") or {}
    bit = twitch.get("bit") or {}
    try:
        each = int(bit.get("each") or 0)
        secs = int(bit.get("seconds") or 0)
    except (TypeError, ValueError):
        return None
    if each <= 0 or secs <= 0 or bits <= 0:
        return None
    return (bits // each) * secs


# Product peg used by the Timer UI / MeiaCoin: R$1 = +1 minute.
# Feed tip.each=1 minor_units→60s would mean 1 centavo = 60s and never matches grants.
TIP_SECONDS_PER_REAL = 60


def extract_pixie_minor_units(payload: dict[str, Any]) -> int | None:
    """Pull BRL minor units from flat or nested Pixie webhook shapes."""
    candidates: list[Any] = [
        payload.get("amount_minor_units"),
        payload.get("amount"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        txn = data.get("transaction")
        if isinstance(txn, dict):
            amt = txn.get("amount")
            if isinstance(amt, dict):
                candidates.append(amt.get("minor_units"))
            else:
                candidates.append(amt)
            candidates.append(txn.get("amount_minor_units"))
        amt = data.get("amount")
        if isinstance(amt, dict):
            candidates.append(amt.get("minor_units"))
        else:
            candidates.append(amt)
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = raw.get("minor_units")
            if raw is None:
                continue
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n
    return None


def tip_seconds_for_match(amount_minor: int | None) -> int | None:
    """Map tip minor units → timer seconds using R$1 = 60s."""
    if amount_minor is None or amount_minor <= 0:
        return None
    return (amount_minor // 100) * TIP_SECONDS_PER_REAL


def expected_seconds(event_type: str, payload: dict[str, Any], rules: dict[str, Any]) -> int | None:
    if event_type == "twitch.cheer":
        try:
            bits = int(payload.get("bits") or 0)
        except (TypeError, ValueError):
            bits = 0
        return cheer_seconds(rules, bits)
    if event_type in ("twitch.sub", "twitch.resub", "twitch.subgift"):
        return tier_seconds(rules, detect_sub_tier(payload))
    if event_type == "twitch.submysterygift":
        per = tier_seconds(rules, detect_sub_tier(payload))
        if per is None:
            return None
        return per * detect_gift_count(payload)
    if event_type.startswith("pixie."):
        return tip_seconds_for_match(extract_pixie_minor_units(payload))
    return None


def event_label(event_type: str, payload: dict[str, Any], rules: dict[str, Any]) -> str:
    if event_type == "twitch.cheer":
        bits = payload.get("bits")
        return f"Bits ({bits})" if bits is not None else "Bits"
    if event_type in ("twitch.sub", "twitch.resub", "twitch.subgift", "twitch.submysterygift"):
        tier = detect_sub_tier(payload)
        tier_s = "Prime" if tier == "prime" else f"Tier {tier}"
        if event_type == "twitch.submysterygift":
            return f"Mystery gift ×{detect_gift_count(payload)} ({tier_s})"
        if event_type == "twitch.subgift":
            return f"Gift {tier_s}"
        if event_type == "twitch.resub":
            return f"Resub {tier_s}"
        return f"Sub {tier_s}"
    if event_type.startswith("pixie."):
        minor = extract_pixie_minor_units(payload)
        if minor is not None:
            reais = minor / 100.0
            return f"Pix R$ {reais:.2f}".replace(".", ",")
        return "Pix (Pixie)"
    return event_type


def donor_name(payload: dict[str, Any]) -> str | None:
    for key in ("display_name", "displayName", "username", "user_name", "user_login"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Nested Pixie payer / customer fields when present.
    data = payload.get("data")
    if isinstance(data, dict):
        for nest_key in ("transaction", "customer", "payer", "from"):
            nest = data.get(nest_key)
            if not isinstance(nest, dict):
                continue
            for key in (
                "display_name",
                "displayName",
                "username",
                "user_name",
                "name",
                "full_name",
            ):
                val = nest.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return None


def classify_code(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "twitch.cheer":
        return "bits"
    if event_type == "twitch.submysterygift":
        return "mystery_gift"
    if event_type == "twitch.subgift":
        return "gift"
    if event_type == "twitch.resub":
        return "resub"
    if event_type == "twitch.sub":
        tier = detect_sub_tier(payload)
        return "prime" if tier == "prime" else f"tier{tier}"
    if event_type.startswith("pixie."):
        return "pix"
    return event_type.replace(".", "_")


def event_occurred_at(payload: dict[str, Any] | None, fallback: datetime) -> datetime:
    if not payload:
        return fallback
    for key in ("occurred_at", "sent_at", "achieved_at", "observed_at"):
        dt = _as_utc(payload.get(key))
        if dt:
            return dt
    return fallback


def stable_event_key(event_type: str, payload: dict[str, Any] | None, sse_id: str | None) -> str:
    if payload:
        for key in ("event_id", "message_id", "id"):
            val = payload.get(key)
            if val is not None and str(val).strip():
                return f"{event_type}:{val}"
    if sse_id:
        return f"{event_type}:sse:{sse_id}"
    at = event_occurred_at(payload, datetime.now(UTC)).isoformat()
    return f"{event_type}:at:{at}"


async def latest_rules() -> dict[str, Any]:
    cached = await db.marathon_state.find_one({"_id": "current"})
    rules = (cached or {}).get("rules")
    return rules if isinstance(rules, dict) else {}


async def store_feed_event(
    event_type: str,
    payload: dict[str, Any] | None,
    *,
    sse_id: str | None = None,
) -> dict[str, Any] | None:
    if event_type in ("handshake",) or not event_type:
        return None
    now = datetime.now(UTC)
    body = payload if isinstance(payload, dict) else {}
    at = event_occurred_at(body, now)
    key = stable_event_key(event_type, body, sse_id)
    rules = await latest_rules()
    expected = (
        expected_seconds(event_type, body, rules)
        if event_type.startswith(("twitch.", "pixie."))
        else None
    )
    doc = {
        "key": key,
        "type": event_type,
        "sse_id": sse_id,
        "at": at,
        "received_at": now,
        "payload": body,
        "expected_seconds": expected,
        "user_name": donor_name(body),
        "label": (
            event_label(event_type, body, rules)
            if event_type.startswith(("twitch.", "pixie."))
            else event_type
        ),
        "class_code": (
            classify_code(event_type, body)
            if event_type.startswith(("twitch.", "pixie."))
            else None
        ),
    }
    await db.feed_events.update_one(
        {"key": key},
        {
            "$set": doc,
            "$setOnInsert": {"matched_increase_at": None},
        },
        upsert=True,
    )
    stored = await db.feed_events.find_one({"key": key})
    if event_type.startswith(("twitch.", "pixie.")):
        await try_match_unattributed_increases()
    return stored


async def attribute_increase(
    *,
    increase_at: datetime,
    granted_seconds: int,
    precision_seconds: int,
    increase_id: Any = None,
) -> dict[str, Any] | None:
    if granted_seconds <= 0:
        return None
    settings = get_settings()
    window = max(
        int(settings.attribution_window_seconds),
        int(precision_seconds) + 15,
        int(settings.timer_poll_seconds) + 30,
    )
    start = increase_at - timedelta(seconds=window)
    end = increase_at + timedelta(seconds=min(30, window // 2))

    cursor = db.feed_events.find(
        {
            "matched_increase_at": None,
            "expected_seconds": {"$gt": 0},
            "type": {"$regex": r"^(twitch\.|pixie\.)"},
            "at": {"$gte": start, "$lte": end},
        }
    ).sort("at", 1)
    candidates = [doc async for doc in cursor]
    if not candidates:
        return None

    exact = [
        c
        for c in candidates
        if abs(int(c.get("expected_seconds") or 0) - granted_seconds) <= 5
    ]
    if exact:
        exact.sort(key=lambda c: abs((_as_utc(c["at"]) or increase_at) - increase_at))
        chosen = [exact[0]]
    else:
        chosen = []
        total = 0
        for c in candidates:
            secs = int(c.get("expected_seconds") or 0)
            if total + secs > granted_seconds + 5:
                continue
            chosen.append(c)
            total += secs
            if abs(total - granted_seconds) <= 5:
                break
        if abs(sum(int(c.get("expected_seconds") or 0) for c in chosen) - granted_seconds) > 5:
            return None

    if not chosen:
        return None

    names = [c.get("user_name") for c in chosen if c.get("user_name")]
    labels = [c.get("label") for c in chosen if c.get("label")]
    types = [c.get("type") for c in chosen]
    keys = [c.get("key") for c in chosen]

    if len(chosen) == 1:
        label = labels[0] if labels else chosen[0].get("type")
        class_code = chosen[0].get("class_code")
        user_name = names[0] if names else None
    else:
        label = " + ".join(labels) if labels else f"{len(chosen)} eventos"
        class_code = "bundle"
        user_name = names[0] if len(set(names)) == 1 else (", ".join(names) if names else None)

    attribution = {
        "source": types[0] if len(types) == 1 else "bundle",
        "sources": types,
        "feed_event_keys": keys,
        "label": label,
        "class_code": class_code,
        "user_name": user_name,
        "attributed": True,
    }

    if increase_id is not None:
        await db.marathon_increases.update_one(
            {"_id": increase_id},
            {"$set": {"attribution": attribution}},
        )
    else:
        await db.marathon_increases.update_one(
            {"at": increase_at, "kind": "grant", "granted_seconds": granted_seconds},
            {"$set": {"attribution": attribution}},
        )
    for c in chosen:
        await db.feed_events.update_one(
            {"_id": c["_id"]},
            {"$set": {"matched_increase_at": increase_at}},
        )
    logger.info(
        "Attributed increase %ss at %s → %s (%s)",
        granted_seconds,
        increase_at.isoformat(),
        label,
        user_name,
    )
    return attribution


async def try_match_unattributed_increases(*, lookback_hours: float | None = None) -> None:
    settings = get_settings()
    if lookback_hours is None:
        window = int(settings.attribution_window_seconds)
        since = datetime.now(UTC) - timedelta(seconds=window * 2)
    else:
        since = datetime.now(UTC) - timedelta(hours=max(0.1, lookback_hours))
    cursor = db.marathon_increases.find(
        {
            "kind": "grant",
            "granted_seconds": {"$gt": 0},
            "at": {"$gte": since},
            "$or": [
                {"attribution": {"$exists": False}},
                {"attribution.attributed": {"$ne": True}},
            ],
        }
    ).sort("at", -1)
    async for inc in cursor:
        at = _as_utc(inc.get("at"))
        if at is None:
            continue
        await attribute_increase(
            increase_at=at,
            granted_seconds=int(inc.get("granted_seconds") or 0),
            precision_seconds=int(inc.get("precision_seconds") or settings.timer_poll_seconds),
            increase_id=inc.get("_id"),
        )


async def refresh_feed_event_expectations(*, rematch_hours: float = 48.0) -> int:
    """Recompute expected_seconds/labels on stored SSE events, then rematch grants."""
    from app.services.subathon_marathon import recover_missed_sse_grants

    rules = await latest_rules()
    updated = 0
    cursor = db.feed_events.find(
        {
            "type": {"$regex": r"^(twitch\.|pixie\.)"},
            "matched_increase_at": None,
        }
    )
    async for doc in cursor:
        body = doc.get("payload") if isinstance(doc.get("payload"), dict) else {}
        event_type = str(doc.get("type") or "")
        expected = expected_seconds(event_type, body, rules)
        label = event_label(event_type, body, rules)
        class_code = classify_code(event_type, body)
        user = donor_name(body)
        fields = {
            "expected_seconds": expected,
            "label": label,
            "class_code": class_code,
            "user_name": user,
        }
        if any(doc.get(k) != v for k, v in fields.items()):
            await db.feed_events.update_one({"_id": doc["_id"]}, {"$set": fields})
            updated += 1

    # Recover grants whose ends_at jump only existed on SSE (poll never saw delta).
    await recover_missed_sse_grants(lookback_hours=rematch_hours)
    await try_match_unattributed_increases(lookback_hours=rematch_hours)
    logger.info("Refreshed %s feed_events expectations; rematch lookback=%.1fh", updated, rematch_hours)
    return updated


SUB_CLASS_CODES = frozenset(
    {"prime", "tier1", "tier2", "tier3", "resub", "gift", "mystery_gift"}
)


def _origin_bucket(class_code: str | None, attributed: bool) -> str:
    if not attributed:
        return "other"
    if class_code in SUB_CLASS_CODES:
        return "subs"
    if class_code == "bits":
        return "bits"
    if class_code == "pix":
        return "pix"
    return "other"


async def attribution_stats(*, hours: int = 24, donor_limit: int = 15) -> dict[str, Any]:
    """Timer seconds by origin (attributed grants) + recent named donors."""
    hours = max(0, int(hours))
    donor_limit = max(1, min(50, int(donor_limit)))
    match: dict[str, Any] = {"kind": "grant", "granted_seconds": {"$gt": 0}}
    if hours > 0:
        match["at"] = {"$gte": datetime.now(UTC) - timedelta(hours=hours)}

    by_origin = {
        "subs": {"seconds": 0, "count": 0},
        "bits": {"seconds": 0, "count": 0},
        "pix": {"seconds": 0, "count": 0},
        "other": {"seconds": 0, "count": 0},
    }
    total = 0
    attributed_seconds = 0
    recent_donors: list[dict[str, Any]] = []

    cursor = db.marathon_increases.find(match).sort("at", -1)
    async for doc in cursor:
        secs = int(doc.get("granted_seconds") or 0)
        total += secs
        attr = doc.get("attribution") if isinstance(doc.get("attribution"), dict) else {}
        attributed = bool(attr.get("attributed"))
        code = attr.get("class_code") if attributed else None
        bucket = _origin_bucket(str(code) if code else None, attributed)
        by_origin[bucket]["seconds"] += secs
        by_origin[bucket]["count"] += 1
        if attributed:
            attributed_seconds += secs
            if len(recent_donors) < donor_limit and attr.get("user_name"):
                at = _as_utc(doc.get("at"))
                recent_donors.append(
                    {
                        "at": at.isoformat() if at else None,
                        "user_name": attr.get("user_name"),
                        "label": attr.get("label"),
                        "granted_seconds": secs,
                        "class_code": attr.get("class_code"),
                    }
                )

    return {
        "hours": hours,
        "total_granted_seconds": total,
        "attributed_seconds": attributed_seconds,
        "by_origin": by_origin,
        "recent_donors": recent_donors,
    }


async def twitch_event_counters(hours: int = 24) -> dict[str, Any]:
    """24h counters from feed_events (independent of ends_at grants)."""
    since = datetime.now(UTC) - timedelta(hours=max(1, hours))
    pipeline = [
        {
            "$match": {
                "at": {"$gte": since},
                "type": {
                    "$in": [
                        "twitch.sub",
                        "twitch.resub",
                        "twitch.subgift",
                        "twitch.submysterygift",
                        "twitch.cheer",
                    ]
                },
            }
        },
        {
            "$group": {
                "_id": "$type",
                "count": {"$sum": 1},
                "bits": {"$sum": {"$ifNull": ["$payload.bits", 0]}},
                "gift_units": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$type", "twitch.submysterygift"]},
                            {"$ifNull": ["$expected_seconds", 0]},
                            0,
                        ]
                    }
                },
            }
        },
    ]
    by_type: dict[str, dict[str, int]] = {}
    async for row in db.feed_events.aggregate(pipeline):
        by_type[str(row["_id"])] = {
            "count": int(row.get("count") or 0),
            "bits": int(row.get("bits") or 0),
        }

    subs = int((by_type.get("twitch.sub") or {}).get("count") or 0)
    resubs = int((by_type.get("twitch.resub") or {}).get("count") or 0)
    gifts = int((by_type.get("twitch.subgift") or {}).get("count") or 0)
    mystery = int((by_type.get("twitch.submysterygift") or {}).get("count") or 0)
    cheers = int((by_type.get("twitch.cheer") or {}).get("count") or 0)
    bits = int((by_type.get("twitch.cheer") or {}).get("bits") or 0)

    # Approximate mysterygift sub count from expected_seconds / tier1 seconds
    rules = await latest_rules()
    tier1 = int(((rules.get("twitch") or {}).get("tier_1_sub") or {}).get("seconds") or 60) or 60
    mystery_subs = 0
    async for doc in db.feed_events.find(
        {"at": {"$gte": since}, "type": "twitch.submysterygift"}
    ):
        exp = int(doc.get("expected_seconds") or 0)
        if exp > 0:
            mystery_subs += max(1, exp // tier1)
        else:
            mystery_subs += detect_gift_count(doc.get("payload") or {})

    return {
        "hours": hours,
        "subs": subs,
        "resubs": resubs,
        "gifts": gifts,
        "mystery_gifts": mystery,
        "mystery_gift_subs": mystery_subs,
        "cheers": cheers,
        "bits": bits,
        "sub_events_total": subs + resubs + gifts + mystery,
        "by_type": by_type,
    }
