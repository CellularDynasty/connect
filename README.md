# Real-Time Communication Platform — Django, DRF, Channels & WebSockets

> **Version 6** — everything from v5, plus the screenshot-matched UI redesign:
> pure-black / mint-green theme, centred pill auth screens, a 3-column chat
> layout with a right-hand info panel (mute, voice/media filters, appearance),
> filter tabs, a mobile active row + bottom nav, separate Profile and Settings
> pages, privacy-aware online dots and
> a per-conversation mute endpoint. See [`docs/UI_REDESIGN.md`](docs/UI_REDESIGN.md).
> Older versions stay untouched in their own folders.

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
- **Email verification (v5)** — new accounts must click the verification link emailed to
  them before they can log in; resend endpoint included. **Chat privacy (v5)** — toggles for
  online status, last seen, read receipts, search discoverability and email visibility, and
  blocking now stops messages in existing chats too. See
  [`docs/EMAIL_VERIFICATION_AND_PRIVACY.md`](docs/EMAIL_VERIFICATION_AND_PRIVACY.md).
  Locally, verification emails are printed in the runserver terminal (no mail setup needed)
- **Private messaging** — instant delivery over WebSockets, history, edit, soft-delete,
  replies, delivery + read receipts
- **Group chats** — create groups, add/remove members (admins only), group title/description/avatar
- **Real-time** — typing indicators, presence updates, unread counters, live receipts
- **File sharing** — images with preview, documents, extension allow-list + 10 MB limit.
  Files are downloaded through an authenticated endpoint
  (`/api/chat/attachments/<id>/download/`, members/uploader only) instead of public
  `/media/` URLs, so downloads also work in production — see
  [`docs/FILE_TRANSFER_AND_MOBILE.md`](docs/FILE_TRANSFER_AND_MOBILE.md), which also
  documents the responsive mobile layout (single-column, back button, ≥44px touch targets)
- **Extras** — user search, message search, emoji reactions, block users, notification centre
- **Appearance (v5)** — dark/light mode toggle switch, per-user chat backgrounds
  (presets, custom colour, own uploaded image — synced to your account), and profile
  pictures: upload a photo or create your own initials/emoji avatar in the browser.
  See [`docs/APPEARANCE.md`](docs/APPEARANCE.md)
- **Password reset & change (v5)** — “Forgot your password?” on the login page emails a
  one-shot set-new-password link (3-day expiry, dies once used); signed-in users can
  change their password from the Profile flow. See
  [`docs/PASSWORD_RESET.md`](docs/PASSWORD_RESET.md)
- **Location sharing & voice notes (v5)** — one-time map pins and auto-expiring live
  location (15 min / 1 hr / 8 hr, updated in place over the WebSocket), and tap-to-record
  voice notes with an inline audio player. See
  [`docs/LOCATION_AND_VOICE_NOTES.md`](docs/LOCATION_AND_VOICE_NOTES.md).
  To deploy this version over the live Render site, follow
  [`docs/GO_LIVE_V6.md`](docs/GO_LIVE_V6.md)
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
Open http://127.0.0.1:8000 → register two users (use a second browser / incognito for user 2).
Each registration prints a verification email in the runserver terminal — open its link to
verify, then log in, search for the other user, click **Chat**, and message in real time.

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
