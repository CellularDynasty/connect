# Making v6 live on Render

Your live site is the **Render web service `realtime-chat`**, which
auto-deploys whatever is on the **`main` branch of
github.com/CellularDynasty/connect**. So "making v6 live" = putting the
v6 code on that branch and letting Render redeploy. Git keeps the old
code in history, so this is reversible (`git revert` / redeploy an older
commit from the Render dashboard).

## Step 0 — set the email settings FIRST (important)

v6 blocks login for unverified emails. Existing users were grandfathered
as verified by the migration, so they are fine — but **new signups can
only verify if Render can actually send email**. Until these are set,
verification emails are only printed in the Render service logs.

In the Render dashboard → web service `realtime-chat` → **Environment**,
add (Gmail example):

| Key | Value |
|---|---|
| `EMAIL_HOST` | `smtp.gmail.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | your Gmail address |
| `EMAIL_HOST_PASSWORD` | a Gmail **App Password** (Google Account → Security → 2-Step Verification → App passwords) — never your normal password |
| `EMAIL_USE_TLS` | `True` |
| `DEFAULT_FROM_EMAIL` | your Gmail address |

Save — Render will redeploy with the new variables; that's fine.

## Step 1 — put v6 into the connect repo (on your Mac)

Your `realtime_chat_platform_deploy` folder is the one linked to the
`connect` repo. In Terminal:

```bash
cd ~/Desktop/django-projects/realtime_chat_platform_deploy
git status            # should be clean, branch main
git remote -v         # should show github.com/CellularDynasty/connect
```

Now replace its contents with v6 — **keep the `.git` folder**, remove the
old code files, and copy v5 in (from the django-projects folder):

```bash
cd ~/Desktop/django-projects
# remove old code (NOT .git, NOT anything you keep separately)
find realtime_chat_platform_deploy -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
# copy v6 in — without its venv, local database, uploads or caches
rsync -a --exclude venv --exclude db.sqlite3 --exclude media \
  --exclude __pycache__ --exclude staticfiles \
  realtime_chat_platform_v6/ realtime_chat_platform_deploy/
cd realtime_chat_platform_deploy
git status            # many changed/new files — that is expected
```

## Step 2 — commit and push

```bash
git add -A
git commit -m "v6: UI redesign (black/mint), info panel, mute, privacy-aware online status"
git push origin main
```

Use the same token as before (username `CellularDynasty`, the
fine-grained token scoped to the `connect` repo as the password).

## Step 3 — watch the Render deploy

Render dashboard → `realtime-chat` → **Logs**. The build runs
`pip install`, `collectstatic` and `migrate` (from render.yaml's
buildCommand) — migrations `accounts.0002` and `chat.0003` apply to the
live database automatically. Wait for the service to show **Live**.

## Step 4 — test the live site

1. Open your onrender.com URL, hard-refresh (Cmd+Shift+R).
2. Log in with an **existing** account — it should just work (grandfathered).
3. Register a **new** account — a real verification email should arrive,
   click its link, then log in.
4. In a chat: send a file and download it, send a voice note, try the 📍
   location share (the deployed site is HTTPS, so mic/location work),
   and open it on your phone for the mobile layout.

## Known free-tier limits (unchanged)

- The web service sleeps after ~15 min idle (first load is slow).
- Uploaded files (including voice notes) live on the service's disk,
  which is **ephemeral** — they are lost on redeploy/restart. Chat
  messages and accounts in PostgreSQL are not affected.
- The free PostgreSQL (`realtime-chat-db`, created 2026-10-30) expires
  after ~30 days — check its status in the dashboard; upgrading it or
  recreating it is a separate decision.
