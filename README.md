# Pererecos Stats (subathon branch)

This is the **`subathon`** branch of [pererecos-stats](https://github.com/Gugaapo/pererecos-stats): a time-boxed second instance for the omeiaum subathon. It uses its own MongoDB (`twitch_stats_subathon`), listens on port **8002**, gates ingest until `SUBATHON_START`, and shows a countdown / remaining-live timer.

**Live:** [tossemideia.cloud/pererecos-stats-subathon](https://tossemideia.cloud/pererecos-stats-subathon)

The long-lived dashboard stays on [`main`](https://github.com/Gugaapo/pererecos-stats/tree/main) at [tossemideia.cloud/pererecos-stats](https://tossemideia.cloud/pererecos-stats).

![Preview](frontend/sapo.avif)

A FastAPI backend stores chat in MongoDB (TwitchIO + Kick listener + EventSub) and serves a vanilla JS UI: user profiles, Ranqueada leaderboards, Folhinha, emotes, Roda (SmokeTime), and Comparar.

## Features

- **User stats** — message counts, percentiles, hourly activity, rivals, replies, rankings, emotes, recent messages, username history
- **Ranqueada** — Top chatters, Rising Stars, Hour Leaders, Writers, Famosinhos, Duas Caras, Copycats, Pererecães, and more via a board registry
- **Folhinha** — FolhinhaBot command/reply boards (`?bonk`, cookies, dungeon, …)
- **Emotes** — 7TV rendering, rankings, weather, least-used, creators, diversity
- **Roda (SmokeTime)** — smoke session stats
- **Chat overview** — active users, 24h activity, unique chatters by hour
- **Filters** — period (1d / 7d / 30d / all / custom dates) and platform (Twitch / Kick / both)
- **Export** — CSV of chat messages; feedback endpoint; random “Ribbits” messages

## Tech stack

| Layer | Stack |
| --- | --- |
| API | FastAPI, Pydantic, SlowAPI |
| Ingest | TwitchIO, Kick websocket, Twitch EventSub |
| DB | MongoDB (Motor) |
| Frontend | Vanilla JS + CSS (no bundler) |
| Emotes | 7TV |

## Quick start

You need **Python 3.11+** and **Docker** (MongoDB). Twitch/Kick tokens are optional.

```bash
git clone -b subathon https://github.com/Gugaapo/pererecos-stats.git
cd pererecos-stats

docker compose -f docker-compose.mongo.yml up -d

cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Leave TWITCH_OAUTH_TOKEN empty to skip the bot
uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Open http://127.0.0.1:8002 — API docs at `/api/docs`. Production on this VPS uses `docker compose up` (API on 8002, host network, host Mongo).

See [CONTRIBUTING.md](CONTRIBUTING.md) for env vars, ingest, tests, and how to add a leaderboard.

## Environment

Copy `backend/.env.example` → `backend/.env`. Never commit `.env`.

| Variable | Required | Notes |
| --- | --- | --- |
| `TWITCH_OAUTH_TOKEN` | For ingest | Empty disables the Twitch bot and EventSub |
| `TWITCH_CHANNEL` | For ingest | Default `omeiaum` |
| `TWITCH_CLIENT_ID` / `SECRET` / `REFRESH_TOKEN` | EventSub / token refresh | `channel:moderate` for timeout tracking |
| `KICK_ENABLED` | No | Default `false` |
| `MONGODB_URL` | Yes | Default `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | Yes | `twitch_stats_subathon` on this branch |
| `PORT` | No | Default `8002` |
| `SUBATHON_START` | No | Ingest + countdown target (BRT) |
| `SUBATHON_PLACEHOLDER_SECONDS` | No | Remaining-live stub after start |
| `SEVENTV_EMOTE_SET_ID` | No | Channel 7TV set |
| `CORS_ORIGINS` | No | Comma-separated; local same-origin does not need it |
| `HEALTH_CHECK_TOKEN` | No | Restricts detailed `/health` |

## Production

The public site is proxied by nginx (`/pererecos-stats-subathon` + `/pererecos-stats-subathon/api/v1/` → uvicorn on `127.0.0.1:8002`). [`nginx.conf`](nginx.conf) is a **generic example** — not the live host config. [`docker-compose.yml`](docker-compose.yml) runs the API container (`network_mode: host`).

Operator helpers (`scripts/run_twitch-stats`, `bot-monitor.sh`, systemd) are for the production VPS. Contributors should use `uvicorn` locally.

## License

[MIT](LICENSE)

## Contributing

PRs and issues welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/adding-a-leaderboard.md](docs/adding-a-leaderboard.md).
