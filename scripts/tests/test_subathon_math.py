#!/usr/bin/env python3
"""Unit tests for subathon timer math (no I/O, no network)."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.subathon_math import (  # noqa: E402
    BRT, Marathon, brt_date, derive_increment, granted_seconds_from_tip,
    humanize_seconds,
)

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


T0 = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)


def m(ends_at, *, paused=False, paused_at=None, at=T0, state="running", direction="decrease"):
    return Marathon(state=state, direction=direction, locked=False, paused=paused,
                    ends_at=ends_at, paused_at=paused_at, observed_at=at,
                    rules={"tip": {"each": 1000, "seconds": 60}})


# remaining ------------------------------------------------------------------
check("remaining = ends_at - now",
      m(T0 + timedelta(hours=10)).remaining_at(T0), 36000)
check("remaining frozen while paused",
      m(T0 + timedelta(hours=10), paused=True, paused_at=T0 - timedelta(hours=1))
      .remaining_at(T0), 39600)
check("remaining null without ends_at", m(None).remaining_at(T0), None)
check("mode ended", m(T0, state="ended").timer_mode(), "ended")
check("mode paused", m(T0, paused=True, paused_at=T0).timer_mode(), "paused")
check("mode unavailable", m(None).timer_mode(), "unavailable")

# increments -----------------------------------------------------------------
check("no movement -> none",
      derive_increment(m(T0 + timedelta(hours=5)),
                       m(T0 + timedelta(hours=5), at=T0 + timedelta(minutes=1)))["kind"],
      "none")
check("+600s while running -> grant 600",
      derive_increment(m(T0 + timedelta(hours=5)),
                       m(T0 + timedelta(hours=5, minutes=10),
                         at=T0 + timedelta(minutes=1)))["granted_seconds"],
      600)
check("backward movement -> adjustment, zero grant",
      derive_increment(m(T0 + timedelta(hours=5)),
                       m(T0 + timedelta(hours=4),
                         at=T0 + timedelta(minutes=1)))["kind"],
      "adjustment")
check("pause credit is not a grant",
      derive_increment(m(T0 + timedelta(hours=5), paused=True, paused_at=T0),
                       m(T0 + timedelta(hours=5, minutes=30),
                         at=T0 + timedelta(minutes=30)))["kind"],
      "pause_credit")
check("grant during a pause window is not mistaken for the pause credit",
      derive_increment(m(T0 + timedelta(hours=5), paused=True, paused_at=T0),
                       m(T0 + timedelta(hours=5, minutes=45),
                         at=T0 + timedelta(minutes=30)))["granted_seconds"],
      2700)
check("pause_credit_mode='always' isolates the real grant (+900 over a 30min pause)",
      derive_increment(m(T0 + timedelta(hours=5), paused=True, paused_at=T0),
                       m(T0 + timedelta(hours=5, minutes=45),
                         at=T0 + timedelta(minutes=30)),
                       pause_credit_mode="always")["granted_seconds"],
      900)
check("pause_credit_mode='off' keeps the raw movement",
      derive_increment(m(T0 + timedelta(hours=5), paused=True, paused_at=T0),
                       m(T0 + timedelta(hours=5, minutes=30),
                         at=T0 + timedelta(minutes=30)),
                       pause_credit_mode="off")["granted_seconds"],
      1800)
check("increase direction still grants +Δends_at (meiaum live feed)",
      derive_increment(m(T0, direction="increase"),
                       m(T0 + timedelta(seconds=300), at=T0 + timedelta(minutes=1),
                         direction="increase"))["granted_seconds"],
      300)

# money ----------------------------------------------------------------------
check("R$15 with 'R$10 -> 60s' grants 60s (integer floor, not 90s)",
      granted_seconds_from_tip(1500, {"tip": {"each": 1000, "seconds": 60}}), 60)
check("R$10 exactly grants 60s",
      granted_seconds_from_tip(1000, {"tip": {"each": 1000, "seconds": 60}}), 60)
check("R$105 grants 600s", granted_seconds_from_tip(10500, {"tip": {"each": 1000, "seconds": 60}}), 600)
check("below threshold grants nothing", granted_seconds_from_tip(900, {"tip": {"each": 1000, "seconds": 60}}), 0)
check("integer floor, never float", granted_seconds_from_tip(2599, {"tip": {"each": 1000, "seconds": 60}}), 120)
check("missing rule is safe", granted_seconds_from_tip(1500, {}), 0)

# misc -----------------------------------------------------------------------
check("brt_date on a UTC boundary",
      brt_date(datetime(2026, 9, 13, 1, 30, tzinfo=timezone.utc)), "2026-09-12")
check("humanize days", humanize_seconds(90000), "1d 01:00:00")
check("BRT offset", BRT.utcoffset(None), timedelta(hours=-3))

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
