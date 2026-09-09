# NetWatch — Network Monitoring System

Real-time LAN monitoring dashboard with device discovery, traffic analysis, alerts, and topology visualization.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind + Recharts
- **Backend:** FastAPI + Uvicorn + SQLAlchemy 2.0 + APScheduler + WebSockets
- **Storage:** PostgreSQL + TimescaleDB (hypertables) — SQLite fallback for dev
- **Realtime:** Redis pub/sub event bus → WebSocket push to the dashboard (in-memory fallback)
- **Discovery:** Scapy ARP scan → ICMP ping-sweep fallback → system ARP-cache merge (catches wireless clients that ignore probes) → psutil bandwidth sampling

## Prerequisites

- **Python 3.10+** (backend)
- **Node.js 18+** (frontend)
- **Docker + Docker Compose** (recommended full-stack run)
- **Admin/root rights + Npcap (Windows) / libpcap** — only for raw Scapy ARP scans; the ping-sweep fallback works without them

## Quick Start (Docker — recommended)

One command starts PostgreSQL (TimescaleDB), Redis, the FastAPI backend, and the nginx-served frontend:

```bash
# from the project root
docker compose up --build
```

- Dashboard: http://localhost:8080
- API docs (OpenAPI/Swagger): http://localhost:8000/docs
- Login: `admin` / `admin` (configurable via `DEMO_USER` / `DEMO_PASSWORD` env vars)

> Note: for real ARP scans inside Docker, run with `network_mode: host` (Linux) or set `NETWORK_CIDR`
> and rely on the ping-sweep fallback (no admin rights needed).

## Quick Start (local development)

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
cp .env.example .env          # optional; defaults work out of the box

uvicorn app.main:app --reload --port 8000
```

Defaults: SQLite database (`netmon.db`) + in-memory event bus — zero external dependencies.
For TimescaleDB + Redis, point `DATABASE_URL` / `REDIS_URL` at `docker compose up db redis` services.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`, so the dashboard
talks to the live backend automatically. Open http://localhost:5173 and log in with `admin` / `admin`.

Demo seeding is disabled by default, so only real devices are shown. An initial ARP scan
(or ping sweep) runs 1 second after startup and repeats every 30s. On wireless home
networks (broadband routers) clients that ignore ICMP/ARP probes are still picked up
from the system ARP cache, and devices quiet for more than `STALE_DEVICE_GRACE_SEC`
(default 300s) are dropped from the inventory.

## Project Structure

```
Network Monitoring System/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app, CORS, lifespan (DB, scheduler, broker)
│   │   ├── config.py      # Environment-driven settings
│   │   ├── database.py    # SQLAlchemy engine + TimescaleDB hypertable setup
│   │   ├── models.py      # devices, ping_history, alerts, bandwidth_logs
│   │   ├── security.py    # JWT auth (PBKDF2 password hashing)
│   │   ├── scanner.py     # Scapy ARP scan → ping-sweep fallback → ARP-cache merge
│   │   ├── monitor.py     # psutil bandwidth sampler + optional protocol sniffer
│   │   ├── events.py      # Redis pub/sub event bus (in-memory fallback)
│   │   ├── services.py    # Scan/ping/bandwidth jobs, alert rules, payloads
│   │   ├── scheduler.py   # APScheduler background jobs
│   │   └── api/           # auth, devices, alerts, bandwidth, topology, stats, scan, ws
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.tsx        # Main app with auth + page routing
│   │   ├── api.ts         # HTTP + WebSocket client for the FastAPI backend
│   │   ├── types.ts       # Shared TypeScript types
│   │   ├── components/    # Shared components (TopBar, Sidebar, KpiCard, etc.)
│   │   └── pages/         # Dashboard, Devices, Topology, Traffic, Alerts, etc.
│   ├── Dockerfile         # Multi-stage build → nginx (+ /api and /ws proxy)
│   ├── nginx.conf
│   └── package.json
├── docker-compose.yml     # TimescaleDB + Redis + backend + frontend
├── network-monitor.html   # Standalone static prototype (no framework)
├── PRD.md                 # Product Requirements Document
└── README.md
```

## API Overview

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | — | JWT login |
| GET | `/api/devices` | — | Device inventory |
| POST | `/api/scan` | Bearer | Trigger a discovery scan |
| GET | `/api/alerts` | — | Active alerts |
| DELETE | `/api/alerts/<id>` | Bearer | Resolve an alert |
| GET | `/api/bandwidth` | — | Current rates, history, protocol distribution |
| GET | `/api/bandwidth/interfaces` | — | Interface statistics |
| GET | `/api/bandwidth/top-talkers` | — | Top bandwidth consumers |
| GET | `/api/topology` | — | Topology nodes/edges |
| GET | `/api/stats` | — | KPI statistics |
| WS | `/ws` | — | Real-time events (snapshot + updates) |

Interactive docs: http://localhost:8000/docs

## Background Jobs (APScheduler)

| Job | Interval | Work |
|-----|----------|------|
| Scan | 30s | ARP/ping + ARP-cache discovery, new-device alerts, stale-device cleanup |
| Ping | 10s | Status, latency, uptime %, latency/offline alerts; ARP-entry fallback keeps ICMP-blocking devices "up" |
| Bandwidth | 2s | Sample per-interface rates → `bandwidth_logs` |
| Cleanup | daily 03:00 | Purge logs past retention window |

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the frontend dev server (proxies to backend) |
| `npm run build` | Type-check and build for production |
| `npm run lint` | Run ESLint |

## Notes

- The dashboard polls every 5s as a fallback and receives push updates via `/ws` for instant refreshes.
- `network-monitor.html` is a self-contained static prototype of the same UI.
- Demo seeding is disabled by default (`DEMO_SEED_ENABLED=false`), so the dashboard only ever shows devices found by real scans.
- All passwords/credentials are LAN-demo defaults — change `DEMO_PASSWORD` and `SECRET_KEY` for anything real.