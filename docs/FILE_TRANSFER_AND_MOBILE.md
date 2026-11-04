# File transfer fix + mobile UI (v5)

## What was actually wrong with file sharing

1. **Downloads were public `/media/` URLs — and `/media/` is not served in
   production.** `realtime_chat/urls.py` only serves media when
   `DEBUG=True`, so on Render (DEBUG=False) a file *uploaded* fine but every
   preview/download was a 404.
2. **A rejected file crashed the upload with a 500.** If the type or size
   failed validation, `AttachmentUploadView` let the `ValidationError`
   escape; the browser got an HTML error page, `r.json()` failed, and the
   user just saw "not working".
3. **Silent failures in the browser.** Picking a file with no conversation
   open, or while the WebSocket was still connecting/closed, did nothing at
   all — no message, no send.

## How it works now

- **Upload** `POST /api/chat/attachments/` (multipart, field `file`) —
  allowed types: jpg/jpeg/png/gif/webp/pdf/doc/docx/txt/zip, max 10 MB.
  Bad type/size now returns a clean `400 {"detail": "..."}`.
- **Download** `GET /api/chat/attachments/<id>/download/` — the file is
  served by the app itself, so it works with DEBUG on or off. It is also
  **private**: only the uploader or a member of the conversation the file
  was sent in can download it (everyone else gets 403, logged-out 401).
  All API responses and WebSocket broadcasts now hand out this URL instead
  of a `/media/` path. Because `<img>`/`<a>` tags cannot send the
  Authorization header, the browser appends `?token=<access JWT>` — the
  same pattern the WebSocket already used.
- **Browser flow** (`static/js/chat.js`): the file input now checks type
  and size *before* uploading and explains every failure with an alert
  (no conversation open, bad type, too big, network error). Sending uses
  the WebSocket when it is open and **falls back to the REST API**
  (`POST /api/chat/messages/` with `attachment_id`) when it is not, for
  both files and text — a dropped socket no longer eats messages.
- Old messages that stored a file as plain "Shared a file: /media/…" text
  still render as clickable links (legacy rescue in `renderBody`), and
  `/media/` is still served in DEBUG for those.

Regression tests: `chat/tests.py::FileTransferTests` (5 tests) covers
upload → send → receiver sees it → receiver downloads the exact bytes,
outsider/anonymous download denial, clean 400s for bad type and oversize,
and the WebSocket broadcast URL. Full suite: **23 tests**.

## Mobile UI

The old CSS squeezed the sidebar to 42% of a phone screen next to the
chat — both unusable. Now (see `static/css/app.css`):

- **≤760 px = single-column app pattern** (WhatsApp-style): the
  conversation list fills the screen; opening a chat switches to the
  full-screen chat (`body.chat-open`, set in `openConv`) with a **← back
  button** in the chat header to return to the list.
- Layout uses `100dvh` so the composer is not hidden behind mobile
  browser chrome; the send bar respects the iPhone safe area
  (`env(safe-area-inset-bottom)`).
- Touch targets are ≥44 px, inputs are 16 px (stops iOS auto-zoom),
  message bubbles go up to 86% width, images scale to the bubble, and
  per-message action buttons stay visible on touch devices
  (`@media (hover:none)` — there is no hover on a phone).
- Auth pages (login/register/verify) shrink their margins on small
  screens. Desktop layout is unchanged.
