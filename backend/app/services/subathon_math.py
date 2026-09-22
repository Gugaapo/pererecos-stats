"""Pure timer math for the MeiaUm subathon marathon. No I/O — fully unit-testable.

Task 6 findings (2026-09-22, public feed https://meiaum.vinnytasso.com.br/api/v1/timer):
- Meiaum creator_id: cr_seEmDiqLyEPmhxrJLGCmvL
- Live state=running, direction=increase, locked=false, paused=false
- Display remaining = ends_at - now (confirmed: ends_at - observed_at ≈ seconds within 1s)
- Prefer ends_at for the header tick; seconds/value are cross-checks only
- direction=increase does NOT flip the display formula
- Empirically donations push ends_at forward → granted = +Δends_at (increase sign = +1;
  the prior assumed -1 convention was overturned by the live feed)
- Primary upstream for ends_at/state is the vinnytasso timer feed (no Pixie auth required)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_LOCKED = "locked"
STATE_ENDED = "ended"

DIRECTION_SIGN = {"decrease": 1, "increase": 1}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def brt_date(dt: datetime) -> str:
    """BRT calendar day key, YYYY-MM-DD (the app's display timezone)."""
    return dt.astimezone(BRT).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Marathon:
    state: str
    direction: str
    locked: bool
    paused: bool
    ends_at: datetime | None
    paused_at: datetime | None
    observed_at: datetime
    rules: dict

    @property
    def sign(self) -> int:
        return DIRECTION_SIGN.get(self.direction, 1)

    def remaining_at(self, now: datetime) -> int | None:
        """Seconds of live left. Frozen while paused (the countdown is stopped)."""
        if self.ends_at is None:
            return None
        anchor = self.paused_at if (self.paused and self.paused_at) else now
        return max(0, int((self.ends_at - anchor).total_seconds()))

    def timer_mode(self) -> str:
        if self.ends_at is None:
            return "unavailable"
        if self.state == STATE_ENDED:
            return "ended"
        if self.paused:
            return "paused"
        if self.locked:
            return "locked"
        return "running"


def derive_increment(prev: Marathon, cur: Marathon, *,
                     pause_credit_mode: str = "detect",
                     pause_tolerance: int = 60) -> dict:
    """Classify the movement of ends_at between two observations.

    Returns {"kind", "granted_seconds", "raw_delta_seconds", "pause_seconds",
             "pause_credit_seconds"}.
    kind is one of: "grant", "pause_credit", "adjustment", "none".

    `pause_credit_mode` decides how an interval that straddles a pause is treated.
    Whether Pixie pushes ends_at forward by the paused duration when a pause ends is
    NOT documented, so this is a guess until Task 25 measures it:
      "off"    -> never subtract pause time (Pixie does not credit pauses)
      "detect" -> subtract it only when the movement matches the pause window within
                  `pause_tolerance` seconds (default: refuse to guess)
      "always" -> always subtract the paused window that straddles the interval
    """
    empty = {"kind": "none", "granted_seconds": 0, "raw_delta_seconds": 0,
             "pause_seconds": 0, "pause_credit_seconds": 0}
    if prev.ends_at is None or cur.ends_at is None:
        return empty

    raw = int((cur.ends_at - prev.ends_at).total_seconds())
    if raw == 0:
        return empty

    if raw < 0:
        # Projection pulled back — a configuration change, never a contribution.
        return {**empty, "kind": "adjustment", "raw_delta_seconds": raw}

    paused_seconds = 0
    if prev.paused or cur.paused:
        paused_seconds = abs(int((cur.observed_at - prev.observed_at).total_seconds()))

    credit = 0
    if paused_seconds and pause_credit_mode != "off":
        matches = abs(raw - paused_seconds) <= pause_tolerance
        if pause_credit_mode == "always" or matches:
            credit = min(paused_seconds, raw)

    granted = (raw - credit) * cur.sign
    if credit and granted == 0:
        return {"kind": "pause_credit", "granted_seconds": 0, "raw_delta_seconds": raw,
                "pause_seconds": paused_seconds, "pause_credit_seconds": credit}
    return {"kind": "grant", "granted_seconds": granted, "raw_delta_seconds": raw,
            "pause_seconds": paused_seconds, "pause_credit_seconds": credit}


def granted_seconds_from_tip(minor_units: int, rules: dict) -> int:
    """Integer-only money -> time conversion using rules.tip."""
    tip = (rules or {}).get("tip") or {}
    each = int(tip.get("each") or 0)
    seconds = int(tip.get("seconds") or 0)
    if each <= 0 or seconds <= 0 or minor_units < each:
        return 0
    return (int(minor_units) // each) * seconds


def humanize_seconds(total: int) -> str:
    """Compact label for logs/tooltips: 3d 04:15:00 / 41:15:00."""
    total = max(0, int(total))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    hms = f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{days}d {hms}" if days else hms
