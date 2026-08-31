# Contributing to Pererecos Stats

Thanks for helping. The live dashboard is [tossemideia.cloud/pererecos-stats](https://tossemideia.cloud/pererecos-stats). Product copy and UI are **pt-BR**; code, comments, and this guide are English.

## How we take changes

1. [Open an issue](https://github.com/Gugaapo/pererecos-stats/issues) for bugs or ideas (search first).
2. Fork the repo and branch from `main` (`feat/short-name` or `fix/short-name`).
3. Open a pull request against `main`. Describe what changed and how you tested it.

Small, focused PRs are easier to review than large ones. A new Ranqueada board is a good first contribution — follow [docs/adding-a-leaderboard.md](docs/adding-a-leaderboard.md). Cursor users can use the skills under `.cursor/skills/`.

Please do not commit secrets, production configs, or chat dumps. Never put `.env`, tokens, or Mongo credentials in a PR.

## Local setup

**Prerequisites:** Python 3.11+, [Docker](https://docs.docker.com/get-docker/) (for MongoDB), Git.

```bash
git clone https://github.com/YOUR_USER/pererecos-stats.git
cd pererecos-stats

docker compose up -d mongo

cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Leave `TWITCH_OAUTH_TOKEN` empty to run the API and UI without connecting to Twitch or Kick. The dashboard works against an empty database; ingest needs your own tokens, not production ones.

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- UI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/api/docs

Hard-refresh the browser after frontend changes (`/static` is served as files).

### Optional: Twitch / Kick ingest

Set tokens in `backend/.env` (see `.env.example`). EventSub timeout tracking needs `channel:moderate` and a bot account that is a moderator of `TWITCH_CHANNEL`. Kick is off until `KICK_ENABLED=true`.

## Project layout

```
backend/app/
  bot/           Twitch, Kick, EventSub listeners
  routers/       FastAPI routes (users, leaderboards, emotes, misc)
  services/
    boards/      Ranqueada registry (add boards here)
    folhinha/    FolhinhaBot parsers and boards
    common/      cache, period, Mongo helpers
  models/schemas Pydantic response models
frontend/        Vanilla JS + CSS (no bundler)
docs/            Contributor how-tos
scripts/         Tests and optional production helpers
```

## Tests

With Mongo and the API running:

```bash
API_URL=http://127.0.0.1:8000 bash scripts/tests/run_all.sh
```

After adding a board, use the smoke checklist in [docs/adding-a-leaderboard.md](docs/adding-a-leaderboard.md).

## Code notes

- Prefer the board registry over one-off gather lists.
- Usernames are stored lowercase; timestamps UTC; `hour` is Brasília (UTC−3).
- Match existing style: type hints on new Python, no extra frameworks on the frontend.
- Production deploy (`scripts/run_twitch-stats`, systemd, nginx) is operator-only. Contributors do not need it.

## Conduct

Be respectful. This is a community stats project for a Twitch/Kick chat. Harassment, slurs, or dumping other people’s messages as “samples” in issues/PRs is not OK.
