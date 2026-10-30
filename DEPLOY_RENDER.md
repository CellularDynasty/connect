# Deploying this codebase on Render

This is the deployment-ready version of the project. Compared to the local versions it adds:
WhiteNoise (serves CSS/JS in production), a `.python-version` file (Python 3.12.7),
production settings for Render (proxy HTTPS header, automatic `*.onrender.com` host),
and a `render.yaml` Blueprint that creates everything in one go.

## Easiest path — Blueprint (recommended)

1. Push **the contents of this folder** to a GitHub repo, so `manage.py` and `render.yaml`
   are at the repo root. (If the repo root is a parent folder instead, open `render.yaml`
   and uncomment/set `rootDir` to this folder's name in the repo.)
2. Render Dashboard → **New → Blueprint** → connect that repo → **Apply**.
3. Render creates 3 resources in Singapore and wires them together automatically:
   - Web service `realtime-chat` (runs Daphne, so WebSockets work)
   - PostgreSQL `realtime-chat-db` → injected as `DATABASE_URL`
   - Key Value `realtime-chat-redis` (Redis-compatible) → injected as `REDIS_URL`
   - A generated `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS=.onrender.com`
4. Wait for the first deploy to finish in the Logs tab, then open the service URL
   (`https://realtime-chat.onrender.com` or similar) and register your accounts there.

Build command used (already in render.yaml):
`pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput`

Start command used (already in render.yaml):
`daphne -b 0.0.0.0 -p $PORT realtime_chat.asgi:application`
Do NOT change this to `runserver` or plain `gunicorn ...wsgi` — WebSockets need the ASGI server.

## Manual path (if you don't want the Blueprint)

Create PostgreSQL and Key Value instances yourself in the same region, create a Python
Web Service from the repo, and copy the Build/Start commands and the environment variables
from `render.yaml` into the dashboard by hand. `DATABASE_URL` = the Postgres *Internal*
Database URL, `REDIS_URL` = the Key Value *Internal* Connection String.

## Known free-tier behaviour (not bugs)

- Free web services spin down after ~15 min without traffic and take ~1 min to wake.
- Free PostgreSQL expires after ~30 days.
- The filesystem is ephemeral, so files uploaded to `media/` are lost on redeploy/restart.
  Chat data is safe in PostgreSQL. For durable uploads, add a paid Persistent Disk mounted
  at the project's `media` folder, or move uploads to S3/Cloudinary.
- Admin panel works at `/admin/`; create a superuser later from a paid instance's Shell
  with `python manage.py createsuperuser` (free instances have no Shell — the app itself
  doesn't need one, registration is built into the UI).
