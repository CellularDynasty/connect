# Forgot password & change password (v5)

## If you FORGOT your password (logged out)

1. On the **login page**, use the **“Forgot your password?”** form: enter
   your registered email and submit.
2. You get an email with a reset link (locally, the email is printed in the
   runserver terminal; in production it is really sent — same email setup
   as verification).
3. Open the link → a page asks for a **new password twice** → submit.
4. Log in with the new password.

Rules behind it:

- `POST /api/auth/password-reset/` always answers with the same generic
  message, whether or not the email is registered — nobody can use it to
  check which emails have accounts.
- The link (`GET/POST /api/auth/password-reset/<uidb64>/<token>/`) uses
  Django's built-in token generator — the same one email verification
  uses. The token is signed from your password hash, so it **expires
  after 3 days** and **stops working the moment the password changes** —
  it cannot be reused, and no reset-token table is stored.
- The new password must pass Django's standard validators (min length 8,
  not common, not fully numeric, not too similar to your details).

## If you KNOW your password and just want a new one (logged in)

- In the chat app: **Profile button → finish the profile/privacy prompts →
  “Change your password?”** — enter the current password, then the new one.
- API: `POST /api/auth/change-password/` with
  `{"current_password": "...", "new_password": "..."}` and your JWT.
  A wrong current password is refused (400); the new one is validated the
  same way as above.

## Before the reset flow existed

There was **no self-service reset**: a locked-out user's only options
were asking an admin to set a new password in Django admin, or
re-registering with a different email. This flow closes that gap.

Tests: `accounts/tests.py::PasswordResetAndChangeTests` — the full
forgot-password journey via the emailed link, unknown-email privacy,
bad-token rejection, link self-destruction after use, and the logged-in
change-password endpoint. Full suite: **33 tests**.
