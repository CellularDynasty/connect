# Appearance: dark mode, chat background & profile pictures (v5)

Open the **🎨 Appearance panel** (button next to Profile in the sidebar).

## 🌙 Dark mode toggle

- A real **toggle switch** in the panel. Dark is the default; switching to
  light flips the whole app (chat, login and register pages included).
- Implementation: every colour in `app.css` is a CSS variable; the light
  theme is a `[data-theme="light"]` block overriding the variables.
- The choice is a *device* preference: saved in the browser's
  `localStorage`, and `base.html` applies it before first paint so there
  is no dark-flash on light-mode devices.

## 🖼️ Chat background

Change what sits behind the messages in `#messages`:

- **Presets** — Ocean, Sunset, Forest and Grape gradients, a Dots pattern,
  or Default (plain theme colour).
- **Custom colour** — any colour from the colour picker.
- **Your own image** — uploaded and used as a cover background.
- **Reset** — back to default; also deletes an uploaded image.

The choice is stored on your profile (`chat_wallpaper` encodes
`preset:<key>` / `color:<#hex>` / `image`, plus a `wallpaper` image file),
so it **follows your account across devices** — unlike the theme toggle.
Your wallpaper is private: `GET /api/auth/wallpaper/` only ever serves
the *signed-in user's own* image, and the setting never appears on your
public profile.

## 👤 Profile pictures

- People now **show** pictures everywhere it matters: your header, the
  conversation list, and user search. No picture → a coloured disc with
  your initials (colour is picked from your username, so it's stable).
- **Upload a photo** — `PATCH /api/auth/profile/` with `avatar_upload`.
- **Create your own** — pick a background colour and an emoji (or no
  emoji, for your initials); the browser draws it on a `<canvas>` and
  uploads the resulting PNG as your avatar. Nothing new needed server-side.
- **Remove** — back to the initials disc (`clear_avatar`).

Serving rule (same lesson as file downloads): avatars are **not** handed
out as public `/media/` URLs — media isn't served in production. They are
served by `GET /api/auth/users/<id>/avatar/`, which needs login; the
browser passes the JWT as `?token=` because `<img>` tags can't send
headers. Any signed-in user can view avatars (they're public inside the
app); anonymous requests get 401.

Tests: `accounts/tests.py::AppearanceTests` — avatar upload → served
path → fetchable via `?token=`, anonymous 401, avatar on the public
profile, avatar clear, wallpaper round-trip, own-wallpaper privacy and
reset. Full suite: **36 tests**.
