---
name: deploy-ops-restart
description: >-
  Restarts and debugs Pererecos Stats production (systemd pererecos-stats,
  nginx static path, frontend hard-refresh, bot health). Use when changes are
  not live, bot is silent, wrong static files served, restarting the API, or
  checking tossemideia.cloud/pererecos-stats deploy.
---

# Deploy / restart Pererecos Stats

Prefer **systemd** over ad-hoc scripts. Ask for approval before `systemctl restart` / `sudo` when the environment requires it. Do not commit unless asked.

## Canonical service

| Item | Value |
|------|--------|
| Unit | `pererecos-stats.service` |
| Code | `/home/gustavo-vps/apps/twitch-stats/backend` |
| Process | `uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| Public UI | `https://tossemideia.cloud/pererecos-stats` |
| API | proxied `/api/v1/` → `127.0.0.1:8000` |

```bash
sudo systemctl restart pererecos-stats.service
systemctl is-active pererecos-stats.service
sudo journalctl -u pererecos-stats.service -n 80 --no-pager
```

Restart when: Python/backend, ingest handlers, indexes, lifespan backfills, or bot code changed.

## Do **not** use for production

[`scripts/restart_server.sh`](../../../scripts/restart_server.sh) runs `pkill` + background uvicorn **outside** systemd. That fights the unit (duplicate process / Next restart overwrites). Use systemd only.

## Frontend not updating

1. Confirm which tree **live nginx** serves (`/etc/nginx/sites-enabled/`, not the repo example [`nginx.conf`](../../../nginx.conf)). Typical aliases:
   - `/pererecos-stats` → this repo's `frontend/`
   - `/static/` → this repo's `frontend/`
2. Working copy lives under **`/home/gustavo-vps/apps/twitch-stats`**. If nginx still points at an older path, sync/symlink or edit the live nginx root — otherwise edits here never appear.
3. **Hard-refresh** the browser (JS/CSS/HTML are static; no backend restart required for pure frontend).
4. API responses may be cached briefly at nginx — retry or bypass cache when verifying new endpoints.

## Backend / empty new boards after deploy

1. Restart service so lifespan backfills run
2. Watch journal for `Starting … backfill` / `already populated` / tracebacks
3. Hit `http://127.0.0.1:8000/api/v1/stats/<endpoint>?period=all` locally before blaming the UI
4. Folhinha **events** backfill is often **manual**: `python -m app.scripts.backfill_folhinha_events` (see `extend-folhinha-parser`)

## Bot / chat silent

Monitors: [`scripts/health-check.sh`](../../../scripts/health-check.sh), [`scripts/bot-monitor.sh`](../../../scripts/bot-monitor.sh) (shared flock under `/tmp/pererecos-stats-monitor.lock`).

1. `systemctl is-active pererecos-stats`
2. Journal for Twitch/Kick/EventSub errors (403 scopes, websocket unused, etc.)
3. Avoid double-restart storms (monitor cooldown files)

EventSub `channel.ban` 403 is a known scope warning — not necessarily a full outage.

## Smoke checklist

- [ ] `systemctl is-active` → active
- [ ] Local API 200 on a known route
- [ ] Public `/pererecos-stats` shows expected UI after hard-refresh
- [ ] Journal has no startup traceback; backfills finished or skipped cleanly
