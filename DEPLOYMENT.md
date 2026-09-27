# Deploying SupportNova: backend on Oracle Cloud, frontend on Vercel

This guide covers everything from an empty Oracle account to a live site. Follow the parts in order. Every command can be copied as-is once you replace the placeholders in `<angle brackets>`.

**Time:** about 60–90 minutes the first time.
**Cost:** nothing. Oracle "Always Free", Vercel "Hobby", DuckDNS and Let's Encrypt are all free. The AI providers already in your `.env` (Gemini, Groq, OpenRouter) are free tiers.

---

## How the pieces fit

```
                 ┌──────────────────────────── Vercel (free) ─────────────────────────────┐
  Browser ──────▶│  Next.js pages  +  /api/session/* (sign-in proxy, keeps the refresh    │
     │           │                     token in an httpOnly cookie)                       │
     │           └───────────────────────────────┬────────────────────────────────────────┘
     │ HTTPS (all other API calls)               │ HTTPS (sign-in, sign-up, refresh)
     ▼                                           ▼
  ┌──────────────────── Oracle VM (Always Free, Ubuntu 24.04) ────────────────────┐
  │  Caddy  :443  (automatic HTTPS certificate)                                    │
  │    └─▶ uvicorn  127.0.0.1:8000   (FastAPI, ONE worker, systemd service)        │
  │           ├─ Gmail IMAP/SMTP (reads the support inbox, sends replies)          │
  │           └─ backend/var/uploads (knowledge-base files, complaint photos)      │
  └────────────────────────────────────────┬──────────────────────────────────────┘
                                           ▼
                           Supabase Postgres (Mumbai, already migrated + filled)
```

Three rules explain most of what follows:

1. **The browser talks to the backend directly.** The Vercel site is `https://`, so the backend must also be `https://` on a real hostname. Browsers block `http://` calls from an `https://` page. That is why the guide sets up a DuckDNS name and Caddy.
2. **Run exactly one backend process.** The speed caches, the logout list, the rate limiter and the Gmail poller all live in memory. Two workers, or a second copy of the backend, would serve stale pages and answer the same email twice.
3. **The database is already migrated and filled.** Don't seed it or reset it. Deploying only points a new server at the same Supabase database.

---

## Names used in this guide

| Placeholder | What it is | Example |
|---|---|---|
| `<VM_IP>` | Public IP of your Oracle VM (Part 1) | `140.238.12.34` |
| `<API_HOST>` | The backend's hostname (Part 10) | `supportnova-api.duckdns.org` |
| `<VERCEL_URL>` | Your Vercel site address (Part 11) | `https://supportnova.vercel.app` |
| `<KEY>` | The SSH private key Oracle gives you | `C:\Users\AWCD\.ssh\supportnova-oracle.key` |
| `<PROXY_SECRET>` | A random string shared by Vercel and the backend (Part 7) | 64 hex characters |

Region choice: your Supabase database is in **Mumbai (ap-south-1)**. Put the Oracle VM in **India West (Mumbai)** and Vercel functions in **bom1 (Mumbai)**. Every page makes database round trips, so a VM far from the database is noticeably slower.

---

## Part 0 — Put all the code on GitHub (on your laptop)

Vercel and the Oracle server both download the code from GitHub, so everything has to be committed and pushed. That includes the new logo files, the speed-cache files (`backend/src/core/response_cache.py`, `backend/src/services/warmup.py`) and `backend/constraints.txt`. A server running without them crashes on start with `ModuleNotFoundError`.

In **PowerShell**, in `C:\Users\AWCD\Desktop\Techwiz`:

```powershell
cd frontend; npm ci; npm run build; cd ..                  # must end without errors (Vercel runs the same strict build)
cd backend; .venv\Scripts\python -m pytest -q; cd ..        # every test must pass (it uses its own test database)
git config user.email           # must be an email on the GitHub account that will own the Vercel project (see below)
git status                      # check: NO .env or .env.local files in the list
git add -A
git status                      # check again before committing
git commit -m "Logo, speed caches, deploy fixes"
git pull --rebase origin main   # take your teammates' latest work first
git push origin main
```

If `git status` ever lists `backend/.env` or `frontend/.env.local`, stop. Those hold your secret keys and must never be pushed. They are ignored by `.gitignore` and should not appear.

> **Vercel's free plan and a private repo with teammates.** On the Hobby plan, Vercel only builds commits whose author is the owner of the Vercel project. A commit pushed by a teammate shows **Blocked** in Vercel. So create the Vercel project with the GitHub account that owns the repo (TheBossMan110), and commit from an email address verified on that account. If a teammate's push is blocked, the owner runs `git pull`, then `git commit --allow-empty -m "deploy"` and `git push`, and Vercel builds it. Making the repo public also removes this limit.

---

## Part 1 — Create the Oracle VM

1. Sign in at **https://cloud.oracle.com**. When you create an account, choose **India West (Mumbai)** as the home region. Always Free resources only exist in your home region, and it cannot be changed later.
2. Menu (☰) → **Compute → Instances → Create instance**.
3. **Name:** `supportnova-api`.
4. **Image and shape → Edit:**
   - **Image:** *Change image* → **Ubuntu** → **Canonical Ubuntu 24.04**. Ubuntu 22.04 ships Python 3.10, which is too old; the backend needs 3.11 or newer.
   - **Shape:** *Change shape* → **Ampere** → **VM.Standard.A1.Flex**, **2 OCPUs, 12 GB memory**. This is within Always Free, which allows up to 4 OCPUs and 24 GB in total. All the backend's Python packages have ARM builds.
5. **Networking:** keep *Create new virtual cloud network* and *Create new public subnet*. Make sure **Assign a public IPv4 address** is **Yes**.
6. **Add SSH keys:** choose **Generate a key pair for me** and click **Save private key**. Move the downloaded file to `C:\Users\AWCD\.ssh\supportnova-oracle.key`. **Oracle cannot give you this file again.**
7. **Boot volume:** leave the default (about 47–50 GB, free).
8. Click **Create**. When the state turns green (**Running**), copy the **Public IP address**. That is your `<VM_IP>`.
9. *Recommended:* make the IP permanent. Open **Instance → Attached VNICs → (the VNIC) → IPv4 Addresses → ⋯ → Edit**, then choose **Reserved public IP → Create new**. Reserved IPs are free while attached. Your DNS name then keeps working even if you ever rebuild the VM.

> **"Out of capacity for shape VM.Standard.A1.Flex"** is common on free accounts. You can try again in a few hours, or ask for 1 OCPU / 6 GB. You can also upgrade the account to *Pay As You Go*: Always Free resources stay free, capacity is easier to get, and Oracle stops reclaiming idle free VMs. The last resort is shape **VM.Standard.E2.1.Micro** (AMD, 1 GB RAM) with the matching Ubuntu 24.04 image. It works, but add the swap file from Part 4.

---

## Part 2 — Open ports 80 and 443 in Oracle's cloud firewall

Oracle blocks everything except SSH (port 22) in **two places**. This part is the first; Part 4 handles the second, inside the VM.

1. Open your instance → **Instance details → Primary VNIC → Subnet** (click the subnet name).
2. **Security** tab (older consoles: *Security Lists*) → **Default Security List for …** → **Add Ingress Rules**.
3. Add two rules:

| Source CIDR | IP protocol | Destination port range | Why |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `80` | Let's Encrypt checks the domain on port 80 |
| `0.0.0.0/0` | TCP | `443` | HTTPS for the site and Vercel |

**Do not open port 8000.** The backend listens only inside the VM, and Caddy is its only door. The ports must be open to everyone because Vercel's servers have no fixed IP addresses.

---

## Part 3 — Connect to the VM from Windows

In **PowerShell** on your laptop:

```powershell
# OpenSSH refuses keys that other Windows users can read; lock the file down once.
icacls "$env:USERPROFILE\.ssh\supportnova-oracle.key" /inheritance:r
icacls "$env:USERPROFILE\.ssh\supportnova-oracle.key" /grant:r "$($env:USERNAME):(R)"

ssh -i "$env:USERPROFILE\.ssh\supportnova-oracle.key" ubuntu@<VM_IP>
```

Type `yes` the first time. You are now on the server, and the prompt looks like `ubuntu@supportnova-api:~$`. Everything in Parts 4–10 runs **on the VM** unless it says *laptop*.

---

## Part 4 — Prepare the server

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3-venv python3-pip git curl debian-keyring debian-archive-keyring apt-transport-https
python3 --version        # must say 3.11 or newer (24.04 gives 3.12)
```

**The second firewall (inside Ubuntu).** Oracle's Ubuntu images come with their own `iptables` rules that reject everything except SSH:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
sudo iptables -L INPUT -n --line-numbers   # 80 and 443 must appear ABOVE the "REJECT" line
```

Don't enable `ufw` on Oracle images, because it conflicts with these rules.

**Only on the 1 GB E2.1.Micro shape**, add swap so `pip install` doesn't run out of memory:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

The clock must be right, because two-step sign-in codes tolerate only ±30 s. `timedatectl` should show `System clock synchronized: yes`, which is Ubuntu's default.

---

## Part 5 — Download the code (private repository)

The GitHub repository is private, so give the server its own **read-only deploy key**:

```bash
ssh-keygen -t ed25519 -C "oracle-supportnova" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copy the line it prints. On GitHub: **TheBossMan110/SupportNova → Settings → Deploy keys → Add deploy key**. Paste it, give it the title `oracle-vm`, leave *Allow write access* **off**, and click **Add key**. The repo owner has to do this. Then:

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
chmod 600 ~/.ssh/config
git clone git@github.com:TheBossMan110/SupportNova.git ~/SupportNova
ls ~/SupportNova          # backend  dataset  frontend  ...
```

---

## Part 6 — Python environment

```bash
cd ~/SupportNova/backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt -c constraints.txt
```

`constraints.txt` pins the exact versions the 977 tests passed with. Without it, pip would pick newer, untested versions. This takes 2–4 minutes.

---

## Part 7 — Configuration: bring your `.env` and uploaded files over

Your laptop's `backend/.env` already holds every correct value: the database, AI keys, JWT secret and Gmail App Password. Copy it rather than retyping 55 variables, then change a few lines.

**On your laptop** (new PowerShell window, in `C:\Users\AWCD\Desktop\Techwiz`):

```powershell
$KEY = "$env:USERPROFILE\.ssh\supportnova-oracle.key"
scp -i $KEY backend\.env ubuntu@<VM_IP>:~/SupportNova/backend/.env
ssh -i $KEY ubuntu@<VM_IP> "mkdir -p ~/SupportNova/backend/var"
scp -i $KEY -r backend\var\uploads ubuntu@<VM_IP>:~/SupportNova/backend/var/
```

The second copy brings the 4.3 MB of uploaded knowledge-base files and complaint photos. They are not in git (`var/` is ignored), but the database points at them. Without them, downloading a complaint's photo fails with "Stored file not found".

**Back on the VM**, make a secret for the sign-in proxy and edit the file:

```bash
cd ~/SupportNova/backend
chmod 600 .env
openssl rand -hex 32          # copy this: it is your <PROXY_SECRET>
nano .env
```

Change or add **only these lines** and leave everything else as it came from your laptop:

```ini
APP_ENV=production
CORS_ORIGINS=http://localhost:3000             # replaced with your Vercel URL in Part 12
PUBLIC_APP_URL=http://localhost:3000           # replaced with your Vercel URL in Part 12
SESSION_PROXY_SECRET=<PROXY_SECRET>            # new line; the same value goes into Vercel
RATE_LIMIT_LOGIN=20/minute
RATE_LIMIT_DEFAULT=600/minute
STORAGE_LOCAL_DIR=/home/ubuntu/SupportNova/backend/var/uploads
```

Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

Why each one:

- `APP_ENV=production` switches logs to JSON. It also makes the backend **refuse to start** if `JWT_SECRET` is the public default. Yours is already a strong custom value.
- **Keep `JWT_SECRET` exactly as on your laptop.** Two-step sign-in secrets in the database are encrypted with it. A new value locks those users out of 2FA, and everyone has to sign in again.
- `SESSION_PROXY_SECRET`: sign-ins reach the backend through Vercel's servers, which share a few IP addresses. With this secret, the backend counts sign-in attempts per visitor instead of per Vercel server. Without it, the sixth sign-in in a minute from *anyone* would be refused.
- Raised limits: a dashboard loads many small requests. Judges on one Wi-Fi share a single public IP, and 120 requests a minute is too tight for a room of them. Account lockout (5 wrong passwords → 15-minute lock) still protects every account.
- `DATABASE_URL` stays the Supabase **session pooler** address (`…pooler.supabase.com:5432`). Don't switch to the direct `db.<ref>.supabase.co` host: it is IPv6-only, and Oracle networks are IPv4.

---

## Part 8 — Check the database (do not seed)

First confirm the server really reads your `.env`. A missing or misnamed file makes the app fall back to an empty local SQLite database. The backend now refuses to start in production when that happens, but check before you go further:

```bash
cd ~/SupportNova/backend
.venv/bin/python -c "from src.core.config import settings as s; print('postgres:', s.is_postgres, '| env:', s.app_env, '| jwt ok:', len(s.jwt_secret) >= 32, '| proxy secret set:', bool(s.session_proxy_secret))"
# expect: postgres: True | env: production | jwt ok: True | proxy secret set: True
find var/uploads -type f | wc -l             # expect about 709 (the copied files)
```

Then the database:

```bash
.venv/bin/python -m alembic current          # expect: 0004_email_messages (head)
.venv/bin/python -m alembic upgrade head     # does nothing when already at head; safe
.venv/bin/python -c "from src.main import app; print('backend imports OK')"
```

**Do not run `python -m src.db.seed.run`.** The database is already full: 555 complaints, 619 rules, 24 knowledge-base documents and your accounts. Seeding resets the demo accounts' passwords. `--reset` would delete everything.

---

## Part 9 — Run the backend as a service

This keeps it running after you log out, restarts it if it crashes, and starts it when the VM reboots.

```bash
sudo tee /etc/systemd/system/supportnova.service > /dev/null <<'EOF'
[Unit]
Description=SupportNova API (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/SupportNova/backend
Environment=PYTHONUNBUFFERED=1
# ONE worker: caches, logout list, rate limits and the Gmail poller live in this process.
# --proxy-headers + 127.0.0.1: trust Caddy (same machine) to say who the real visitor is.
ExecStart=/home/ubuntu/SupportNova/backend/.venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --timeout-keep-alive 75 --timeout-graceful-shutdown 15 --no-server-header
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now supportnova
systemctl status supportnova --no-pager           # should say "active (running)"
curl -s http://127.0.0.1:8000/api/health; echo
```

The health check should show `"status":"ok"`, `"database":"ok"` and `"llm_configured":true`. Right after a start, the backend spends about 30–40 s warming the heavy dashboard pages in the background (the log line is `warmup_done`). Pages served after that load in well under a second.

Never add `--reload` or `--workers 2` or more here.

---

## Part 10 — A hostname and HTTPS

### 10a. Get a free hostname (DuckDNS)

1. Go to **https://www.duckdns.org** and sign in with GitHub or Google.
2. Type a sub-domain, for example `supportnova-api`, and click **add domain**.
3. In the **current ip** box next to it, enter `<VM_IP>` and click **update ip**.

Your `<API_HOST>` is now `supportnova-api.duckdns.org`. Check it from the VM:

```bash
getent hosts supportnova-api.duckdns.org      # must print <VM_IP>
```

*Alternatives:* if you own a domain, add an **A record** `api` → `<VM_IP>`, and your host is `api.yourdomain.com`. Or skip sign-ups and use `<VM_IP with dashes>.sslip.io`, for example `140-238-12-34.sslip.io`.

### 10b. Install Caddy (it gets and renews the certificate by itself)

```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt -y install caddy

sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
supportnova-api.duckdns.org {
	reverse_proxy 127.0.0.1:8000 {
		# stream the live "analysing your complaint" steps instead of buffering them
		flush_interval -1
	}
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
		-Server
	}
}
EOF
sudo systemctl reload caddy
```

If you picked a different hostname, put it in place of `supportnova-api.duckdns.org` in the Caddyfile.

Wait about 20 seconds, then test from the VM **and** from your laptop browser:

```bash
curl -s https://supportnova-api.duckdns.org/api/health; echo
```

If it fails, run `sudo journalctl -u caddy -n 50 --no-pager`. The usual cause is port 80 or 443 still closed in Part 2 or Part 4, or DNS not pointing at `<VM_IP>` yet.

Caddy needs no extra settings for this app. It has no upload-size limit, no 60-second timeout, and passes the visitor's IP to uvicorn. Don't add CORS headers in Caddy: FastAPI already sends them, and doubled headers break the browser.

---

## Part 11 — Deploy the frontend on Vercel

1. Go to **https://vercel.com**, sign in with GitHub, then **Add New… → Project → Import** `TheBossMan110/SupportNova`. Grant Vercel access to the private repo if asked.
2. **Configure Project:**

| Setting | Value |
|---|---|
| Project Name | `supportnova` (this becomes `supportnova.vercel.app` if it's free) |
| Framework Preset | **Next.js** |
| **Root Directory** | **`frontend`** ← click *Edit*; required, the repo root has no `package.json` |
| Build Command | leave default (`next build`) |
| Install Command | override → `npm ci` |
| Output Directory | leave default |

3. **Environment Variables.** Add them now, before the first build, for **Production and Preview**:

| Name | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<API_HOST>` | No trailing slash and no `/api`. It is built into the pages, so **redeploy after any change**. |
| `API_URL` | `https://<API_HOST>` | Used by the sign-in proxy on Vercel's servers. |
| `SESSION_PROXY_SECRET` | `<PROXY_SECRET>` | Exactly the value in the VM's `.env`. Tick **Sensitive**. Server-only; never name it `NEXT_PUBLIC_…`. |

4. Click **Deploy** and wait about 2 minutes for the green *Ready*. Your `<VERCEL_URL>` is the address under **Settings → Domains**, for example `https://supportnova.vercel.app`. Use that one. Do **not** use the long per-deployment address like `supportnova-a1b2c3-team.vercel.app`: it changes on every deploy and sits behind Vercel's login.
5. **Settings → Functions → Function Region → Mumbai, India (bom1)**. Sign-ins travel browser → Vercel → Oracle, and the default US region adds about 250 ms to each one.
6. **Settings → Build and Deployment → Node.js Version → 22.x**.
7. After changing 5 and 6: **Deployments → ⋯ on the latest → Redeploy**.

Every `git push` to `main` now redeploys the frontend automatically.

---

## Part 12 — Connect the two

The backend must allow your Vercel address. **On the VM**:

```bash
cd ~/SupportNova/backend && nano .env
```

```ini
CORS_ORIGINS=https://supportnova.vercel.app          # your exact <VERCEL_URL>; no trailing slash
PUBLIC_APP_URL=https://supportnova.vercel.app        # links and the logo in emails point here
```

To add more addresses, separate them with commas and no spaces: `https://supportnova.vercel.app,http://localhost:3000`. Add `http://localhost:3000` only if you want your laptop's frontend to use this server. The value is a plain comma list, **not** JSON (`["..."]` does not work).

*Optional, for Vercel preview links:* these are URLs like `supportnova-git-branch-team.vercel.app`. To allow them, add:

```ini
CORS_ORIGIN_REGEX=^https://supportnova(-[a-z0-9-]+)?\.vercel\.app$
```

Then restart:

```bash
sudo systemctl restart supportnova
```

**On your laptop — stop reading the support inbox twice.** Once Oracle is live, two backends with the Gmail App Password would both read `supportnova110@gmail.com`. You would get duplicate complaints and duplicate replies. In your **laptop's** `backend/.env`, blank the line `EMAIL_APP_PASSWORD=`, or simply don't run the laptop backend while the server is live. Put it back if you go back to local-only.

Also avoid running the laptop backend against the same Supabase database during judging. Each process has its own caches, so edits made through one appear on the other only after a few minutes.

---

## Part 13 — Check that everything works

**From your laptop's PowerShell:**

```powershell
curl.exe -s https://<API_HOST>/api/health
Test-NetConnection <VM_IP> -Port 8000        # must FAIL (TcpTestSucceeded : False); only Caddy is public
curl.exe -s -X POST https://supportnova.vercel.app/api/session/refresh   # {"detail":"No session."} means Vercel reaches the backend
# CORS: must print "access-control-allow-origin: https://supportnova.vercel.app"
curl.exe -s -D - -o NUL -X OPTIONS https://<API_HOST>/api/auth/me -H "Origin: https://supportnova.vercel.app" -H "Access-Control-Request-Method: GET" | findstr /i "access-control-allow-origin"
```

**In the browser, open `<VERCEL_URL>`:**

- [ ] The tab shows the copper **S** icon, and the nav shows the SupportNova badge.
- [ ] Sign in as `admin@supportnova.com`. The dashboard shows numbers, not an error.
- [ ] **Press F5.** You stay signed in (this checks the cookie proxy).
- [ ] Open Complaints, Users & Roles, Reports and Analytics. Each loads in about a second, and revisits are instant.
- [ ] Reports: the table scrolls sideways.
- [ ] Top-right menu → Agent dashboard opens.
- [ ] Sign out, then sign in as `review@supportnova.com`. The reviewer dashboard shows.
- [ ] Sign in as a customer and submit a complaint. The steps appear live one by one, which checks streaming through Caddy. Attach a photo, which checks uploads.
- [ ] Open an older complaint that has a photo. The photo opens, which checks that the copied uploads arrived.
- [ ] Email page: *Receiving: Connected* and *Sending replies: From Gmail*.
- [ ] From your own Gmail, send a complaint to `supportnova110@gmail.com`. Within about a minute a reply arrives **with the logo in its header**, and the email appears on the Email page.
- [ ] Open the Nova chat bubble and ask something. It answers.
- [ ] Press F12 → Console. There are no red *CORS* or *Mixed Content* errors. In the **Network** tab, API calls go to `https://<API_HOST>/api/…` and never to `localhost`.
- [ ] Export a report. The downloaded file keeps its proper name.
- [ ] While signed in, run `sudo systemctl restart supportnova` on the VM, wait 20 s and reload the page. You are still signed in.
- [ ] `sudo reboot` the VM once, wait 2 minutes, and check the site still works. That proves the service, Caddy and the firewall rules all survive a reboot.

---

## Part 14 — Day-to-day operation

| Task | Command (on the VM) |
|---|---|
| Live backend logs | `journalctl -u supportnova -f` (stop with `Ctrl+C`) |
| Last 100 lines | `journalctl -u supportnova -n 100 --no-pager` |
| Restart backend | `sudo systemctl restart supportnova` |
| Caddy/HTTPS logs | `sudo journalctl -u caddy -n 50 --no-pager` |
| Is it up? | `curl -s https://<API_HOST>/api/health` |
| Disk / memory | `df -h /` · `free -h` |

**Update after new code is pushed to GitHub.** Vercel redeploys by itself. For the backend:

```bash
cd ~/SupportNova && git pull
cd backend
.venv/bin/pip install -r requirements.txt -c constraints.txt   # only needed if requirements changed
.venv/bin/python -m alembic upgrade head                       # only needed if a migration was added
sudo systemctl restart supportnova
```

**Back up the uploaded files** now and then. The database is on Supabase, but these files exist only on the VM. On your laptop:

```powershell
scp -i $KEY -r ubuntu@<VM_IP>:~/SupportNova/backend/var/uploads backup-uploads
```

**Keep the free services awake:**

- Add a free uptime monitor, such as **UptimeRobot**, that opens `https://<API_HOST>/api/health` every 5 minutes. It warns you when the site goes down, and the steady traffic keeps both Oracle and Supabase from treating the project as idle.
- **Oracle** can reclaim an Always Free VM that stays almost idle for 7 days (low CPU, network and memory). Upgrading the account to *Pay As You Go* (still free for Always Free resources) removes this. So does regular use.
- **Supabase** free projects pause after about a week without activity. If the site suddenly says the server can't be reached, open the Supabase dashboard and click **Restore**.
- **DuckDNS** names stay as long as you sign in to duckdns.org every few months.

If you ever **stop and start** the VM, the public IP normally stays the same. If you terminate it and make a new one, enter the new IP on DuckDNS (Part 10a).

---

## Part 15 — Security checklist

- [ ] **Never** put `.env` in git. **Never** give the frontend `SUPABASE_SERVICE_ROLE_KEY` or any AI key; only the three variables in Part 11 go to Vercel.
- [ ] Port **8000 stays closed** in Oracle. Only 22, 80 and 443 are open.
- [ ] After judging, change the demo passwords. `admin@supportnova.com` / `review@supportnova.com` use `123456789`, and the seeded accounts use the password published in `backend/README.md`. Anyone can find these on a public site.
- [ ] Rotate the DeepSeek key that was pasted in chat earlier (DeepSeek dashboard → API keys → delete). The app no longer uses it.
- [ ] **Lock Supabase's public data API. Do this before sharing the link.** Row-level security is currently off on all 55 tables. Anyone holding the project's public "anon" key could read them through `https://<ref>.supabase.co/rest/v1/…`, including the `users` table with its password hashes. SupportNova never uses that API; the backend connects straight to Postgres as the table owner and is unaffected. Either option below works:
  - **Simplest:** Supabase → **Project Settings → Data API** → turn the Data API off, or remove `public` from *Exposed schemas*.
  - **Or**, in **Supabase → SQL Editor**, run:

  ```sql
  DO $$ DECLARE t record; BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
    END LOOP;
  END $$;
  ```

  Then reload the dashboard to confirm it still works. To undo, run the same block with `DISABLE`.
- [ ] One sign-in per browser: the sign-in cookie belongs to the browser, so signing in as another role in a second tab switches every tab to that role. To show several roles side by side, use a separate browser profile or an incognito window for each.
- [ ] The API docs at `https://<API_HOST>/api/docs` are public. That is handy for judges. They reveal the API's shape, not data, because every data route still needs a token.

---

## Part 16 — Troubleshooting

| What you see | Most likely cause | Fix |
|---|---|---|
| Site says *"The server could not be reached. Is the backend running?"* | Browser can't reach the API | F12 → Console. A **CORS** error means `CORS_ORIGINS` doesn't exactly match `<VERCEL_URL>` (Part 12). **Mixed Content** means `NEXT_PUBLIC_API_URL` starts with `http://`. **ERR_NAME_NOT_RESOLVED** means the DuckDNS IP is wrong. Otherwise the backend is down: `systemctl status supportnova`. |
| Sign-in says *"The server could not be reached. Please try again in a moment."* | Vercel's sign-in proxy can't reach Oracle | `API_URL` on Vercel is wrong or not `https`, or the backend is down. Check **Vercel → Deployments → Logs**. |
| Changed an env var on Vercel and nothing changed | `NEXT_PUBLIC_*` values are built in at build time | Redeploy (Part 11 step 7). |
| Vercel build: *No Next.js version detected* | Root Directory not set | Settings → Build and Deployment → Root Directory = `frontend`. |
| Vercel build: lockfile / `ERR_PNPM…` errors | Wrong package manager | The repo uses npm (`package-lock.json`). Set Install Command to `npm ci`. |
| Vercel build: TypeScript error | A type error was pushed | Run `npm run build` in `frontend/` on your laptop, fix, and push. |
| `systemctl status supportnova` → *failed* | Startup error | `journalctl -u supportnova -n 80 --no-pager`. *ModuleNotFoundError* means Part 0 wasn't fully pushed. *JWT_SECRET must be set…* means the `.env` copy failed. *could not connect / password authentication* means `DATABASE_URL` is wrong or Supabase is paused. |
| Caddy: *no certificate* / browser shows a certificate warning | Let's Encrypt can't reach the VM | Open 80 and 443 in **both** Part 2 and Part 4. `getent hosts <API_HOST>` must equal `<VM_IP>`. |
| *429 Too Many Requests* when signing in | Rate limit | `SESSION_PROXY_SECRET` is missing or differs between Vercel and the VM (set it, redeploy, restart). Otherwise raise `RATE_LIMIT_LOGIN`. |
| *Account locked* | 5 wrong passwords | Wait 15 minutes, or an admin unlocks the user on Users & Roles. |
| Vercel shows a deployment as **Blocked** | Hobby plan, private repo, commit by a teammate | The owner pushes an empty commit (Part 0 note), or make the repo public. |
| Log says *Max client connections reached* / *too many clients* | Laptop and server both connected to Supabase | Stop the laptop backend (each one uses up to 10 of the ~15 free pooler connections). |
| Customers get two replies / duplicate complaints | Two backends reading Gmail | Blank `EMAIL_APP_PASSWORD` on the laptop (Part 12). |
| No replies are sent | Gmail sign-in blocked from a datacenter IP | Check the Gmail account's *Security* alerts and approve the sign-in. Make sure the App Password is still valid. |
| An old complaint's photo gives an error | Uploads not copied | Redo the `scp -r backend\var\uploads` step in Part 7. |
| Pages are slow for the first ~40 s after a restart | Warm-up still running | Normal. Wait for `warmup_done` in the log. |
| Dashboard is slow every time | VM far from the database | Put the VM in Mumbai, next to Supabase. |
| After moving to a custom domain everyone is signed out | Sign-in cookie belongs to the old address | Expected, once. Also add the new address to `CORS_ORIGINS` and `PUBLIC_APP_URL`. |

---

## Reference: what goes where

**Oracle VM — `~/SupportNova/backend/.env`:** a copy of your laptop's file with these differences:

| Variable | Server value |
|---|---|
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | `<VERCEL_URL>` (comma-separated list, no trailing slash) |
| `CORS_ORIGIN_REGEX` | optional, for preview URLs |
| `PUBLIC_APP_URL` | `<VERCEL_URL>` |
| `SESSION_PROXY_SECRET` | `<PROXY_SECRET>` (new) |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_DEFAULT` | `20/minute` / `600/minute` |
| `JWT_SECRET`, `DATABASE_URL`, AI keys, `EMAIL_*`, `SUPABASE_*` | **unchanged** from the laptop |

**Vercel — Project → Settings → Environment Variables** (Production + Preview):
`NEXT_PUBLIC_API_URL`, `API_URL` (both `https://<API_HOST>`) and `SESSION_PROXY_SECRET`. Nothing else. The frontend holds no API keys.

**Files on the VM:**

| Path | What |
|---|---|
| `/etc/systemd/system/supportnova.service` | the backend service |
| `/etc/caddy/Caddyfile` | HTTPS + reverse proxy |
| `~/SupportNova/backend/.env` | secrets (mode 600) |
| `~/SupportNova/backend/var/uploads/` | uploaded files, **back these up** |
