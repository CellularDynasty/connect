# Architecture

```
Browser ── HTTP/REST (JWT) ──► Django + DRF ──► PostgreSQL
   │                              │
   └── WebSocket (JWT in query) ► Daphne / Channels ──► Redis channel layer
                                      │
                                      └─ ChatConsumer: groups = one room per conversation (chat_<id>)
```

- **REST** handles anything durable and list-shaped: auth, profiles, conversation CRUD,
  history (paginated), search, uploads, notifications, reactions, blocks.
- **WebSocket** handles anything live: send message, typing, presence, read/delivery receipts,
  edit/delete events. Messages sent over the socket are persisted by the consumer, then
  broadcast to the conversation group, so REST history and live view never diverge.
- **JWT for both**: SimpleJWT for REST (`Authorization: Bearer …`); the same access token is
  passed as `?token=` on the WebSocket handshake and verified by `chat/middleware.py`.
- **Redis channel layer** makes this scale horizontally: multiple Daphne workers share rooms
  via Redis. Locally it falls back to the in-memory layer so the project runs with zero setup.
- **Presence**: consumer sets `UserProfile.is_online` / `last_seen` on connect/disconnect and
  broadcasts a `presence` event to the room.

## WebSocket protocol
See the docstring at the top of `chat/consumers.py` — it is the contract.

## Scaling / production notes
- Run Daphne (or Uvicorn) behind Nginx, terminate TLS there, use `wss://`.
- Postgres + Redis as in `docker-compose.yml`; set a real `DJANGO_SECRET_KEY`.
- Serve media via S3 / object storage in production; validate uploads at the edge too.
- Add Celery if you later need push notifications (FCM/APNs) or thumbnail generation.
