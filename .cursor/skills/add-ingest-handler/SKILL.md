---
name: add-ingest-handler
description: >-
  Adds a per-message ingest handler and optional daily Mongo collection with
  indexes and lifespan backfill (INGEST_HANDLERS, record_*, backfill_*). Use when
  wiring a new *_daily counter, Famosinhos/smoke/copycats-style ingest, or
  Type A data path without necessarily adding a Ranqueada UI card yet.
---

# Add an ingest handler (+ daily collection)

Encodes the three-way sync agents often miss: **handler → indexes/db property → lifespan backfill**. For a full Ranqueada card afterward, use **`add-leaderboard`**. Do not commit unless asked.

## Before coding — collect

1. Collection name (e.g. `maria_daily`) and unique key (usually `(date, platform, user_id)`)
2. What increments the counter (scoring rules)
3. Whether historical **backfill** is required
4. BRT date bucketing? (almost always yes for daily keys)

## Checklist

### 1. Record handler

In [`backend/app/services/stats_aggregates.py`](../../../backend/app/services/stats_aggregates.py):

- Implement `record_<name>(doc: dict) -> None`
- Skip `IGNORED_BOTS` / empty payloads early
- Use **BRT** date string for `date` (see existing `BRT` / `astimezone(BRT).strftime("%Y-%m-%d")`)
- Append to `INGEST_HANDLERS` (order rarely matters; keep beside similar handlers)

Pilots: `record_famosinhos`, `record_copycats`, `record_smoke_session`, `record_folhinha`.

### 2. Database

In [`backend/app/database.py`](../../../backend/app/database.py):

- Create unique index on the natural key
- Add secondary indexes used by leaderboard `$match` (`platform+date`, `date`)
- Add `@property` on `DatabaseManager` so `getattr(db, "my_daily")` / `db.my_daily` works with `get_named_daily_leaderboard`

### 3. Backfill

- Implement `backfill_<name>()` that **skips if already populated** (count / estimated_document_count threshold like siblings)
- Prefer chronological scan + in-memory buckets for lookback logic; prefer aggregation `$group` when purely additive
- Register call in lifespan `_run_backfill()` in [`backend/app/main.py`](../../../backend/app/main.py)
- Import the backfill symbol in `main.py`

### 4. Reads (if needed now)

- Prefer [`get_named_daily_leaderboard`](../../../backend/app/services/stats_aggregates.py) for simple tops
- Cache heavy custom queries via [`services/common/cache.py`](../../../backend/app/services/common/cache.py)

## Rules of thumb

- **Never** unbounded-scan `chat_messages` on every HTTP request for lookback — do it in ingest + one-shot backfill
- Live path should be cheap (small `find` + `$inc` upsert)
- Timestamps in Mongo are UTC; **daily keys and `hour` fields are BRT-oriented** in this project
- After deploy: `sudo systemctl restart pererecos-stats.service` so lifespan backfill runs (ask approval if required)

## Smoke

1. Restart service; journal shows backfill start/skip/complete without traceback
2. Collection has documents; spot-check counts
3. If a route exists: `GET /api/v1/stats/...` returns rows
4. Send a test chat message (or wait for live) → `$inc` updates today’s bucket

## Done criteria

- [ ] `record_*` in `INGEST_HANDLERS`
- [ ] Indexes + `db` property
- [ ] Backfill + `main.py` lifespan hook
- [ ] Restart + verify population

## Next step

Wire UI/API ranks with **`add-leaderboard`** (Ranqueada) or domain-specific skills (emotes/smoke/Folhinha).
