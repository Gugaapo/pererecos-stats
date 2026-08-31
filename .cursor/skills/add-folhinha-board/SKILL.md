---
name: add-folhinha-board
description: >-
  Wires a new Folhinha tab leaderboard (bonk/abraço/roleta/cookies boards under
  /stats/folhinha/boards). Use when adding a Folhinha board, Folhinha tab rank,
  ?bonk/?abraco/?rr/?cookie ranking, FOLHINHA_BOARDS, or data-fh-board card —
  not for Ranqueada BoardSpec ranks (use add-leaderboard).
---

# Add a Folhinha tab board

Folhinha boards are **not** Ranqueada `BoardSpec`s. They query `folhinha_events` via a separate registry. Do not commit unless asked.

Related skills: `extend-folhinha-parser` (new command/reply kinds), `add-leaderboard` (Ranqueada only).

## Before coding — collect from the user

1. **Title**, **slug** (`kebab-case`, e.g. `mais-fortes`)
2. Short card note + long detail `description`
3. **Event `kind`** in `folhinha_events` (existing: `bonk`, `abraco`, `roulette_survive`, `roulette_death`, `cookie_cd`, `cookie_claim`, `cookie_balance`, `cookie_slot`) — or confirm a new kind needs the parser skill first
4. Aggregation: count by `actor_username` / `target_username`, avg `%`, cookie balance, slot delta, or custom
5. Render: `folhinha-count` vs `folhinha-pct` (stacked %)

If the events do not exist yet, stop and use **`extend-folhinha-parser`** before this skill.

## Backend checklist (must stay in sync)

All of these must include the new id:

1. [`backend/app/services/folhinha/leaderboards.py`](../../../backend/app/services/folhinha/leaderboards.py)
   - Add to `BoardId` Literal
   - Implement fetcher (reuse `_count_leaderboard`, `_avg_percentage_leaderboard`, `_cookie_balance_leaderboard`, `_slot_delta_leaderboard`, or new helper)
   - Register in `BOARD_FETCHERS`
2. [`backend/app/routers/stats_leaderboards.py`](../../../backend/app/routers/stats_leaderboards.py)
   - Append id to `FOLHINHA_TAB_BOARDS` (powers `/stats/folhinha/tab` batch + `{board_id}` allowlist)
3. Optional profile stats: [`backend/app/services/folhinha/user_stats.py`](../../../backend/app/services/folhinha/user_stats.py) if the user profile Folhinha block should show the metric
4. Optional overview/stories: [`get_folhinha_overview`](../../../backend/app/services/folhinha/leaderboards.py) + [`frontend/js/folhinha_tab.js`](../../../frontend/js/folhinha_tab.js) only if condensed KPIs/stories need the new signal

Single-board route already exists: `GET /api/v1/stats/folhinha/boards/{board_id}`.

## Frontend checklist

1. [`frontend/js/boards/folhinha.js`](../../../frontend/js/boards/folhinha.js) — append to `FOLHINHA_BOARDS`:
   - `id` / `slug`, `title`, long `description`
   - `listId` (e.g. `fh-<slug>-list`)
   - `endpoint`: `/stats/folhinha/boards/<slug>`
   - `render`: `folhinha-count` or `folhinha-pct`
   - `countKey` / `responseKey: 'leaderboard'`
2. [`frontend/index.html`](../../../frontend/index.html) — card inside `#folhinha-grid`:
   - `data-fh-board="<slug>"`
   - title button: `data-board-id="<slug>"` + `data-board-source="folhinha"`
   - short note + `.leaderboard-list` with matching `listId`

`loadFolhinhaBoards` / tab batch already iterate registries — no separate fetch list. Detail navigation reuses Ranqueada board view with `boardSource: 'folhinha'`.

## Do not confuse with

| Folhinha tab board | Ranqueada |
|--------------------|-----------|
| `FOLHINHA_BOARDS` + `BoardId` + `BOARD_FETCHERS` | `RANQUEADA_BOARDS` + `BoardSpec` |
| `/stats/folhinha/boards/<id>` | `/stats/<slug>` |
| Data: `folhinha_events` | Data: messages / `*_daily` / other |

Ranqueada’s “Abusadores do Folhinha” / commands boards are separate (`folhinha_daily` / message scan).

## Smoke

1. Restart backend only if Python changed: `sudo systemctl restart pererecos-stats.service`
2. Hard-refresh frontend
3. `GET /api/v1/stats/folhinha/boards/<slug>?period=all`
4. `GET /api/v1/stats/folhinha/tab?period=all` includes the new key under `boards`
5. Folhinha tab card fills; click-through detail shows long description

## Done criteria

- [ ] `BoardId` + `BOARD_FETCHERS` + `FOLHINHA_TAB_BOARDS`
- [ ] `FOLHINHA_BOARDS` + HTML card
- [ ] Tab batch + single board API return data
- [ ] Parser/events already produce the needed `kind` (or parser skill done first)
