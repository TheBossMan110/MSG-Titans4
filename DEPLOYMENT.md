# Deployment: Render (backend) + Vercel (frontend)

This is how the live system is deployed, entirely on free plans:

| Part | Where | Address |
|---|---|---|
| Frontend (Next.js) | Vercel, Hobby plan | https://support-nova.vercel.app |
| Backend (FastAPI) | Render, Free web service, Singapore region | https://supportnova.onrender.com |
| Database | Supabase Postgres (session pooler, Mumbai) | already migrated and filled |
| Email | Gmail: IMAP to read the inbox; Google Apps Script relay to send replies | supportnova110@gmail.com |

The browser calls the backend directly over HTTPS. Sign-in, sign-up and session refresh go through the frontend's own `/api/session/*` routes on Vercel, which keep the refresh token in an httpOnly cookie.

---

## 1. Backend on Render

**New → Web Service**, then connect the GitHub repository.

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Region | Singapore (closest to the Supabase database in Mumbai) |
| Build Command | `pip install -r requirements.txt -c constraints.txt` |
| Start Command | `uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips "*"` |
| Instance Type | Free |
| Health Check Path | `/` |

**Exactly one worker.** The response cache, the sign-out list, the rate limiter and the Gmail poller live in the process's memory. A second worker would serve stale pages and answer each email twice.

**Environment.** Use "Add from .env" with the contents of a working `backend/.env` (template: `backend/.env.example`), then set:

| Variable | Value |
|---|---|
| `PYTHON_VERSION` | `3.13.7` |
| `APP_ENV` | `production`. With this set, the app refuses to start on a weak `JWT_SECRET` or a non-Postgres database. |
| `DATABASE_URL` | Supabase **session pooler** URL (`…pooler.supabase.com:5432`) |
| `JWT_SECRET` | 32+ random characters. Keep it unchanged once users exist: it signs sessions and encrypts 2FA secrets. |
| `CORS_ORIGINS` | `https://support-nova.vercel.app`: exactly the site's address, comma-separated if several. |
| `CORS_ORIGIN_REGEX` | optional, for Vercel preview URLs, e.g. `^https://support-nova(-[a-z0-9-]+)?\.vercel\.app$` |
| `PUBLIC_APP_URL` | `https://support-nova.vercel.app`. Links in emails point here. |
| `SESSION_PROXY_SECRET` | a long random string; **the same value on Vercel** |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_DEFAULT` | `20/minute` / `600/minute` |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | free-tier keys |
| `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD` | the support Gmail account and its App Password (used to read the inbox) |
| `EMAIL_RELAY_URL`, `EMAIL_RELAY_SECRET` | the Apps Script relay, see section 3 |

**Never run the seeder against the live database.** It is already migrated (Alembic head `0004_email_messages`) and filled, and seeding resets the demo accounts' passwords.

Check: https://supportnova.onrender.com/api/health should show `"database":"ok"`.

## 2. Frontend on Vercel

**Add New → Project**, then import the repository.

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework | Next.js |
| Install Command | `npm ci` |
| Function Region | Singapore (`sin1`), next to the Render backend |

Environment variables (Production and Preview):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://supportnova.onrender.com`, with no trailing slash and no `/api` |
| `API_URL` | the same |
| `SESSION_PROXY_SECRET` | the same value as on Render |

`NEXT_PUBLIC_*` values are built into the pages, so **redeploy after changing them**.

## 3. Email replies on Render's free plan

Render's free web services block outbound SMTP ports 25, 465 and 587 (since September 2025), so the backend cannot send through `smtp.gmail.com`. Replies go instead through a tiny Google Apps Script web app running inside the Gmail account, reached over ordinary HTTPS:

1. Signed in as the support Gmail account, open https://script.google.com, create a **New project** and paste `backend/scripts/gmail-relay.gs`.
2. Replace the `SECRET` placeholder with a long random string. **Do not commit that value**; the repository copy keeps the placeholder.
3. **Deploy → New deployment → Web app**, with *Execute as: Me* and *Who has access: Anyone*. Authorise, then copy the URL ending in `/exec`.
4. On Render, set `EMAIL_RELAY_URL` to that URL and `EMAIL_RELAY_SECRET` to the same string.

The Email page then shows *Sending replies: From Gmail*. Free Gmail accounts can send about 100 emails a day this way. After editing the script, use **Manage deployments → Edit → New version**.

Only one backend may hold the Gmail credentials. Blank `EMAIL_APP_PASSWORD` on any local copy while the live one is running.

## 4. Keeping it awake

Render's free services sleep after 15 minutes without traffic; the next request then takes about 50 seconds. For judging, add a free monitor (for example UptimeRobot) that opens `https://supportnova.onrender.com/` every 5 minutes. One always-on service fits in Render's free monthly hours.

## 5. Known limits of the free setup

- **Uploaded files** are stored on the instance's disk, which Render's free plan does not keep across restarts. Knowledge-base search is unaffected because sections and embeddings live in the database, but an uploaded original or photo may need re-uploading after a restart. Setting `STORAGE_BACKEND=supabase` with a private Supabase Storage bucket makes uploads permanent.
- **Free AI quotas**: the model chain falls back Gemini → Groq → OpenRouter. If every provider is exhausted, the Python rules still decide alone.
- **Supabase free** projects pause after about a week without activity; restore from the dashboard if needed.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Sign-in works but pages say *"The server could not be reached"* | `NEXT_PUBLIC_API_URL` was missing or wrong when the site was built: fix it and **redeploy** on Vercel. Or `CORS_ORIGINS` on Render doesn't exactly match the site address (no trailing slash). |
| First page load takes about a minute | The free backend was asleep (section 4). |
| Replies not sent | Relay not configured or secret mismatch: check `EMAIL_RELAY_URL` / `EMAIL_RELAY_SECRET` and the Email page's last error. |
| Duplicate replies or complaints | Two backends are reading the same Gmail inbox. |
| `429 Too Many Requests` at sign-in | `SESSION_PROXY_SECRET` missing or different between Vercel and Render. |
| Vercel deployment **Blocked** | On the Hobby plan with a private repository, only the project owner's commits deploy. Push an empty commit as the owner, or make the repository public. |
