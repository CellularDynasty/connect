# v5 — Email Verification & Chat Privacy

What changed from the deploy version, and how to run it.

## 1. Email verification

**Flow**

1. `POST /api/auth/register/` creates the account with `email_verified=False`
   and sends a verification email. Response includes:
   `"Account created. A verification link has been sent to your email..."`
2. The email contains a link like
   `/api/auth/verify-email/<uid>/<token>/` (valid 3 days, single-purpose:
   it is built with Django's token generator, so it also dies if the
   password or email changes). Opening it shows a small confirmation page
   and sets `email_verified=True`.
3. `POST /api/auth/login/` now refuses unverified accounts with
   `401 {"detail": "Email not verified..."}` — *after* the password check,
   so the endpoint never reveals verification status to someone who does
   not know the password.
4. `POST /api/auth/resend-verification/` `{ "email": "..." }` sends a fresh
   link if the account exists and is unverified. The response message is
   **always identical**, even for unknown emails (privacy: it cannot be
   used to check which emails are registered).

**Existing users** are not locked out: migration
`accounts/0002_email_verified_and_privacy` marks everyone who registered
*before* this feature existed as verified. Only new registrations verify.

**Email delivery**

- **Local (default):** no setup. If `EMAIL_HOST` is not set, Django's
  console backend prints the whole email — including the clickable link —
  in the terminal running `runserver`. Register, copy the link from the
  terminal, open it, then log in.
- **Production (real email):** set these environment variables:
  `EMAIL_HOST` (e.g. `smtp.gmail.com`), `EMAIL_PORT=587`,
  `EMAIL_HOST_USER` (your Gmail address), `EMAIL_HOST_PASSWORD`
  (a Gmail **App Password** — Google account → Security → 2-Step
  Verification → App passwords — *not* your normal password),
  `EMAIL_USE_TLS=True`, `DEFAULT_FROM_EMAIL` (same Gmail address).
  `render.yaml` in v5 already declares these as dashboard-filled values.

Admin: Django Admin → Users shows/filters `email_verified` and it can be
toggled by hand (useful for rescuing a test account).

## 2. Privacy in chats

Every user gets five privacy toggles on their profile
(`GET/PATCH /api/auth/privacy/`, also asked in the web UI via
Profile → privacy prompts):

| Setting | Default | Effect when off / on |
|---|---|---|
| `show_online_status` | on | Off: you always appear offline — WebSocket presence, stored profile state, and the API all agree |
| `show_last_seen` | on | Off: other users see `last_seen = null` |
| `send_read_receipts` | on | Off: your reads are recorded (your unread counts still clear) but no read-receipt event is broadcast — no blue ticks from you |
| `discoverable` | on | Off: you never appear in user search |
| `show_email` | **off** | Your email is hidden from other users (returns `null` in their API responses) unless you opt in. You and staff always see your own email |

**Blocking now actually protects you** (before, it only stopped *starting*
a new private chat):

- A block in either direction stops **new messages inside an existing
  private chat** too — REST `POST /api/chat/messages/` returns `403` and
  the WebSocket returns an error event; no message is stored.
- A user with a block relationship with you cannot be added to a group
  you create, and a group admin cannot add a user they have a block
  relationship with.

## 3. New/changed files

- `accounts/models.py` — `User.email_verified`; five privacy fields on `UserProfile`
- `accounts/migrations/0002_email_verified_and_privacy.py` — schema + grandfathering
- `accounts/emails.py` — builds & sends the verification email
- `accounts/serializers.py` — verified-only JWT login serializer, public-profile
  serializer that masks presence/last-seen, email visibility rule, privacy serializer
- `accounts/views.py` — register sends mail, verify page view, generic resend,
  privacy endpoint, search excludes non-discoverable users
- `accounts/urls.py` — `verify-email/…`, `resend-verification/`, `privacy/`, custom login
- `templates/verify_email.html` — standalone confirmation page (no static files needed)
- `templates/login.html` / `register.html`, `static/js/auth.js` — messages + resend form
- `chat/views.py`, `chat/consumers.py` — block enforcement on send (REST + WebSocket),
  presence/read-receipt privacy
- `static/js/chat.js` — Profile button now also edits the five privacy toggles
- `accounts/tests.py` — 10 new tests (verification flow + privacy); full suite: 18 tests
- `realtime_chat/settings.py` — email backend config, token timeout, `SITE_BASE_URL`
- `render.yaml` — email env vars declared for the dashboard

## 4. Run it

```bash
cd realtime_chat_platform_v5
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then: register at http://127.0.0.1:8000/register/ → copy the verification
link from the runserver terminal (the printed email) → open it → log in.
Try logging in *before* verifying to see the block. Run tests with
`python manage.py test`.
