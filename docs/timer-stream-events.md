# MeiaUm `/api/v1/timer/stream` event shapes

Source: [API da subathon](https://meiaum.vinnytasso.com.br/developers/subathon) (examples on the page) + live handshake probe 2026-09-24.

Connection: long-lived SSE. Starts with `handshake`, then `: keepalive` comments. Reconnect with `Last-Event-ID`. Limits: 10 SSE connects/min per IP — keep one connection per process.

## `handshake`

```json
{"connected": true, "connected_at": "2026-09-23T13:10:00.000Z"}
```

## `timer.updated`

```json
{
  "id": 184,
  "occurred_at": "2026-09-23T13:10:00Z",
  "previous": {
    "ends_at": "2026-10-07T21:50:12Z",
    "state": "running",
    "direction": "increase",
    "locked": false,
    "paused": false
  },
  "current": {
    "ends_at": "2026-10-07T21:51:00Z",
    "state": "running",
    "direction": "increase",
    "locked": false,
    "paused": false,
    "value": "365:15:10",
    "seconds": 1314910
  },
  "observed_at": "2026-09-23T13:10:00Z"
}
```

## `timer.record`

```json
{
  "id": 185,
  "occurred_at": "2026-09-23T13:10:00Z",
  "value": "365:15:10",
  "seconds": 1314910,
  "ends_at": "2026-10-07T21:51:00Z",
  "previous_value": "365:14:23",
  "previous_seconds": 1314863,
  "achieved_at": "2026-09-23T13:10:00Z"
}
```

## `twitch.sub` / `twitch.resub` / `twitch.subgift` / `twitch.submysterygift`

```json
{
  "id": 186,
  "occurred_at": "2026-09-23T13:11:02Z",
  "event_id": "abc123",
  "type": "sub",
  "user_id": "123456",
  "username": "usuario",
  "display_name": "Usuário",
  "message": "tamo junto!",
  "system_message": "Usuário subscribed at Tier 1.",
  "sent_at": "2026-09-23T13:11:02Z",
  "tags": {}
}
```

Tier / count are inferred from `system_message` and/or Twitch `tags` (`msg-param-sub-plan`, `msg-param-mass-gift-count`). Mystery gifts multiply tier seconds by pack size.

## `twitch.cheer`

```json
{
  "id": 190,
  "occurred_at": "2026-09-23T13:15:31Z",
  "message_id": "abc127",
  "user_id": "123456",
  "username": "usuario",
  "display_name": "Usuário",
  "bits": 100,
  "message": "Cheer100 boa live!",
  "sent_at": "2026-09-23T13:15:31Z",
  "tags": {}
}
```

## `pixie.*`

Docs example (type varies; event name is the Pixie webhook type forwarded as `pixie.<type>` or similar):

```json
{
  "occurred_at": "2026-09-23T13:16:00Z",
  "id": "txn_123",
  "type": "transaction.confirmed",
  "creator_id": "cr_seEmDiqLyEPmhxrJLGCmvL"
}
```

## Live `GET /timer` `rules` (2026-09-24)

```json
{
  "tip": {"each": 1, "unit": "minor_units", "seconds": 60, "currency": "BRL"},
  "kick": {"sub": {"unit": "subscription", "seconds": 1800}},
  "twitch": {
    "bit": {"each": 100, "unit": "bits", "seconds": 300},
    "prime_sub": {"unit": "subscription", "seconds": 30},
    "tier_1_sub": {"unit": "subscription", "seconds": 60},
    "tier_2_sub": {"unit": "subscription", "seconds": 120},
    "tier_3_sub": {"unit": "subscription", "seconds": 180}
  },
  "youtube": {
    "member": {"unit": "membership", "seconds": 60},
    "superchat": {"each": 1, "unit": "minor_units", "seconds": 60}
  }
}
```

## Live notes (2026-09-24)

Observed live `twitch.resub` + matching `timer.updated` (~0.5s later, +30s = Prime):

- Top-level fields match the docs examples (`username`, `display_name`, `system_message`, `event_id`).
- `tags` carries IRC-style keys (`msg-param-sub-plan=Prime`, `display-name`, `login`).
- Timestamps may use a space instead of `T` (`2026-09-24 14:51:19.997000+00:00`); Python `fromisoformat` accepts them.
- Quiet periods only emit `handshake` + keepalives; do not treat an idle stream as broken.
