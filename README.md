# NetWatch — Network Monitoring System

Real-time LAN monitoring dashboard with device discovery, traffic analysis, alerts, and topology visualization.

## Prerequisites

- **Python 3.10+** — [Download Python](https://www.python.org/downloads/)
- **Node.js 16+** — [Download Node.js](https://nodejs.org/)
- **Administrator/Root privileges** — Required for ARP scanning (Scapy)

## Quick Start

### 1. Backend (Flask API)

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Start the server (requires admin/root for ARP scanning)
python app.py
```

The API starts at `http://localhost:5000`.

### 2. Frontend (React Dashboard)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

The dashboard opens at `http://localhost:3000`.

## Project Structure

```
Network Monitoring System/
├── backend/
│   ├── app.py          # Flask REST API
│   ├── scanner.py      # ARP scan + ICMP ping (Scapy)
│   ├── monitor.py      # Bandwidth monitoring (psutil) + scheduler
│   ├── database.py     # SQLite database layer
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx     # Main app with routing
│   │   ├── App.css     # Dark theme styles
│   │   ├── components/ # Shared components
│   │   └── pages/      # Dashboard, Devices, Topology, Traffic, etc.
│   └── package.json
├── PRD.md              # Product Requirements Document
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | All discovered devices |
| GET | `/api/devices/<ip>` | Single device details |
| POST | `/api/scan` | Trigger manual ARP scan |
| GET | `/api/alerts` | Active alerts with counts |
| GET | `/api/bandwidth` | Current bandwidth + history |
| GET | `/api/topology` | Topology nodes/edges |
| GET | `/api/stats` | KPI summary statistics |
| GET | `/api/interfaces` | Interface card data |
| GET | `/api/protocols` | Protocol distribution |
| GET | `/api/top-talkers` | Top bandwidth consumers |
| GET | `/api/pdu-simulation` | PDU simulation steps |

## Features

- **Device Discovery** — ARP scanning to find all LAN devices
- **Real-time Monitoring** — Auto-refresh every 30 seconds
- **Dashboard** — KPI cards, bandwidth charts, status donut, alerts
- **Device Inventory** — Searchable table with status, latency, uptime
- **Network Topology** — Interactive canvas-based visualization
- **Traffic Analysis** — Bandwidth charts, protocol distribution, top talkers
- **Performance Metrics** — Interface stats, latency charts, packet loss
- **Alert System** — Critical, warning, and info alerts
- **About Page** — Project details, tech stack, objectives

## Notes

- Scapy requires **administrator/root** privileges for raw packet operations
- If Scapy is unavailable, the system falls back to ping-based discovery
- The dashboard auto-polls the API every 5 seconds for live updates
- SQLite database (`netmon.db`) is created automatically on first run
