#!/usr/bin/env python3
"""Standalone tests for the pure Timer-tab insight math (no pytest)."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.services.subathon_insights import (  # noqa: E402
    best_worst_hours,
    brt_hour,
    cross_check_summary,
    day_balance,
    dry_spell,
    end_projection,
    feed_cross_check,
    feed_health,
    growth_streak,
    hours_above,
    increase_histogram,
    live_vs_offline,
    milestones,
    new_crossings,
    pace_arrow,
    pace_minutes_per_hour,
    panic_rate_stats,
    ramp_buckets,
    reactive_emote_stats,
    records_update,
    single_increase_stats,
)

FAILED = 0
PASSED = 0


def check(name, got, want):
    global FAILED, PASSED
    if got == want:
        PASSED += 1
        print("PASS", name)
    else:
        FAILED += 1
        print("FAIL", name, "-> got", repr(got), "want", repr(want))


NOW = datetime(2026, 9, 22, 14, 20, tzinfo=timezone.utc)


def obs(offset_seconds, raw_delta, remaining=None):
    at = NOW + timedelta(seconds=offset_seconds)
    row = {"at": at, "raw_delta_seconds": raw_delta}
    if remaining is not None:
        row["remaining_seconds"] = remaining
    return row


# pace
check("pace basic", pace_minutes_per_hour(300, 3600), 5.0)
check("pace zero window", pace_minutes_per_hour(300, 0), None)
check("pace half window", pace_minutes_per_hour(300, 1800), 10.0)

# pace arrow
check("arrow up", pace_arrow(10.0, 5.0), "up")
check("arrow down", pace_arrow(5.0, 10.0), "down")
check("arrow flat", pace_arrow(5.1, 5.0), "flat")
check("arrow unknown", pace_arrow(None, 5.0), "unknown")
check("arrow zero baseline", pace_arrow(0.0, 0.0), "flat")

# day balance
bal = day_balance(360, 1980)
check("balance net", bal["net_seconds"], -1620)
check("balance gaining", bal["gaining"], False)
check("balance ratio", bal["ratio"], 0.1818)
check("balance zero elapsed", day_balance(60, 0)["ratio"], None)

# projection
proj = end_projection(3600, 0, 3600, NOW)
check("projection finite", proj["finite"], True)
check("projection hours", proj["hours_left"], 1.0)
check("projection eta", proj["eta"], NOW + timedelta(hours=1))
check("projection decay", proj["decay_seconds_per_hour"], 3600.0)
growing = end_projection(7200, 3600, 3600, NOW)
check("projection growing finite", growing["finite"], False)
check("projection growing eta", growing["eta"], None)
check("projection low confidence", end_projection(3600, 0, 300, NOW)["confidence"], "low")
check("projection unavailable", end_projection(None, 0, 3600, NOW)["available"], False)
check("projection no window", end_projection(3600, 0, 0, NOW)["hours_left"], 1.0)

# growth streak
live_snaps = [
    obs(-840, 0), obs(-540, 0), obs(-240, 300), obs(-120, 60), obs(-60, 0),
]
streak = growth_streak(live_snaps)
check("streak longest", streak["longest_minutes"], 2.0)
check("streak current", streak["current_minutes"], 0.0)
single = growth_streak([obs(0, 300)])
check("streak single event", single["longest_minutes"], 1.0)
gap_break = growth_streak([obs(-600, 120), obs(0, 120)])
check("streak broken by gap", gap_break["longest_minutes"], 1.0)

# hours above
# remaining 90000 is ABOVE 86400, so the zero case must use a higher threshold.
above_obs = [obs(-120, 0, 90000), obs(-60, 0, 90000), obs(0, 0, 90000)]
check("hours above zero", hours_above(above_obs, 100000), 0.0)
check("hours above counted", hours_above(above_obs, 80000), 0.033)

# histogram
hist = increase_histogram([30, 60, 61, 300, 301, 1800, 1801, 20000])
check("histogram counts", [b["count"] for b in hist], [2, 2, 2, 1, 0, 1])
check("histogram seconds", [b["seconds"] for b in hist], [90, 361, 2101, 1801, 0, 20000])
check("histogram empty", increase_histogram([])[0]["count"], 0)

# single increase stats
even = single_increase_stats([300, 60])
check("mean even", even["mean_seconds"], 180)
check("median even", even["median_seconds"], 180)
check("biggest", even["biggest_seconds"], 300)
odd = single_increase_stats([60, 120, 300])
check("median odd", odd["median_seconds"], 120)
check("stats empty", single_increase_stats([])["count"], 0)

# dry spell
spell = dry_spell(
    [NOW - timedelta(seconds=600), NOW - timedelta(seconds=480), NOW - timedelta(seconds=300)],
    NOW,
)
check("dry since", spell["since_seconds"], 300)
check("dry record", spell["record_seconds"], 180)
check("dry avg", spell["avg_gap_seconds"], 150)
check("dry count", spell["count"], 3)
check("dry downtime flag", spell["record_may_include_downtime"], False)
long_spell = dry_spell(
    [NOW - timedelta(seconds=4000), NOW - timedelta(seconds=300)], NOW
)
check("dry downtime flagged", long_spell["record_may_include_downtime"], True)
check("dry none", dry_spell([], NOW)["since_seconds"], None)

# naive MongoDB datetimes (Motor returns NAIVE UTC) — regression guards for aware()
NAIVE = datetime(2026, 9, 22, 14, 0)
check("dry spell naive times", dry_spell([NAIVE], NOW)["since_seconds"], 1200)
check("brt hour from naive", brt_hour(datetime(2026, 9, 22, 14, 30)), 11)
check(
    "cross check mixed naive/aware",
    feed_cross_check(60, NOW + timedelta(seconds=60), datetime(2026, 9, 22, 14, 20)),
    0,
)
check(
    "milestones naive tz",
    milestones(1315067, datetime(2026, 9, 22, 14, 6), [])[0]["crossed_at"].tzinfo
    is not None,
    True,
)
check(
    "records naive tz",
    records_update(None, 100, NAIVE)["max_remaining_at"].tzinfo is not None,
    True,
)
check(
    "streak naive obs",
    growth_streak([
        {"at": datetime(2026, 9, 22, 14, 16), "raw_delta_seconds": 300},
        {"at": datetime(2026, 9, 22, 14, 18), "raw_delta_seconds": 60},
    ])["longest_minutes"],
    2.0,
)

# ramp
ramp = ramp_buckets({0: 60, 23: 300})
check("ramp length", len(ramp), 24)
check("ramp first", ramp[0], {"hours_ago": 23, "granted_seconds": 300})
check("ramp last", ramp[-1], {"hours_ago": 0, "granted_seconds": 60})
check("ramp str keys", ramp_buckets({"2": 120})[21]["granted_seconds"], 120)

# best/worst hours
hours = best_worst_hours({10: 7200, 11: 60}, {10: 3600, 11: 3600}, 1800)
check("best hour", hours["best"]["hour"], 10)
check("best net", hours["best"]["net_seconds"], 3600)
check("worst hour", hours["worst"]["hour"], 11)
check("hours considered", hours["hours_considered"], 2)
check("hours guard", best_worst_hours({10: 7200}, {10: 60}, 1800)["hours_considered"], 0)
check("hours str keys", best_worst_hours({"5": 100}, {"5": 3600})["best"]["hour"], 5)

# panic
panic = panic_rate_stats(
    [{"at": NOW, "seconds": 600, "msgs": 120, "remaining_seconds": 900},
     {"at": NOW, "seconds": 300, "msgs": 30, "remaining_seconds": 1200}],
    3600, 60,
)
check("panic seconds", panic["panic_seconds"], 900)
check("panic minutes", panic["panic_minutes"], 15.0)
check("panic rate", panic["avg_msgs_per_min"], 10.0)
check("panic baseline", panic["baseline_msgs_per_min"], 1.0)
check("panic delta", panic["delta_pct"], 900.0)
check("panic top", panic["top_moments"][0]["msgs"], 120)
check("panic empty", panic_rate_stats([], 0, 0)["avg_msgs_per_min"], None)

# reactive emotes
reactive = reactive_emote_stats({"MeiaTimer": 10}, 300, {"MeiaTimer": 20}, 3600)
check("reactive lift", reactive[0]["lift"], 6.0)
check("reactive after rate", reactive[0]["after_per_min"], 2.0)
check("reactive baseline rate", reactive[0]["baseline_per_min"], 0.333)
check("reactive no baseline", reactive_emote_stats({"X": 1}, 300, {}, 3600)[0]["lift"], None)
check("reactive min filter", reactive_emote_stats({"X": 0}, 300, {}, 3600), [])
check("reactive guard", reactive_emote_stats({"X": 5}, 0, {}, 3600), [])

# cross-check
ends_at = NOW + timedelta(seconds=1315068)
observed = NOW
check("cross check clean", feed_cross_check(1315068, ends_at, observed), 0)
check("cross check drift", feed_cross_check(1315000, ends_at, observed), 68)
check("cross check missing", feed_cross_check(None, ends_at, observed), None)
summary = cross_check_summary([0, 1, 9], tolerance=5)
check("cross summary samples", summary["samples"], 3)
check("cross summary max", summary["max_delta_seconds"], 9)
check("cross summary mismatches", summary["mismatches"], 1)
check("cross summary latest", summary["latest_delta_seconds"], 9)
check("cross summary empty", cross_check_summary([])["samples"], 0)

# feed health
health = feed_health(57, 3, 300)
check("health uptime", health["uptime_pct"], 95.0)
check("health degraded", health["degraded"], True)
check("health clean", feed_health(10, 0, 60)["degraded"], False)
check("health no polls", feed_health(0, 0, 0)["uptime_pct"], None)

# live vs offline
live = live_vs_offline(
    [{"granted_seconds": 300, "status": "online"},
     {"granted_seconds": 60, "status": "offline"}]
)
check("live online", live["online_granted_seconds"], 300)
check("live offline", live["offline_granted_seconds"], 60)
check("live pct", live["online_pct"], 83.3)
check("live unknown zero", live["unknown_status_granted_seconds"], 0)
no_status = live_vs_offline([{"granted_seconds": 5}])
check("live unknown bucket", no_status["unknown_status_granted_seconds"], 5)
check("live unknown not offline", no_status["offline_granted_seconds"], 0)
check("live unknown pct", no_status["online_pct"], None)
check("live empty", live_vs_offline([])["online_pct"], None)

# milestones
first = datetime(2026, 9, 22, 14, 6, tzinfo=timezone.utc)
# 1315067s ≈ 365h → above through 350h, below 400h; extended (>500h) still hidden
boot = milestones(1315067, first, [])
check("milestones count", len(boot), 11)
check("milestone 24h above", boot[0]["above"], True)
check("milestone 24h estimated", boot[0]["estimated"], True)
check("milestone 24h crossed", boot[0]["crossed_at"], first)
check("milestone 350h above", boot[7]["label"], "350h")
check("milestone 350h above now", boot[7]["above"], True)
check("milestone 400h below", boot[8]["label"], "400h")
check("milestone 400h below now", boot[8]["above"], False)
check("milestone 400h crossed", boot[8]["crossed_at"], None)
check("milestone last is 500h", boot[-1]["label"], "500h")
unlocked = milestones(500 * 3600, first, [])
check("milestones unlocked count", len(unlocked), 19)
check("milestone unlocked last", unlocked[-1]["label"], "1000h")
check("milestone unlocked 550h", unlocked[11]["label"], "550h")
known = milestones(1315067, first, [
    {"threshold_seconds": 86400, "direction": "above", "at": first}
])
check("milestone known not estimated", known[0]["estimated"], False)
fell = milestones(80000, first, [
    {"threshold_seconds": 86400, "direction": "above", "at": first},
    {"threshold_seconds": 86400, "direction": "below", "at": NOW},
])
check("milestone fell below", fell[0]["above"], False)
check("milestone last below", fell[0]["last_below_at"], NOW)
# Once 500h was crossed, keep extended visible even if remaining fell back
stayed = milestones(400 * 3600, first, [
    {"threshold_seconds": 500 * 3600, "direction": "above", "at": first},
])
check("milestones stay unlocked after 500h", len(stayed), 19)

# new crossings
up = new_crossings(86000, 87000)
check("cross up label", up[0]["label"], "24h")
check("cross up direction", up[0]["direction"], "above")
down = new_crossings(87000, 86000)
check("cross down direction", down[0]["direction"], "below")
check("cross none", new_crossings(87000, 87500), [])
check("cross unknown", new_crossings(None, 87500), [])

# records
rec = records_update(None, 100, NOW)
check("record max", rec["max_remaining_seconds"], 100)
check("record min", rec["min_remaining_seconds"], 100)
check("record first", rec["first_observed_at"], NOW)
rec = records_update(rec, 50, NOW + timedelta(seconds=60))
check("record max held", rec["max_remaining_seconds"], 100)
check("record min updated", rec["min_remaining_seconds"], 50)
check("record observations", rec["observations_seen"], 2)
check("record noop", records_update(rec, None, NOW)["observations_seen"], 2)

print("")
print("{} passed, {} failed".format(PASSED, FAILED))
sys.exit(1 if FAILED else 0)
