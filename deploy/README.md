# CrypSavvy backend deployment — Oracle Cloud Always Free + Cloudflare Tunnel (alternative)

> ⚠️ **This is the alternative, self-hosted path.** The **recommended** deployment is
> **Fly.io** — see [FLY-SETUP-GUIDE.md](FLY-SETUP-GUIDE.md). It's simpler (managed `https`/`wss`,
> no server to maintain, Mumbai region) and what the repo's CI (`fly-deploy.yml`) is wired for.
> Use the OCI/VM path below only if you specifically want a self-hosted, $0-forever box and
> don't mind running it yourself.

This path runs the backend as a Docker container on a **free** OCI VM, exposed over
HTTPS/`wss://` by **Cloudflare Tunnel**, redeploying via **GitHub Actions → GHCR → Watchtower**
(its build workflow, `deploy-backend.yml`, is **manual-only** so it doesn't clash with the Fly deploy).

```
GitHub push (main, backend/**)
  └─ Actions: build multi-arch image → push ghcr.io/<owner>/crypsavvy-backend:latest
                                                       │
OCI Always Free VM (ap-mumbai-1, Ubuntu 24.04, Ampere A1 1 OCPU / 6 GB)
  docker compose:
    ├─ backend     uvicorn :8000  (internal only — no published port)
    ├─ cloudflared api.<domain> ⇒ http://backend:8000   (HTTPS + wss, outbound-only)
    └─ watchtower  polls GHCR every 60s, recreates backend
                                                       │
Vercel frontend → NEXT_PUBLIC_API_URL=https://api.<domain>, NEXT_PUBLIC_WS_URL=wss://api.<domain>
```

The DB stays on **Supabase Postgres** — nothing data-related migrates. The VM is
stateless/disposable.

> **Prerequisites:** a GitHub repo for CrypSavvy (CI pushes to its GHCR), and a domain
> added to a free Cloudflare account (for the tunnel hostname).

---

## 1. Provision the OCI VM

1. Sign up at [Oracle Cloud](https://www.oracle.com/cloud/free/). A card is needed for
   identity verification only — **Always Free** resources are never billed.
2. **Home region = `ap-mumbai-1`** (or `ap-hyderabad-1`). ⚠️ This is **permanent** — pick India for low CoinDCX latency.
3. Compute → Create instance:
   - Shape: **Ampere (VM.Standard.A1.Flex)**, **1 OCPU / 6 GB** (inside the free 4 OCPU / 24 GB pool).
   - Image: **Ubuntu 24.04**.
   - Add your **SSH public key**.
   - If you get **"Out of capacity"**, retry over a few hours / try the other AD, or fall
     back to **VM.Standard.E2.1.Micro** (x86, 1 GB — always available, tight for pandas).
4. **Firewall: leave VCN ingress at defaults (SSH/22 only).** Cloudflare Tunnel is
   outbound-only, so **no app port is ever opened**.

## 2. Install Docker on the VM

```bash
ssh ubuntu@<vm-public-ip>
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && exit   # then SSH back in for group to take effect
```

## 3. Create the Cloudflare Tunnel

1. Cloudflare **Zero Trust → Networks → Tunnels → Create a tunnel** (type: *Cloudflared*).
2. Copy the **tunnel token** (the long string after `--token` in the install command).
3. Add a **Public Hostname**:
   - Subdomain `api`, your domain → **Service: `http://backend:8000`**
     (`backend` is the compose service name — cloudflared reaches it over the internal network).
4. WebSockets are enabled by default on the zone — no extra config for `/ws`.

## 4. GHCR pull auth on the VM

The CI image is private by default. Give the VM read access so Watchtower can pull it:

```bash
# GitHub → Settings → Developer settings → PAT (classic) with scope: read:packages
echo <PAT> | docker login ghcr.io -u <github-username> --password-stdin
```

This writes `~/.docker/config.json`, which `docker-compose.yml` mounts into Watchtower.
*(Alternative: make the GHCR package public and delete the config.json volume line — the
image carries no secrets.)*

## 5. Deploy

```bash
mkdir -p ~/crypsavvy && cd ~/crypsavvy
# copy deploy/docker-compose.yml and deploy/.env.example here, then:
cp .env.example .env          # MUST be named .env — Compose auto-loads it
nano .env                     # fill in every value (see notes below)
chmod 600 .env
docker compose up -d
docker compose logs -f backend
```

**Filling in `.env` — reuse the values from Railway:**
- `DATABASE_URL` and **`MASTER_ENCRYPTION_KEY` must be identical to Railway's** — the KEK
  is what decrypts existing users' stored credentials. A new key would orphan them.
- `CF_TUNNEL_TOKEN` = the token from step 3.
- `API_CORS_ORIGINS` must include your exact Vercel origin (no trailing slash).
- `LIVE_TRADING_ENABLED` — leave `false` until you've completed
  [VALIDATION-RUNBOOK.md](VALIDATION-RUNBOOK.md); live mode is refused while it's false.

## 6. Point the frontend at the new backend (Vercel)

In the Vercel project → Settings → Environment Variables, set (then redeploy):

```
NEXT_PUBLIC_API_URL = https://api.<your-domain>
NEXT_PUBLIC_WS_URL  = wss://api.<your-domain>
```

## 7. Monitoring

- Free **UptimeRobot** HTTP(s) check on `https://api.<your-domain>/api/status` — a **401**
  means the app is up (the endpoint requires a JWT). The bot's per-user Telegram alerts
  also keep working.

---

## Verify (end-to-end)

```bash
docker compose ps                         # backend + cloudflared + watchtower => running
docker compose logs -f backend            # "API server starting on port 8000" + a scan every ~5 min
curl -i https://api.<domain>/api/status   # HTTP/2 401 JSON => tunnel → backend works
```

- **WebSocket**: open the Vercel dashboard signed in → DevTools → Network → WS →
  `wss://api.<domain>/ws?ticket=…` shows **101 Switching Protocols** (the Clerk JWT is
  exchanged for a single-use ticket first, never put in the URL), and `price_update`
  events arrive within ~15 s.
- **CI/CD loop**: push a trivial change under `backend/` → Actions builds & pushes to GHCR →
  within ~60s `docker compose logs watchtower` shows it pulling and recreating `backend`.
- **Always-on**: `sudo reboot` → after boot `docker compose ps` shows the stack back up
  (`restart: unless-stopped`); logs show `boot_persisted_users` re-enabling any `bot_enabled` users.

**Cutover:** only after all of the above pass, delete the Railway service.

---

## Day-2 operations

- **Logs filling disk** — Docker's json log driver is unbounded. Add to `/etc/docker/daemon.json`:
  `{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }` then
  `sudo systemctl restart docker`.
- **OS patches** — `sudo apt update && sudo apt upgrade -y` (or enable `unattended-upgrades`).
- **Manual redeploy** — `cd ~/crypsavvy && docker compose pull && docker compose up -d`.
- **Roll back** — pin `BACKEND_IMAGE` to a specific `…:<sha>` tag in `.env` and `docker compose up -d`.
