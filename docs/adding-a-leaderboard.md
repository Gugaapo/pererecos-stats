# Adding a leaderboard

Checklist for wiring a new Pererecos Stats board end-to-end. Prefer the board registry so Pererecães, Seus Rankings, and Comparar pick it up without hand-maintained gather lists.

## 1. Backend board module

Create `backend/app/services/boards/my_board.py`:

```python
from app.services.boards.base import BoardSpec, register_board

async def fetch_my_board_top(period="all", platform="all", limit=10, start_date=None, end_date=None):
    # return list[(username, display_name, platform)]
    ...

async def rank_my_board_user(username, user_id=None, platform="twitch", period="all", start_date=None, end_date=None):
    # return (rank|None, value|None)  — optional
    ...

MY_BOARD = register_board(BoardSpec(
    id="my_board",
    label="My Board",          # shown in Pererecães breakdown
    fetch_top=fetch_my_board_top,
    rank_user=rank_my_board_user,  # or None
    rankings_fields=("my_board_rank", "my_board_count"),
    include_in_pererecoes=True,
))
```

Register the import in `backend/app/services/boards/registry.py` (and `__init__.py` if needed).

Shared helpers live under `backend/app/services/common/` (`cache`, `query`, `period`).

## 2. Schema + rankings fields

Add response models in `backend/app/models/schemas/leaderboards.py` (or the matching domain file).

If the board appears in Seus Rankings / Comparar, add fields on `UserRankings` in `schemas/user.py` and wire `rank_user` / `rankings_fields` from the registry when gathering rankings.

## 3. HTTP route

Add a thin route in `backend/app/routers/stats_leaderboards.py` that calls your `fetch_top` / board-specific response builder (same URL style as existing boards: `/api/v1/stats/...`).

## 4. Frontend (Ranqueada)

1. Add the card markup in `frontend/index.html`.
2. Export a board descriptor from `frontend/js/boards/` (or extend `frontend/js/boards/registry.js`):

```js
{
  id: 'my-board',
  listId: 'my-board-list',
  endpoint: '/stats/my-board',
  render: 'simple', // or a custom render key
}
```

`loadRanqueadaSection` iterates `RANQUEADA_BOARDS` — no edits to a hand-maintained fetch list.

## 5. Daily counters (optional)

If the board is fed by per-message counters:

1. Add `record_my_board(doc)` in `stats_aggregates.py` (or a dedicated module).
2. Append it to `INGEST_HANDLERS`.
3. Add indexes in `database.py`.
4. Add a backfill in app lifespan (`main.py`) if historical data is needed.

## Pilot reference

**Duas Caras** is the end-to-end template:

- Backend: `services/boards/duas_caras.py`
- Registry: imported via `services/boards/registry.py`
- Route: `/stats/duas-caras`
- Frontend: Ranqueada board entry + `duas-caras` render
- Pererecães: automatic via `include_in_pererecoes=True`

## Smoke-test after changes

1. Hard-refresh the frontend (CSS/JS under `/static`).
2. Open **Ranqueada** — boards load without errors.
3. Open a **user profile** (Seus Rankings).
4. Open **Comparar** with two known users.
5. Hit the new API: `GET /api/v1/stats/<your-board>?platform=all`.
6. Confirm **Pererecães** includes the new board label in breakdowns when `include_in_pererecoes` is true.
