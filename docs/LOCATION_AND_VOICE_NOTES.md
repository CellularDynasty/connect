# Location sharing & voice notes (v5)

## Voice notes 🎤

- Tap 🎤 in the composer, allow microphone access, tap 🎤 again to stop
  and send (✕ in the red recording bar cancels). Recording uses the
  browser's `MediaRecorder` (webm on Chrome/Android, mp4/m4a on Safari).
- A voice note is an ordinary attachment under the hood: it is uploaded to
  `POST /api/chat/attachments/` (audio extensions now allowed:
  mp3/wav/ogg/webm/m4a/aac, same 10 MB limit), sent with `attachment_id`,
  and downloaded through the same private download endpoint as files.
- Messages render audio attachments with an inline `<audio controls>`
  player (`Attachment.is_audio` → serializer flag → `renderAttachment`).
- Needs HTTPS or localhost for the microphone, like all browser media APIs.

## Location sharing 📍

Tap 📍 and choose:

- **Send current location** — a one-time map pin.
- **Live · 15 min / 1 hour / 8 hours** — one location message whose
  coordinates update *in place* while you move, and which **auto-expires**
  server-side. A "🔴 You are sharing live location" bar with a **Stop
  sharing** button is shown the whole time, and closing the tab stops it too.

Data: `Message.kind = "location"` with `latitude`, `longitude` and
`location_live_until` (migration `chat/0003_message_location`). Rules,
enforced identically on both transports:

- Coordinates must be valid (-90..90, -180..180), live duration must be
  15, 60 or 480 minutes — anything else is rejected.
- Only the **sender** can update/stop their live location, and only while
  it is still live; updates after expiry or stop are rejected.
- Location messages are normal messages: only conversation members can
  see them, blocking rules apply, and a location share creates a
  "📍 Shared a location" notification.

Transports:

- WebSocket: `send_message` with `"location": {"latitude": …, "longitude": …,
  "live_minutes": 15|null}`, then `location_update`
  `{"message_id": …, "latitude": …, "longitude": …}` or `{"stop": true}`;
  everyone in the chat receives `location_updated` and the pin moves live.
- REST fallback: `POST /api/chat/messages/` with `latitude`/`longitude`/
  `live_minutes`, and `POST /api/chat/messages/<id>/location/` to update
  or `{"stop": true}` to stop.

In the chat, a location renders as a card showing the pin state
("📍 Location", "🔴 Live location · until 14:30", or "Live location
ended") and opens Google Maps at the coordinates. The browser updates the
sender's position with `watchPosition`, throttled to one update every
10 seconds. Geolocation needs HTTPS or localhost (on the deployed
Render site it works; over a plain-http phone IP it may be blocked by
the browser).

Tests: `chat/tests.py::LocationAndVoiceNoteTests` — one-time location,
invalid coordinates, the full live lifecycle (update, other-member
rejection, stop, post-stop rejection), WebSocket consumer location,
and a voice note going upload → send → other user downloads the bytes.
Full suite: **28 tests**.
