# UI redesign (v6) — screenshot-matched black / mint theme

v6 is a visual redesign of v5. No v5 behaviour was removed: every element id
and JS hook from v5 still exists, so WebSockets, location sharing, voice
notes, reactions, edit/delete, blocking, clearing, notifications, profile /
privacy editing and the appearance system all work exactly as before.

## Palette

Defined once as CSS variables at the top of `static/css/app.css`:

| Token | Dark (default) | Use |
|---|---|---|
| `--bg` | `#000000` | page / messages background |
| `--panel` | `#0d120e` | sidebar, info panel, composer |
| `--panel2` / `--panel3` | `#131a14` / `#1a231c` | inputs, icon buttons, incoming-adjacent surfaces |
| `--bubble` | `#1a231c` | incoming message bubbles |
| `--mine` | `#2e4f3e` | own message bubbles, primary buttons, avatar discs |
| `--mint` (`--link`/`--accent-text`) | `#a9f0bd` | titles, initials, accents, unread badge |
| `--muted` | sage grey | previews, status lines, timestamps |

`[data-theme="light"]` flips the same variables to a light grey-green theme
(white panels, darkened green accent for contrast). Dark stays the default;
the existing toggle switch (`#theme-toggle`, `.switch` styles kept) still
switches per-device via localStorage, applied pre-paint by `base.html`.
Everything is rounded: 14px inputs, 16px bubbles, pill buttons, circular
icon buttons. Avatar discs are dark green with a mint initial and a small
mint `.online-dot` at the bottom-right when the user is online.

## Auth screens (`templates/login.html`, `templates/register.html`)

Centred single column (same on desktop and mobile): circular dark-green
logo disc with a chat-bubble glyph, big mint title, muted subtitle.

- Login: “Log in to Chat” / “Welcome back.”, username (mint focus outline)
  and password inputs, the `.err` error pill (dark panel, ⓘ prefix;
  `.err:empty{display:none}` so it only appears when `auth.js` sets a
  message — a wrong password shows “Username or password is incorrect.”),
  pill primary “Log in”, then two small text links that expand forms
  **inline** (hidden by default): “Forgot your password?” → `#forgot-form`,
  “Didn't get the verification email? Resend” → `#resend-form`
  (toggle wiring added at the bottom of `static/js/auth.js`, guarded so it
  is a no-op on pages without those ids). A divider, then the secondary
  pill “Create new account” → `/register/`.
- Register: “Create account” / “Quick and easy.”, Username / Email /
  Password (min 8 characters), pill “Sign up”, the centred verification
  note, divider, secondary pill “I already have an account” → `/login/`.
- `reset_password.html` and `verify_email.html` stay standalone (they must
  render even if static files are broken) but their inline styles now use
  the same black / dark-green / mint palette, pill buttons and 14px inputs.

## Desktop chat — three columns (`templates/chat.html`)

**Left sidebar (~340px).** Header: bold mint “Chats”, circular icon buttons
👥 (focuses `#user-search`) and ✎ (opens the group-creation `<details>` and
focuses `#group-title`; the v5 group flow — search, check users, name,
`#new-group` — is unchanged inside it). Search pill `#user-search`
(placeholder “Search Chat”). Filter tabs All / Unread / Groups: purely
client-side, filtering the stored conversation array by `convFilter`
(`chat.js`: `allConvs` + `renderConvList()`). Rows: avatar (photo or
initials disc) wrapped with an online dot driven by the new
privacy-respecting `memberships[].is_online`, bold name, styled preview
(`convPreview()`: 🎤 Voice message, “You sent a location”, group sender
prefix, time = HH:MM today / weekday / date via `fmtConvTime()`), unread
count badge + mint dot. Footer pinned at the bottom: own avatar + username
(`#me-wrap` / `#me`, kept from v5) and a circular logout button (`#logout`).

**Middle pane.** Header: `#back-btn` (mobile only), peer avatar
(`#chat-peer-avatar`), `#chat-header` name and `#chat-status` line
(“Active now” / “Offline”, or “N members” for groups), then circular
buttons: 🔍 toggles the collapsible `#msg-search-row` (the existing
`#msg-search` input lives there), `#notif-btn` + `#notif-count` (panel
`#notif-panel` unchanged), ⓘ `#info-btn` toggles the info panel.
`#block-btn` / `#clear-btn` are kept (hidden) and stay fully functional —
the info panel's visible Block/Clear controls simply call `.click()` on
them. Messages (`renderMsgList()`): centred day dividers
(“Today 06:51”, “Yesterday …”, date), incoming bubbles in `--bubble` with a
small sender avatar at their left, own bubbles in `--mine`, compact.
Voice notes render inside a `.voice-note` strip: black circular ▶ disc,
decorative `.waveform` bars, and the native `<audio controls>` player
(which shows the real duration). Deleted own messages render as an
outlined transparent italic pill “You unsent a message” (others':
“This message was unsent”). Read receipts keep the v5 behaviour of
appending ✓✓ to the message's small line. `#typing`, `#reply-bar`,
`#rec-bar`, `#live-bar`, `#emoji-panel`, `#location-panel` are unchanged in
behaviour and restyled to the palette. Composer order: **+** (`#plus-btn`,
toggles the emoji panel), 📎 file label (`#file-input`), 📍 (`#loc-btn`),
pill input `#msg-input` (placeholder “Aa”), 😊 (`#emoji-btn`), 🎤
(`#mic-btn`), circular ➤ submit button — Enter still submits `#send-form`.

**Right info panel (~320px, `#info-panel`).** Centred large avatar with
online dot, name, status; circular Mute / Search / Block buttons with
labels; “Chat info”: Voice messages row with the count of voice-note
messages in the open conversation (click = filter the message list to
voice notes only, click again = unfilter), Media and files row with count
and chevron (same toggle-filter for attachments); “Privacy”: Block and
🗑 Clear chat rows (wired to the hidden `#block-btn` / `#clear-btn`).
Below that: `#profile-btn` (profile + privacy + password prompts, unchanged)
and the **entire v5 appearance panel** (`#appearance-panel` with
`#theme-toggle`, `#wp-presets`, `#wp-color`, `#wp-upload`, `#wp-reset`,
`#my-avatar`, `#avatar-upload`, `#avatar-remove`, `#av-colors`,
`#av-emojis`, `#av-create` — every id preserved). With no conversation
open it shows your own avatar/name + Appearance. For groups it shows the
group title, member count instead of status, and hides Block. Below
~1250px the panel is hidden and slides over when toggled (ⓘ, 🎨
`#appearance-btn`, or mobile Profile).

Presence: WebSocket `presence` events now update the stored memberships,
the list dots, the header status and the info panel — they no longer write
into `#typing` (typing events still do).

## Mobile (<760px)

The v5 single-column `body.chat-open` pattern is kept. List screen: own
avatar + “Chats” top-left, 👥/✎ top-right, search pill, tabs, a
mobile-only horizontal **active row** (`#active-row`: a “New” + circle,
then each private contact's avatar + online dot + first name; tap opens
that conversation), conversation rows, and a fixed bottom nav
(`#mobile-nav`): Chats (all), Groups (groups filter), Profile (opens the
info panel as a slide-over with profile/appearance). Chat screen: back
arrow, peer avatar/name/status, 🔍 🔔 ⓘ header icons, same composer.
≥44px touch targets, 16px inputs (no iOS auto-zoom), safe-area padding and
always-visible message actions on `hover:none` devices are carried over
from v5.

## Backend additions (v6 only)

- `chat/serializers.py` — `MemberSerializer.is_online`
  (`SerializerMethodField`): mirrors `PublicProfileSerializer` — true only
  when the member's profile is online **and** their `show_online_status`
  privacy toggle allows it (the owner always sees their own true state).
  This powers every online dot/status in the new UI.
- `chat/views.py` — `POST /api/chat/conversations/<id>/mute/` with
  `{"muted": true|false}` sets the requesting user's own membership
  `is_muted`; with no `muted` key it toggles. Returns `{"is_muted": …}`.
  Muted memberships were already excluded from server-side notifications.
  Wired in the UI to the info panel's Mute button (label becomes “Muted”).
- `chat/tests.py` — `MuteAndMemberPrivacyTests` (5 tests): mute sets and
  unsets only the caller's membership, mute toggles when `muted` is absent,
  and `is_online` is hidden when `show_online_status=False` even if the
  profile is online, shown when the toggle is on, false when offline.

## Profile & Settings pages (added on top of the redesign)

The prompt-chain profile editor and the appearance panel that used to sit
inside the info panel are **gone**. They are real pages now:

- **`/profile/`** (`templates/profile.html` + `static/js/profile.js`) —
  your avatar (large), username, email and verification status;
  **profile picture tools**: upload a photo, remove it, or create your own
  (colour + emoji / initials canvas maker, same as before); display name
  and bio with a Save button; links to Settings and Log out. Reached from
  the sidebar footer (tap your name/avatar), the info panel's Profile row,
  and the mobile bottom nav's Profile tab.
- **`/settings/`** (`templates/settings.html` + `static/js/settings.js`) —
  **Appearance**: the dark-mode toggle switch (per device, localStorage)
  and the chat-background picker (presets / custom colour / own image /
  reset; saved to the account). **Privacy**: all five toggles as proper
  switches (`/api/auth/privacy/`). **Account**: verification status +
  resend, and the change-password form (`/api/auth/change-password/`).
  Reached from the sidebar ⚙️ button and the info panel's Settings row.

The chat screen itself only *applies* the saved wallpaper now
(`initWallpaper`/`applyWallpaper` in `chat.js`); all editing happens on
the Settings page. Routes are plain TemplateViews in
`realtime_chat/urls.py`, styled by the `.page-wrap`/`.card`/`.set-row`
classes in `app.css`, so both pages follow the same theme variables
(dark/light) as everything else.

Tests: `accounts/tests.py::StandalonePagesTests` checks all five pages
render and that the chat page links to the pages instead of embedding the
old panel. Full suite: **45 tests**.
