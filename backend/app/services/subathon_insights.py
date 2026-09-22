"""Pure insight math for the subathon Timer tab. No I/O — fully unit-testable."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.subathon_math import BRT  # reuse the shared BRT constant


def aware(dt: datetime | None) -> datetime | None:
    """Mongo/Motor returns NAIVE UTC datetimes; normalize before any arithmetic.

    `datetime.now(timezone.utc) - doc["at"]` raises TypeError on a naive value, and
    `astimezone()` on a naive value silently assumes the SERVER's local timezone, which
    would shift every BRT hour bucket. Run every Mongo datetime through this first.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)

HOUR = 3600

# Early milestones stay in hours (never convert to days).
MILESTONE_EARLY: list[tuple[str, int]] = [
    ("24h", 24 * HOUR),
    ("48h", 48 * HOUR),
    ("72h", 72 * HOUR),
]

# From 100h onward: fixed hour ladder (no day labels).
MILESTONE_BASE: list[tuple[str, int]] = [
    (f"{h}h", h * HOUR)
    for h in (100, 150, 200, 250, 350, 400, 450, 500)
]

# Same gap pattern after 500h, up to 1000h. Hidden in the UI until 500h is reached.
MILESTONE_EXTENDED: list[tuple[str, int]] = [
    (f"{h}h", h * HOUR)
    for h in (550, 600, 650, 750, 800, 850, 900, 1000)
]

MILESTONE_UNLOCK_SECONDS = 500 * HOUR

# Full set for event-sourcing (poller must detect every crossing).
MILESTONE_THRESHOLDS: list[tuple[str, int]] = (
    MILESTONE_EARLY + MILESTONE_BASE + MILESTONE_EXTENDED
)

# Accumulator for "hours spent above this threshold" (formerly labeled 7d).
HOURS_ABOVE_THRESHOLD_SECONDS = 168 * HOUR  # 168h = 7 × 24h
HOURS_ABOVE_KEY = "168h"

HISTOGRAM_EDGES: list[tuple[int | None, str]] = [
    (60, "até 1 min"),
    (300, "1-5 min"),
    (1800, "5-30 min"),
    (3600, "30 min-1h"),
    (14400, "1-4h"),
    (None, "4h+"),
]

PACE_MIN_WINDOW_SECONDS = 600
MAX_SANE_INTERVAL_SECONDS = 1800
STALE_THRESHOLD_SECONDS = 180
POLL_INTERVAL_SECONDS = 60
CROSS_CHECK_TOLERANCE_SECONDS = 5


def pace_minutes_per_hour(granted_seconds: int, window_seconds: int) -> float | None:
    """Minutes of timer gained per hour of wall clock inside the window."""
    window = int(window_seconds)
    if window <= 0:
        return None
    return round(int(granted_seconds) * 60 / window, 2)


def pace_arrow(current: float | None, baseline: float | None, dead_zone: float = 0.05) -> str:
    if current is None or baseline is None:
        return "unknown"
    if baseline <= 0:
        return "up" if current > 0 else "flat"
    if current > baseline * (1 + dead_zone):
        return "up"
    if current < baseline * (1 - dead_zone):
        return "down"
    return "flat"


def day_balance(granted_seconds: int, elapsed_seconds: int) -> dict:
    granted = max(0, int(granted_seconds))
    elapsed = max(0, int(elapsed_seconds))
    net = granted - elapsed
    ratio = round(granted / elapsed, 4) if elapsed else None
    return {
        "granted_seconds": granted,
        "elapsed_seconds": elapsed,
        "net_seconds": net,
        "ratio": ratio,
        "gaining": net >= 0,
    }


def end_projection(
    remaining_seconds: int | None,
    window_granted_seconds: int,
    window_seconds: int,
    now: datetime,
) -> dict:
    """Projected end at the pace of the window. Growing timer => finite is False."""
    now = aware(now)
    if remaining_seconds is None:
        return {
            "available": False, "finite": None, "hours_left": None, "eta": None,
            "naive_eta": None, "decay_seconds_per_hour": None, "confidence": "none",
        }
    remaining = max(0, int(remaining_seconds))
    naive_eta = now + timedelta(seconds=remaining)
    window = int(window_seconds)
    if window <= 0:
        return {
            "available": True, "finite": True, "hours_left": round(remaining / 3600, 2),
            "eta": naive_eta, "naive_eta": naive_eta,
            "decay_seconds_per_hour": 3600.0, "confidence": "low",
        }
    confidence = "ok" if window >= PACE_MIN_WINDOW_SECONDS else "low"
    granted_per_hour = int(window_granted_seconds) * 3600 / window
    decay = 3600 - granted_per_hour
    if decay <= 0:
        return {
            "available": True, "finite": False, "hours_left": None, "eta": None,
            "naive_eta": naive_eta, "decay_seconds_per_hour": 0.0, "confidence": confidence,
        }
    hours_left = remaining / decay
    return {
        "available": True, "finite": True, "hours_left": round(hours_left, 2),
        "eta": now + timedelta(hours=hours_left), "naive_eta": naive_eta,
        "decay_seconds_per_hour": round(decay, 2), "confidence": confidence,
    }


def growth_streak(
    observations: list[dict],
    max_gap_seconds: int = 180,
    cadence_seconds: int = POLL_INTERVAL_SECONDS,
) -> dict:
    """Longest/current run of consecutive snapshots moving ends_at forward."""
    pts = []
    for o in observations:
        if o.get("at") is None:
            continue
        row = dict(o)
        row["at"] = aware(row["at"])
        pts.append(row)
    pts.sort(key=lambda o: o["at"])
    best = 0.0
    current = 0.0
    run_start: datetime | None = None
    prev_at: datetime | None = None
    for o in pts:
        at = o["at"]
        positive = int(o.get("raw_delta_seconds") or 0) > 0
        gap = int((at - prev_at).total_seconds()) if prev_at is not None else None
        if positive:
            if run_start is None or (gap is not None and gap > max_gap_seconds):
                run_start = at
            run = (at - run_start).total_seconds() or cadence_seconds
        else:
            run_start = None
            run = 0.0
        best = max(best, run)
        current = run
        prev_at = at
    return {
        "longest_minutes": round(best / 60, 1),
        "current_minutes": round(current / 60, 1),
    }


def hours_above(
    observations: list[dict],
    threshold_seconds: int,
    max_gap_seconds: int = 300,
) -> float:
    """Live hours spent with remaining >= threshold (capped gaps)."""
    pts = []
    for o in observations:
        if o.get("at") is None:
            continue
        row = dict(o)
        row["at"] = aware(row["at"])
        pts.append(row)
    pts.sort(key=lambda o: o["at"])
    total = 0.0
    prev = None
    for cur in pts:
        if prev is not None:
            remaining = prev.get("remaining_seconds")
            if remaining is not None and int(remaining) >= int(threshold_seconds):
                gap = int((cur["at"] - prev["at"]).total_seconds())
                total += min(max(gap, 0), max_gap_seconds)
        prev = cur
    return round(total / 3600, 3)


def increase_histogram(values: list[int]) -> list[dict]:
    vals = [max(0, int(v or 0)) for v in values]
    buckets = []
    for edge, label in HISTOGRAM_EDGES:
        if edge is None:
            picked = [v for v in vals if v > HISTOGRAM_EDGES[-2][0]]
        else:
            picked = [v for v in vals if v <= edge]
            vals = [v for v in vals if v > edge]
        buckets.append(
            {"label": label, "count": len(picked), "seconds": int(sum(picked))}
        )
    return buckets


def single_increase_stats(values: list[int]) -> dict:
    vals = sorted(max(0, int(v or 0)) for v in values)
    n = len(vals)
    if not n:
        return {
            "count": 0, "total_seconds": 0, "mean_seconds": 0,
            "median_seconds": 0, "biggest_seconds": 0,
        }
    total = sum(vals)
    mid = n // 2
    median = vals[mid] if n % 2 else int((vals[mid - 1] + vals[mid]) // 2)
    return {
        "count": n,
        "total_seconds": total,
        "mean_seconds": int(total // n),
        "median_seconds": median,
        "biggest_seconds": vals[-1],
    }


def dry_spell(
    times: list[datetime],
    now: datetime,
    max_sane_gap_seconds: int = MAX_SANE_INTERVAL_SECONDS,
) -> dict:
    now = aware(now)
    ts = sorted(t for t in (aware(t) for t in times) if t is not None)
    if not ts:
        return {
            "since_seconds": None, "since_at": None, "record_seconds": 0,
            "record_at": None, "record_may_include_downtime": False,
            "avg_gap_seconds": None, "count": 0,
        }
    gaps = [
        (int((ts[i + 1] - ts[i]).total_seconds()), ts[i + 1]) for i in range(len(ts) - 1)
    ]
    record_seconds, record_at = (0, None)
    for seconds, at in gaps:
        if seconds > record_seconds:
            record_seconds, record_at = seconds, at
    return {
        "since_seconds": max(0, int((now - ts[-1]).total_seconds())),
        "since_at": ts[-1],
        "record_seconds": record_seconds,
        "record_at": record_at,
        "record_may_include_downtime": record_seconds > max_sane_gap_seconds,
        "avg_gap_seconds": (
            int(sum(g for g, _ in gaps) // len(gaps)) if gaps else None
        ),
        "count": len(ts),
    }


def ramp_buckets(values_by_hours_ago: dict, hours: int = 24) -> list[dict]:
    norm = {int(k): max(0, int(v or 0)) for k, v in (values_by_hours_ago or {}).items()}
    return [
        {"hours_ago": h, "granted_seconds": norm.get(h, 0)}
        for h in range(int(hours) - 1, -1, -1)
    ]


def best_worst_hours(
    granted_by_hour: dict,
    elapsed_by_hour: dict,
    min_elapsed_seconds: int = 1800,
) -> dict:
    granted = {int(k): max(0, int(v or 0)) for k, v in (granted_by_hour or {}).items()}
    elapsed = {int(k): max(0, int(v or 0)) for k, v in (elapsed_by_hour or {}).items()}
    rows = []
    for hour in range(24):
        observed = elapsed.get(hour, 0)
        if observed < int(min_elapsed_seconds):
            continue
        rows.append({
            "hour": hour,
            "granted_seconds": granted.get(hour, 0),
            "elapsed_seconds": observed,
            "net_seconds": granted.get(hour, 0) - observed,
        })
    if not rows:
        return {
            "best": None, "worst": None, "hours_considered": 0,
            "min_elapsed_seconds": int(min_elapsed_seconds),
        }
    rows.sort(key=lambda r: r["net_seconds"])
    return {
        "best": rows[-1],
        "worst": rows[0],
        "hours_considered": len(rows),
        "min_elapsed_seconds": int(min_elapsed_seconds),
    }


def panic_rate_stats(
    windows: list[dict],
    baseline_seconds: int,
    baseline_msgs: int,
) -> dict:
    """windows: [{'at': dt, 'seconds': int, 'msgs': int, 'remaining_seconds': int}]"""
    panic_seconds = sum(max(0, int(w.get("seconds") or 0)) for w in windows)
    panic_msgs = sum(max(0, int(w.get("msgs") or 0)) for w in windows)
    rate = round(panic_msgs / (panic_seconds / 60), 2) if panic_seconds else None
    base = (
        round(int(baseline_msgs) / (int(baseline_seconds) / 60), 2)
        if int(baseline_seconds or 0) > 0
        else None
    )
    delta = round((rate - base) / base * 100, 1) if rate is not None and base else None
    top = []
    for w in sorted(windows, key=lambda w: int(w.get("msgs") or 0), reverse=True)[:3]:
        row = dict(w)
        row["at"] = aware(row.get("at"))
        top.append(row)
    return {
        "panic_seconds": panic_seconds,
        "panic_minutes": round(panic_seconds / 60, 1),
        "panic_msgs": panic_msgs,
        "avg_msgs_per_min": rate,
        "baseline_msgs_per_min": base,
        "delta_pct": delta,
        "top_moments": top,
    }


def reactive_emote_stats(
    after_counts: dict,
    after_seconds: int,
    baseline_counts: dict,
    baseline_seconds: int,
    min_after: int = 1,
    limit: int = 5,
) -> list[dict]:
    """Emotes whose per-minute rate rises after an increase vs. the baseline."""
    after_window = int(after_seconds or 0)
    base_window = int(baseline_seconds or 0)
    if after_window <= 0 or base_window <= 0:
        return []
    rows = []
    for name, count in (after_counts or {}).items():
        hits = int(count or 0)
        if hits < int(min_after):
            continue
        after_rate = hits / (after_window / 60)
        base_hits = int((baseline_counts or {}).get(name, 0) or 0)
        base_rate = base_hits / (base_window / 60)
        lift = round(after_rate / base_rate, 2) if base_rate > 0 else None
        rows.append({
            "emote_name": name,
            "after_count": hits,
            "after_per_min": round(after_rate, 3),
            "baseline_per_min": round(base_rate, 3),
            "lift": lift,
        })
    rows.sort(
        key=lambda r: (
            r["lift"] is not None,
            r["lift"] if r["lift"] is not None else 0.0,
            r["after_count"],
        ),
        reverse=True,
    )
    return rows[: int(limit)]


def feed_cross_check(
    feed_seconds: int | None,
    ends_at: datetime | None,
    observed_at: datetime | None,
) -> int | None:
    if feed_seconds is None or ends_at is None or observed_at is None:
        return None
    return abs(
        int(feed_seconds) - int((aware(ends_at) - aware(observed_at)).total_seconds())
    )


def cross_check_summary(deltas: list[int], tolerance: int = CROSS_CHECK_TOLERANCE_SECONDS) -> dict:
    vals = [abs(int(d)) for d in deltas if d is not None]
    if not vals:
        return {
            "samples": 0, "latest_delta_seconds": None, "max_delta_seconds": None,
            "mismatches": 0, "tolerance_seconds": int(tolerance),
        }
    return {
        "samples": len(vals),
        "latest_delta_seconds": vals[-1],
        "max_delta_seconds": max(vals),
        "mismatches": len([v for v in vals if v > int(tolerance)]),
        "tolerance_seconds": int(tolerance),
    }


def feed_health(
    polls_ok: int,
    polls_fail: int,
    max_gap_seconds: int,
    stale_threshold_seconds: int = STALE_THRESHOLD_SECONDS,
) -> dict:
    ok = max(0, int(polls_ok or 0))
    fail = max(0, int(polls_fail or 0))
    total = ok + fail
    return {
        "polls_ok": ok,
        "polls_fail": fail,
        "total_polls": total,
        "uptime_pct": round(100 * ok / total, 2) if total else None,
        "max_gap_seconds": max(0, int(max_gap_seconds or 0)),
        "stale_threshold_seconds": int(stale_threshold_seconds),
        "degraded": max(0, int(max_gap_seconds or 0)) > int(stale_threshold_seconds),
    }


def live_vs_offline(increases: list[dict]) -> dict:
    """Granted seconds by the feed's `status` at the time of the increase.

    Rows without a recorded status (any increase captured before the poller started
    persisting it) go into a separate bucket — never silently counted as "offline", which
    would render a misleading 0% online on day 1.
    """
    online = offline = unknown = 0
    for item in increases or []:
        granted = max(0, int(item.get("granted_seconds") or 0))
        status = str(item.get("status") or "").strip().lower()
        if status == "online":
            online += granted
        elif status:
            offline += granted
        else:
            unknown += granted
    known = online + offline
    return {
        "online_granted_seconds": online,
        "offline_granted_seconds": offline,
        "unknown_status_granted_seconds": unknown,
        "online_pct": round(100 * online / known, 1) if known else None,
    }


def milestones(
    remaining_seconds: int | None,
    first_observed_at: datetime | None,
    crossings: list[dict],
    max_remaining_seconds: int | None = None,
) -> list[dict]:
    """Bootstrap-aware milestone list. estimated=True means "at least since then".

    Thresholds above 500h stay hidden until the timer has reached 500h (now or ever),
    so the card stays compact early on.
    """
    by_threshold: dict[int, dict] = {}
    for row in crossings or []:
        by_threshold.setdefault(int(row["threshold_seconds"]), {})[
            str(row.get("direction"))
        ] = row

    rem = int(remaining_seconds) if remaining_seconds is not None else None
    max_rem = int(max_remaining_seconds) if max_remaining_seconds is not None else None
    unlocked_extended = (
        (rem is not None and rem >= MILESTONE_UNLOCK_SECONDS)
        or (max_rem is not None and max_rem >= MILESTONE_UNLOCK_SECONDS)
        or any(
            int(row.get("threshold_seconds") or 0) >= MILESTONE_UNLOCK_SECONDS
            and str(row.get("direction")) == "above"
            for row in (crossings or [])
        )
    )
    visible = MILESTONE_EARLY + MILESTONE_BASE + (
        MILESTONE_EXTENDED if unlocked_extended else []
    )

    out = []
    for label, threshold in visible:
        rec = by_threshold.get(threshold, {})
        above_event = rec.get("above")
        above_now = rem is not None and rem >= threshold
        out.append({
            "key": label,
            "label": label,
            "threshold_seconds": threshold,
            "above": bool(above_now),
            "crossed_at": aware(above_event.get("at")) if above_event else (
                aware(first_observed_at) if above_now else None
            ),
            "estimated": bool(above_now and not above_event),
            "last_below_at": aware((rec.get("below") or {}).get("at")),
        })
    return out


def new_crossings(prev_remaining: int | None, cur_remaining: int | None) -> list[dict]:
    """Threshold crossings between two observations, for event-sourcing."""
    if prev_remaining is None or cur_remaining is None:
        return []
    prev_r = int(prev_remaining)
    cur_r = int(cur_remaining)
    out = []
    for label, threshold in MILESTONE_THRESHOLDS:
        if prev_r < threshold <= cur_r:
            out.append({
                "label": label, "threshold_seconds": threshold,
                "direction": "above", "remaining_at_event": cur_r,
            })
        elif cur_r < threshold <= prev_r:
            out.append({
                "label": label, "threshold_seconds": threshold,
                "direction": "below", "remaining_at_event": cur_r,
            })
    return out


def records_update(
    records: dict | None,
    remaining_seconds: int | None,
    at: datetime | None,
) -> dict:
    """O(1) all-time high/low bookkeeping (survives the 90d snapshot TTL)."""
    rec = dict(records or {})
    at = aware(at)
    if remaining_seconds is None or at is None:
        return rec
    remaining = int(remaining_seconds)
    if rec.get("max_remaining_seconds") is None or remaining > int(rec["max_remaining_seconds"]):
        rec["max_remaining_seconds"] = remaining
        rec["max_remaining_at"] = at
    if rec.get("min_remaining_seconds") is None or remaining < int(rec["min_remaining_seconds"]):
        rec["min_remaining_seconds"] = remaining
        rec["min_remaining_at"] = at
    if rec.get("first_observed_at") is None:
        rec["first_observed_at"] = at
    rec["observations_seen"] = int(rec.get("observations_seen") or 0) + 1
    return rec


def brt_hour(dt: datetime) -> int:
    """BRT hour-of-day. Naive input is treated as UTC, never as server-local time."""
    return aware(dt).astimezone(BRT).hour
