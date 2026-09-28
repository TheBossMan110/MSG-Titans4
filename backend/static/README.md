# static/

The FastAPI backend serves **no static files**: there is no `StaticFiles` mount in `backend/src/main.py`, and every
route under `/api` returns JSON, a live event stream (`POST /api/complaints/stream`) or a file generated or
fetched for that one request (report exports, and evidence downloads, which are always sent as attachments). The
only HTML it returns is the interactive API documentation at `/api/docs` and `/api/redoc`, which FastAPI generates
itself (its scripts and styles come from a public CDN). This folder is therefore empty apart from this signpost.

## Where the static assets are

All static assets are served by the **Next.js frontend** from [`frontend/public/`](../../frontend/public/), which
Vercel publishes at the site root (`frontend/public/brand/og.png` is served as `/brand/og.png`).

| Path | What it is |
|---|---|
| `frontend/public/brand/supportnova-mark.png`, `supportnova-mark-256.png` | The SupportNova logo mark used in the interface |
| `frontend/public/brand/favicon-16.png`, `favicon-32.png`, `icon-192.png`, `icon-512.png` | Browser and app icons |
| `frontend/public/brand/og.png` | Social-sharing preview image (1200 × 630) |
| `frontend/public/brand/supportnova-mark-email.png` | The logo variant made for email |
| `frontend/public/favicon.ico`, `icon.svg`, `apple-touch-icon.png`, `apple-icon.png`, `icon-light-32x32.png`, `icon-dark-32x32.png` | Favicons, wired up in `frontend/app/layout.tsx` |
| `frontend/public/placeholder*` | Placeholder images from the UI kit |

Related, but not static files:

* **Styles** are in `frontend/app/globals.css` (Tailwind CSS 4) and compiled by the Next.js build.
* **Fonts** (Fraunces, Instrument Sans, JetBrains Mono) are loaded with `next/font/google`, which downloads them at
  build time and serves them from the site itself, so the browser makes no request to Google.
* **The email logo** that the backend itself needs lives at `backend/src/assets/supportnova-mark-email.png`. It is
  read from disk and embedded in each outgoing email as an inline image; it is not served over HTTP.

To add a static asset, put it in `frontend/public/` and reference it from the frontend by its root path
(for example `/brand/new-image.png`).
