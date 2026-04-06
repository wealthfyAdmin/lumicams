# Lumicams

AI-powered video surveillance stack: **FastAPI** backend (RTSP ingestion, YOLO/tracking, face pipeline, WebSocket alerts) and **Next.js** dashboard. Data lives in **PostgreSQL**.

This document covers **local development**, **VPS production** deployment, and **suggested server sizes** when selling deployments (about **10 cameras per client site**).

---

## Architecture (quick)

| Layer | Stack | Notes |
|--------|--------|--------|
| API & inference | Python 3.11–3.12 (recommended), FastAPI, Uvicorn | Keep **one inference process** per server (see VPS section). |
| Frontend | Node 18+, Next.js 14 | `next dev` locally; `next build` + `next start` in production. |
| Database | PostgreSQL 14+ | Connection string via `DATABASE_URL`. |
| Realtime | WebSocket `/ws/alerts` | Proxied through Next rewrites in dev; reverse proxy must support WebSockets in prod. |

---

## Prerequisites

- **PostgreSQL** (local or remote).
- **Python** 3.11 or 3.12 for best compatibility (MediaPipe fall detection; Python 3.13 on Windows may omit MediaPipe—backend degrades gracefully).
- **Node.js** 18+ and npm.
- **FFmpeg** libraries (usually pulled in with OpenCV); on Ubuntu: `sudo apt install ffmpeg libsm6 libxext6`.
- **YOLO / PPE model files** (`.pt`) placed where `backend/.env` points (e.g. under `backend/models/`).

---

## Local machine — setup steps

### 1. PostgreSQL

Create a database and user (example):

```sql
CREATE USER aegis_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE aegis_eye OWNER aegis_user;
```

### 2. Backend

```bash
cd backend
python -m venv venv
```

**Windows:** `venv\Scripts\activate`  
**Linux/macOS:** `source venv/bin/activate`

```bash
pip install -r requirements.txt
```

Create `backend/.env` (minimal example — adjust paths and secrets):

```env
DATABASE_URL=postgresql://aegis_user:your_secure_password@localhost:5432/aegis_eye
SECRET_KEY=use-a-long-random-string-in-production
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

DEFAULT_ADMIN_EMAIL=admin@aegis.local
DEFAULT_ADMIN_PASSWORD=ChangeMeOnFirstLogin

# Models (examples — use your actual filenames)
PERSON_DETECT_MODEL=yolov5su.pt
YOLO_FIRE_MODEL=yolov5su.pt
YOLO_PPE_MODEL=models/your_ppe_primary.pt
YOLO_PPE_AUX_MODEL=models/your_ppe_aux.pt

SNAPSHOT_DIR=snapshots
```

Run the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/api/docs`  
On first start, tables are created and a default admin is seeded if no users exist.

### 3. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local` so Next.js can proxy API and WebSocket to the backend (`next.config.js` uses `BACKEND_URL` / `NEXT_PUBLIC_BACKEND_URL`, default `http://localhost:8000`):

```env
BACKEND_URL=http://localhost:8000
# Optional: if the browser must call the API on another origin
# NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

Run:

```bash
npm run dev
```

Open `http://localhost:3000`, log in with `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`, then change the password and production secrets.

### 4. Cameras

Add cameras in the UI with valid **RTSP URLs**. Start a stream from the dashboard; inference runs in the backend process.

---

## VPS — production deployment (example: Ubuntu 22.04)

### 0. DNS and firewall

- Point a hostname (e.g. `app.client.com`) to the VPS public IP.
- Open **80** and **443** for HTTP/S; **22** for SSH (restrict by IP if possible).
- RTSP is usually **outbound** from server to cameras (or cameras push to your recorder — match your network design).

### 1. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y postgresql postgresql-contrib nginx certbot python3-certbot-nginx \
  python3.12-venv python3-pip ffmpeg libsm6 libxext6 git
```

Use PostgreSQL locally or a managed DB; set `DATABASE_URL` accordingly.

### 2. Deploy application

Example layout: `/opt/aegis-eye` (clone or upload your release).

**Backend**

```bash
cd /opt/aegis-eye/backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set `backend/.env` with production values:

- Strong `SECRET_KEY`, real `DATABASE_URL`.
- `ALLOWED_ORIGINS=https://app.client.com` (no trailing issues — exact browser origin).
- Model paths and thresholds.
- **Do not** commit `.env`.

**Important:** Run the backend with **a single worker** so one process owns all `VideoProcessor` threads (multiple workers duplicate state and break camera handling):

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 proxy-headers
```

Use **systemd** to keep it running (example unit `/etc/systemd/system/aegis-api.service`):

```ini
[Unit]
Description=Lumicams API
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/aegis-eye/backend
Environment=PATH=/opt/aegis-eye/backend/venv/bin
ExecStart=/opt/aegis-eye/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aegis-api
```

**Frontend**

```bash
cd /opt/aegis-eye/frontend
npm ci
```

Production `frontend/.env.local` (or environment for the build):

```env
BACKEND_URL=http://127.0.0.1:8000
```

Build and run:

```bash
npm run build
```

Run with systemd (example `aegis-web.service`):

```ini
[Unit]
Description=Lumicams Next.js
After=network.target aegis-api.service

[Service]
User=www-data
WorkingDirectory=/opt/aegis-eye/frontend
ExecStart=/usr/bin/npm run start -- -p 3000
Restart=always
Environment=NODE_ENV=production
Environment=BACKEND_URL=http://127.0.0.1:8000

[Install]
WantedBy=multi-user.target
```

### 3. Nginx reverse proxy (TLS + WebSockets)

Terminates HTTPS and forwards to Next.js; Next’s own rewrites forward `/api`, `/ws`, `/snapshots` to Uvicorn. Ensure WebSocket upgrade headers are set for `/ws/`.

Example server block (after `certbot --nginx`):

- `proxy_pass` to `http://127.0.0.1:3000` for the site.
- For `/ws/`, set `Upgrade` and `Connection "upgrade"` headers (same upstream as Next, or proxy `/api` and `/ws` directly to `8000` if you prefer — both work if configured consistently with `ALLOWED_ORIGINS` and cookies).

Verify:

- `https://app.client.com` loads the UI.
- Login works; live alerts connect (WebSocket).

### 4. Hardening checklist

- Change default admin password; use strong user passwords.
- Rotate `SECRET_KEY`; restrict `ALLOWED_ORIGINS` to real domains.
- Set `ENVIRONMENT=production` (enables stricter defaults: API docs off, WebSocket JWT required unless overridden).
- Use `WS_REQUIRE_TOKEN=true` in production so `/ws/alerts` requires `?token=` (the dashboard already sends it).
- Optional `TRUSTED_HOSTS` when the API is exposed directly (normally nginx terminates TLS and forwards a safe Host).
- Monitor `GET /api/health` (returns **503** if PostgreSQL is down).
- Regular PostgreSQL backups; snapshot disk for disaster recovery.
- Log rotation for journald / nginx; monitor disk (snapshots and logs grow).
- Optional: GPU drivers + CUDA if you add a discrete GPU for inference.

---

## Docker (API + web)

Templates: `backend/.env.example`, `frontend/.env.example`, root `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`.

1. Create `backend/.env` from the example and set **`DATABASE_URL`**, **`SECRET_KEY`**, **`ALLOWED_ORIGINS`** (e.g. `http://localhost:3000` for local compose).
2. Build and run: `docker compose up --build -d`
3. API health: `http://localhost:8000/api/health` — UI: `http://localhost:3000`

**Important:** The inference service must run **one Uvicorn worker** (already set in the Dockerfile). PostgreSQL is not bundled—use your managed DB or install Postgres on the host and point `DATABASE_URL` at it.

Rebuild the **web** image when you change **`NEXT_PUBLIC_API_URL`** (it is applied at build time). For a public HTTPS domain, pass the correct API URL as a build arg to match how browsers reach the API.

---

## Selling the product — server configuration **per client (~10 cameras)**

Use these as **starting baselines**. Real needs depend on resolution (720p vs 1080p), FPS, how many modules are ON per camera (fire, crowd, PPE dual-model, face), and `INFER_EVERY_N_FRAMES` in `backend/.env`.

### Entry: CPU-only (pilot / cost-sensitive)

| Resource | Recommendation |
|----------|----------------|
| **vCPU** | 16 (dedicated or cloud “compute optimized”) |
| **RAM** | 32 GB |
| **Disk** | 100 GB SSD (OS, models, DB, snapshots) |
| **GPU** | None |
| **Network** | ≥ 100 Mbps symmetric; stable RTSP path to cameras |

Expect to tune: fewer modules per camera, higher `INFER_EVERY_N_FRAMES`, lower resolution streams, or fewer concurrent cameras if CPU saturates.

### Recommended: **GPU-assisted** (smooth 10-camera production)

| Resource | Recommendation |
|----------|----------------|
| **vCPU** | 8–16 |
| **RAM** | 32–64 GB |
| **GPU** | NVIDIA **RTX 4060 / 4060 Ti** (8 GB VRAM) or better; datacenter **L4 / T4** class for multi-tenant |
| **Disk** | 100–250 GB NVMe |
| **Network** | 1 Gbps or Wi-Fi AP isolated; ~4–8 Mbps sustained per 1080p RTSP stream typical |

GPU runs PyTorch/ONNX workloads; CPU handles decode, tracking glue, and API.

### Database

- **Small single-site (10 cams):** PostgreSQL on the same VPS is acceptable with 32 GB RAM and tuned backups.
- **Multi-tenant SaaS:** managed PostgreSQL + separate **inference** workers per tenant or region.

### Bandwidth rule of thumb

- **~2–4 Mbps** per 720p RTSP stream; **~4–8 Mbps** per 1080p (variable by codec).  
- **10 × 1080p** ≈ **40–80 Mbps** ingress to the server if all streams terminate at this host.

### Licensing and ops (your business)

- One deployment per client VM is simple to support and bill (per camera / per module tier).
- Quote **GPU** for any client enabling **PPE + face + crowd** together on **10× 1080p** streams.
- Offer a **site survey**: network latency to RTSP, peak headcount, and required retention for snapshots/alerts drive disk and compliance.

---

## Useful environment variables (backend)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing (must be strong in production) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (frontend URLs) |
| `ENVIRONMENT` / `AEGIS_ENV` | `production` → docs off by default; WebSocket JWT on by default |
| `DOCS_ENABLED` | `true`/`false` — override OpenAPI `/api/docs` visibility |
| `WS_REQUIRE_TOKEN` | `true`/`false` — require JWT on `/ws/alerts` |
| `TRUSTED_HOSTS` | Optional comma-separated Host headers (direct exposure) |
| `APP_VERSION` | Shown in `/api/health` |
| `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD` | First bootstrap admin |
| `SNAPSHOT_DIR` | Where alert snapshots are stored |
| `YOLO_FIRE_MODEL`, `PERSON_DETECT_MODEL`, `YOLO_PPE_MODEL`, `YOLO_WEAPON_MODEL` | Model paths |
| `PERSON_COUNT_CONF_MIN`, `CROWD_OVERCROWD_ALERT_MIN_INTERVAL_SECONDS`, … | Crowd / person tuning (see `backend/.env.example`) |
| `INFER_EVERY_N_FRAMES` | Run heavy inference every N frames (higher = less CPU/GPU load) |
| `OPENAI_API_KEY`, `VLM_ENABLED`, `VLM_MODEL` | Alert verification (VLM) |

Full template: **`backend/.env.example`**. Code defaults: `backend/app/inference.py`, `backend/app/database.py`, `backend/app/vlm_service.py`.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Frontend 401 / CORS | `ALLOWED_ORIGINS` must match the exact browser URL (scheme + host + port). |
| WebSocket disconnects | Nginx must pass `Upgrade` / `Connection` for `/ws/`; only one backend worker. |
| PPE / fire “not loading” | Model path in `.env`; files exist on server; read permissions for service user. |
| High CPU | Increase `INFER_EVERY_N_FRAMES`; reduce resolution; disable unused per-camera modules; add GPU. |
| Fall detection missing on Windows Py 3.13 | Use Python 3.11/3.12 with MediaPipe, or accept fall module off. |

---

## License

Proprietary / your choice — set terms before selling deployments.
