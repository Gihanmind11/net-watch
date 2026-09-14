# 📡 NetWatch — Network Monitoring System

Real-time LAN monitoring dashboard with device discovery, traffic analysis, alerts, and topology visualization.

## ✨ Highlights

- 🖥️ **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS 4 + Recharts
- ⚙️ **Backend:** FastAPI + Uvicorn + SQLAlchemy 2.0 + APScheduler + WebSockets (JWT auth with access & refresh tokens)
- 🗄️ **Storage:** Supabase — Postgres for users (auth), Storage bucket for the devices/alerts state document and the hourly traffic-history shards
- ⚡ **Realtime:** Redis pub/sub event bus → WebSocket push to the dashboard (in-memory fallback)
- 🔍 **Discovery:** Layered Scapy ARP scan → ICMP ping-sweep fallback → system ARP-cache merge (catches wireless clients that ignore probes)
- 🧰 **Extras:** TCP connect port scanning (no admin rights), optional protocol sniffing, whole-LAN traffic via SNMP, Wi-Fi/hotspot status, psutil bandwidth sampling

## 🛠️ Prerequisites

- 🐍 **Python 3.10+** (backend)
- 🟢 **Node.js 18+** (frontend)
- 🐳 **Docker + Docker Compose** (recommended full-stack run)
- 🛡️ **Admin/root rights + Npcap (Windows) / libpcap** — only for raw Scapy ARP scans; the ping-sweep fallback works without them

## 🚀 Quick Start (Docker — recommended)

One command starts Redis, the FastAPI backend, and the nginx-served frontend. Data lives in
Supabase, so create `backend/.env` with your credentials first (compose reads that file):

```bash
# from the project root
docker compose up --build
```

- 🌐 Dashboard: http://localhost:8080
- 📚 API docs (OpenAPI/Swagger): http://localhost:8000/docs
- 🔑 Login: use an account from the Supabase `users` table (bcrypt-hashed password)

> 💡 Note: for real ARP scans inside Docker, run with `network_mode: host` (Linux) or set `NETWORK_CIDR`
> and rely on the ping-sweep fallback (no admin rights needed).

## 💻 Quick Start (local development)

### 1. Backend 🔧

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
# optional: create a .env file — defaults work out of the box

uvicorn app.main:app --reload --port 8000
```

Supabase is required — there is no local database fallback. Put the project's connection
string in `backend/.env` as `DATABASE_URL` (users/auth), plus `SUPABASE_URL` and
`SUPABASE_SERVICE_KEY` for the devices/alerts state document and the hourly
traffic-history shards. The event bus is in-memory
unless `REDIS_URL` is set.

### 2. Frontend 🎨

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`, so the dashboard
talks to the live backend automatically. Open http://localhost:5173 and log in with an account from the `users` table.

Only real devices are shown. An initial ARP scan
(or ping sweep) runs 1 second after startup and repeats every 30s. On wireless home
networks (broadband routers) clients that ignore ICMP/ARP probes are still picked up
from the system ARP cache, and devices quiet for more than `STALE_DEVICE_GRACE_SEC`
(default 300s) are dropped from the inventory.

### 📡 Whole-LAN traffic (SNMP)

A single host on a switched network only sees the frames on its own link, so the
`Network Traffic (Mbps)` chart cannot measure the whole LAN from OS counters. The
backend instead polls the router/gateway over SNMPv2c (`backend/app/snmp.py`) and
converts its interface counter deltas (`ifInOctets`/`ifOutOctets`) into Mbps. The
chart is labelled `LAN-WIDE` when this succeeds and `THIS HOST` when it falls back
to local `psutil` counters.

Enable SNMP on the router and set at least the community string:

```bash
SNMP_ENABLED=true        # default
SNMP_HOST=               # empty → auto-detected default gateway
SNMP_COMMUNITY=public
SNMP_VERSION=2c          # "1" or "2c"
SNMP_PORT=161
SNMP_INTERFACE=          # empty → auto-pick the router's busiest interface
SNMP_INTERVAL_SEC=5
```

If the router does not answer (SNMP off, wrong community, unsupported device) the
sampler backs off for 5 minutes and the dashboard silently falls back to this
host's traffic — no configuration is required to keep working.

### 📈 Historical traffic (Traffic page)

`/api/bandwidth?minutes=N` serves the series behind the Traffic page's
`Historical Traffic` chart. The backend averages the 2 s samples into 10 s
buckets of this host's interfaces (the same figure the live `Last 60 Seconds`
chart plots) and keeps them in **Supabase Storage**, one JSON document per UTC
hour:

```
netwatch/bandwidth/2026-09-15T10.json
  {"hour": "2026-09-15T10", "bucket_sec": 10,
   "samples": [{"recorded_at": "2026-09-15T10:00:00", "mbps_in": 12.34,
                "mbps_out": 5.67, "bytes_in": 1542500, "bytes_out": 708750}, ...]}
```

Hourly shards keep every upload small (≈35 KB per hour) and make a 6 h range a
handful of object reads. Only the shard of the bucket that just closed is
rewritten — once per 10 s, not once per sample — and the recent shards are read
back into memory at startup, so the chart survives a restart. Long ranges are
averaged down to at most 600 points, and the daily cleanup deletes shards past
the retention window (the equivalent of the TimescaleDB retention policy the
hypertable used to have).

```bash
TRAFFIC_HISTORY_ENABLED=true    # default; false disables recording/reading
TRAFFIC_HISTORY_BUCKET_SEC=10   # seconds per chart point
TRAFFIC_HISTORY_RETENTION_HOURS=48
TRAFFIC_HISTORY_LOAD_HOURS=6    # shards restored into memory at startup
```
### 📶 Wi-Fi status

The dashboard shows the current wireless connection (SSID, BSSID, signal, channel,
link rates, authentication) plus hotspot detection, gathered from OS tools
(`netsh wlan` on Windows, `nmcli`/`iw` on Linux, `airport` on macOS). No admin
rights are needed, and every field degrades gracefully on Ethernet-only or
headless machines.

## 📁 Project Structure

```
Network Monitoring System/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app, CORS, lifespan (DB, scheduler, broker)
│   │   ├── config.py      # Environment-driven settings
│   │   ├── database.py    # SQLAlchemy engine bound to Supabase Postgres
│   │   ├── models.py      # SQLAlchemy models (Supabase `users` table)
│   │   ├── store.py       # Devices/alerts state document in Supabase Storage
│   │   ├── traffic_history.py # Hourly traffic-history shards in Supabase Storage
│   │   ├── security.py    # JWT auth (PBKDF2 password hashing)
│   │   ├── scanner.py     # Scapy ARP scan → ping-sweep fallback → ARP-cache merge + port scan
│   │   ├── monitor.py     # psutil bandwidth sampler + optional protocol sniffer
│   │   ├── snmp.py        # dependency-free SNMPv2c client + gateway LAN traffic sampler
│   │   ├── wifi.py        # Wi-Fi / hotspot status via OS commands
│   │   ├── events.py      # Redis pub/sub event bus (in-memory fallback)
│   │   ├── services.py    # Scan/ping/bandwidth jobs, alert rules, payloads
│   │   ├── scheduler.py   # APScheduler background jobs
│   │   └── api/           # auth, devices, alerts, bandwidth, topology, stats, scan, wifi, ws
│   ├── tests/             # Unit tests (device classifier, traffic history)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx        # Main app with auth + page routing
│   │   ├── api.ts         # HTTP + WebSocket client for the FastAPI backend
│   │   ├── types.ts       # Shared TypeScript types
│   │   ├── components/    # Shared components (TopBar, Sidebar, KpiCard, StatusBadge, …)
│   │   └── pages/         # Dashboard, Devices, Topology, Traffic, Performance, Alerts, About
│   ├── Dockerfile         # Multi-stage build → nginx (+ /api and /ws proxy)
│   ├── nginx.conf
│   └── package.json
├── docker-compose.yml     # Redis + backend + frontend (Supabase is the datastore)
├── network-monitor.html   # Standalone static prototype (no framework)
├── PRD.md                 # Product Requirements Document
├── how to run.txt         # Quick run instructions
└── README.md
```

## 🔌 API Overview

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | — | JWT login (returns access + refresh tokens) |
| POST | `/api/auth/refresh` | — | Refresh an expired access token |
| POST | `/api/auth/logout` | — | Logout |
| GET | `/api/devices` | — | Device inventory |
| GET | `/api/devices/{ip}` | — | Single device detail |
| DELETE | `/api/devices` | Bearer | Reset the inventory |
| POST | `/api/scan` | Bearer | Trigger a discovery scan |
| GET | `/api/alerts` | — | Active alerts |
| DELETE | `/api/alerts/{id}` | Bearer | Resolve an alert |
| DELETE | `/api/alerts` | Bearer | Resolve all alerts |
| GET | `/api/bandwidth` | — | Current rates, historical series (`?minutes=`, default 5), protocol distribution |
| GET | `/api/bandwidth/interfaces` | — | Interface statistics |
| GET | `/api/bandwidth/top-talkers` | — | Top bandwidth consumers |
| GET | `/api/topology` | — | Topology nodes/edges |
| GET | `/api/stats` | — | KPI statistics |
| GET | `/api/wifi` | — | Wi-Fi connection & hotspot status |
| WS | `/ws` | — | Real-time events (snapshot + updates) |

Interactive docs: http://localhost:8000/docs

## ⏱️ Background Jobs (APScheduler)

| Job | Interval | Work |
|-----|----------|------|
| Scan | 30s | ARP/ping + ARP-cache discovery, port scan, new-device alerts, stale-device cleanup |
| Ping | 5s | Status, latency, uptime %, latency/offline alerts; ARP-entry fallback keeps ICMP-blocking devices "up" |
| Bandwidth | 2s | Sample per-interface rates → 10 s history buckets → hourly Supabase Storage shards |
| LAN Traffic | 5s | Poll the router via SNMP → LAN-wide Mbps (local `psutil` fallback) |
| Cleanup | daily 03:00 | Purge logs and traffic-history shards past the retention window |

An initial scan also runs 1 second after startup.

## 📜 Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the frontend dev server (proxies to backend) |
| `npm run build` | Type-check and build for production |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview the production build locally |

## 📝 Notes

- The dashboard polls every 5s as a fallback and receives push updates via `/ws` for instant refreshes.
- `network-monitor.html` is a self-contained static prototype of the same UI.
- The dashboard only ever shows devices found by real scans.
- Change `SECRET_KEY` for anything real.
