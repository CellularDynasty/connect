# Real-Time Communication Platform — Django, DRF, Channels & WebSockets

A production-structured real-time messaging platform: private 1-to-1 chats, group chats with
admins, typing indicators, presence, delivery/read receipts, reactions, file sharing,
search, blocking and notifications — without page refreshes.

> **Start here for the design:** [`docs/DATABASE.md`](docs/DATABASE.md) explains every model
> and relationship before you read the code. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
> covers the real-time design. [`docs/API.md`](docs/API.md) is the endpoint cheat-sheet.

## Tech stack
Python · Django 5 · Django REST Framework · Django Channels · WebSockets · Redis ·
PostgreSQL · JWT (SimpleJWT) · Swagger/OpenAPI (drf-spectacular) · Docker · Vanilla JS frontend

## Features
- **Auth & profiles** — register/login, secure password hashing, JWT, profiles with avatar,
  bio, online/offline status and last seen
- **Private messaging** — instant delivery over WebSockets, history, edit, soft-delete,
  replies, delivery + read receipts
- **Group chats** — create groups, add/remove members (admins only), group title/description/avatar
- **Real-time** — typing indicators, presence updates, unread counters, live receipts
- **File sharing** — images with preview, documents, extension allow-list + 10 MB limit
- **Extras** — user search, message search, emoji reactions, block users, notification centre
- **In the web UI** — emoji picker, per-message react/reply/edit/delete buttons, Clear Chat
  (per-user: hides history for you only, via `ConversationMember.cleared_at`), profile editing.
  Attachments are linked to their message (`attachment_id` over the WebSocket), so files render
  as clickable downloads and images as previews on both sides, live and in history

## Quick start (zero setup — SQLite + in-memory channel layer)
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional
python manage.py runserver
# For WebSockets, runserver works via Daphne in INSTALLED_APPS. Or explicitly:
# daphne realtime_chat.asgi:application
```
Open http://127.0.0.1:8000 → register two users (use a second browser / incognito for user 2),
search for the other user, click **Chat**, and message in real time.

## Production / full stack (Postgres + Redis)
```bash
cp .env.example .env   # set DATABASE_URL and REDIS_URL
docker compose up --build
```
API docs (Swagger): http://127.0.0.1:8000/api/docs/

## Tests
```bash
python manage.py test
```

## Project structure
```
accounts/       Custom User, UserProfile, BlockedUser, JWT auth, search, blocking
chat/           Conversation, Message, Attachment, receipts, reactions,
                REST viewsets, Channels consumer, JWT websocket middleware
notifications/  Notification model + API
templates/      Login, register, chat UI
static/         CSS + JS (REST + WebSocket client)
docs/           DATABASE.md, ARCHITECTURE.md, API.md
```

## WebSocket endpoint
```
ws://127.0.0.1:8000/ws/chat/<conversation_id>/?token=<access_jwt>
```
Client events: `send_message`, `typing`, `mark_read`, `edit_message`, `delete_message`.
Server events: `chat_message`, `typing`, `presence`, `read_receipt`, `message_edited`, `message_deleted`.
