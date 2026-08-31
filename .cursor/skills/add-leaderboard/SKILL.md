---
name: add-leaderboard
description: >-
  Wires a new Pererecos Stats Ranqueada board/rank/leaderboard end-to-end
  (BoardSpec, HTTP route, daily ingest or read-time query, frontend card,
  Seus Rankings, Comparar, Pererecães). Use when adding a rank, leaderboard,
  Ranqueada board, Famosinhos-style daily counter, Pererecães board, or when
  following docs/adding-a-leaderboard.md.
---

# Add a Ranqueada leaderboard

Read [`docs/adding-a-leaderboard.md`](../../../docs/adding-a-leaderboard.md) first, then follow this skill. Do not edit unrelated files. Do not commit unless the user asks.

## Before coding — collect from the user

If anything below is missing, ask before implementing:

1. **Title** (display name) and **slug** (`kebab-case`, used as board id and URL path)
2. **Short Ranqueada note** (card subtitle) and **long detail description** (board detail page)
3. **Type**
   - **A** — daily counter: live ingest + `*_daily` collection + backfill (lookbacks, per-message scoring)
   - **B** — read-time query/cache over existing data (totals, daily stats, one-off aggregates)
4. **`include_in_pererecoes`** — default `true`
5. **Scoring / match rules** — exact definition of what increments the count

Naming:

- Board id / frontend `id` / API path segment: `kebab-case` (e.g. `maria-vai-com-as-outras`)
- Python / Mongo / `UserRankings` fields: `snake_case` with `*_rank` and `*_count` (e.g. `maria_vai_com_as_outras_rank`)

## Choose type A vs B

| Prefer A | Prefer B |
|----------|----------|
| Needs lookback over recent messages | Derivable from `user_daily_stats`, `user_totals`, or existing collections |
| Per-message scoring at ingest time | One aggregation query is enough |
| Unbounded `chat_messages` scan on every request would be too slow | No historical backfill required beyond what data already exists |

**Never** unbounded-scan `chat_messages` on every HTTP request for lookback logic. Use type A + backfill instead.

## Type A — daily counter

Pilot: [`backend/app/services/boards/copycats.py`](../../../backend/app/services/boards/copycats.py) + `record_copycats` / `backfill_copycats` in [`stats_aggregates.py`](../../../backend/app/services/stats_aggregates.py).

1. Add `record_<board>(doc)` in [`backend/app/services/stats_aggregates.py`](../../../backend/app/services/stats_aggregates.py)
2. Append it to `INGEST_HANDLERS`
3. Add unique index `(date, platform, user_id)` (+ helpful secondary indexes) and a `@property` on `DatabaseManager` in [`backend/app/database.py`](../../../backend/app/database.py)
4. Add `backfill_<board>()` that skips if the collection is already populated; call it from the lifespan task in [`backend/app/main.py`](../../../backend/app/main.py)
5. Prefer `get_named_daily_leaderboard("<collection>")` for reads

## Type B — read-time query

Pilot: [`backend/app/services/boards/duas_caras.py`](../../../backend/app/services/boards/duas_caras.py).

1. Implement the query/service (use [`backend/app/services/common/`](../../../backend/app/services/common/) for `cache`, `period`, `query`)
2. Cache expensive paths with `get_stats_cache` / `set_stats_cache` / `stats_cache_key` (default TTL ~300s)

## Always wire (A and B)

### Backend BoardSpec

1. Create or extend a module under [`backend/app/services/boards/`](../../../backend/app/services/boards/)
2. `register_board(BoardSpec(id=..., label=..., fetch_top=..., rankings_fields=(...), include_in_pererecoes=...))`
3. Import the module in [`backend/app/services/boards/registry.py`](../../../backend/app/services/boards/registry.py) so registration runs

`fetch_top` must return `list[(username, display_name, platform)]` for Pererecães (or use `as_pererecoes_row`).

### HTTP route

Add a thin handler in [`backend/app/routers/stats_leaderboards.py`](../../../backend/app/routers/stats_leaderboards.py):

- Path: `/stats/<slug>` under the existing `/api/v1` prefix
- Reuse `NamedLeaderboardResponse` / `NamedLeaderboardEntry` when the payload is a simple ranked list

### Frontend Ranqueada

1. Card in [`frontend/index.html`](../../../frontend/index.html) inside `#ranqueada-grid`:
   - `data-board-id="<slug>"`
   - title button with `data-board-id`
   - short note
   - `.leaderboard-list` with `id` matching registry `listId`
2. Entry in [`frontend/js/boards/registry.js`](../../../frontend/js/boards/registry.js) `RANQUEADA_BOARDS`:
   - `id`, `slug`, `title`, long `description`, `listId`, `endpoint` (`/stats/<slug>`), `render` (usually `'simple'`), `countKey`, `responseKey` (usually `'leaderboard'`)

`loadRanqueadaSection` already iterates `RANQUEADA_BOARDS` — do **not** maintain a separate fetch list.

## Still manual — do not skip

`BoardSpec.rankings_fields` is metadata only. Seus Rankings and Comparar are **not** auto-wired.

1. Add fields on `UserRankings` in [`backend/app/models/schemas/user.py`](../../../backend/app/models/schemas/user.py) (`*_rank`, `*_count`, …)
2. Wire gathers in [`backend/app/services/stats_service.py`](../../../backend/app/services/stats_service.py):
   - `get_user_rankings`
   - the compare/boards helper that builds `UserRankings` for Comparar
3. Frontend [`frontend/js/app.js`](../../../frontend/js/app.js):
   - Seus Rankings: `addRank('…', rankings.<field>_rank)`
   - Comparar: metric row with `metricCell` / `betterSide` for the new fields

## Deploy and smoke

1. If ingest/backfill/indexes changed: `sudo systemctl restart pererecos-stats.service` (ask for approval if required)
2. Hard-refresh the frontend (`/static` assets)
3. Verify:
   - `GET /api/v1/stats/<slug>?platform=all`
   - Ranqueada card loads; detail page shows the long description
   - User profile Seus Rankings
   - Comparar with two known users
   - Pererecães includes the new board label when `include_in_pererecoes=True`

## Done criteria

- [ ] BoardSpec registered and imported
- [ ] HTTP route returns ranked entries
- [ ] Type A: ingest + indexes + backfill (or Type B: cached query)
- [ ] Frontend card + `RANQUEADA_BOARDS` entry
- [ ] `UserRankings` + `stats_service` + `app.js` Seus Rankings/Comparar
- [ ] Smoke checks above pass
