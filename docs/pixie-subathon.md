# Pixie / MeiaUm Subathon Timer

## Timer state source

Primary feed (public, no auth):

`GET https://meiaum.vinnytasso.com.br/api/v1/timer`

Docs: https://meiaum.vinnytasso.com.br/developers

Fields used: `ends_at`, `state`, `direction`, `locked`, `paused`, `observed_at`, `creator_id`.
Display remaining = `ends_at - now` (confirmed empirically). Browser never calls this URL —
a background poller (~60s) caches into Mongo (`marathon_state`) and our API serves
`GET /api/v1/subathon/timer` from cache only.

## Money (optional Pixie webhooks)

When the streamer provides a full `pxk_…` token and `whsec_…`:

1. Set `PIXIE_API_TOKEN`, `PIXIE_CREATOR_ID=cr_seEmDiqLyEPmhxrJLGCmvL`, `PIXIE_WEBHOOK_SECRET` in `backend/.env`.
2. Register in Pixie Dashboard → Webhooks:

   `https://tossemideia.cloud/pererecos-stats-subathon/api/v1/subathon/webhook/pixie`

3. Event: `transaction.confirmed`. After save, copy `whsec_…`, restart container, press **Verificar**.
4. Acceptance: Dashboard shows endpoint **Ativo**.

Watch: `docker logs -f pererecos-stats-subathon | grep -i webhook`

## nginx (host — requires sudo)

Insert **before** the generic `/pererecos-stats-subathon/api/v1/` block:

```nginx
    # Pixie webhooks: must not be rate-limited
    location = /pererecos-stats-subathon/api/v1/subathon/webhook/pixie {
        proxy_pass http://127.0.0.1:8002/api/v1/subathon/webhook/pixie;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 15;
        proxy_connect_timeout 10;
    }
```

Then: `sudo nginx -t && sudo systemctl reload nginx`

## Reconciliation

- **Time** totals come from poller `Δends_at` (`marathon_increases`).
- **Money** totals come from webhooks (`marathon_txn`) only.
- Do not add webhook granted seconds into time totals.

## Pause credit

`SUBATHON_PAUSE_CREDIT_TOLERANCE_SECONDS` (default 60). If real pauses do not move `ends_at`,
set it to `0` and treat pause_credit as unused.
