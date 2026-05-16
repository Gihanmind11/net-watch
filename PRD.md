# Product Requirements Document (PRD)
## Network Monitoring System with Real-Time Dashboard

---

| Field              | Details                                      |
|--------------------|----------------------------------------------|
| **Document Title** | Product Requirements Document (PRD)          |
| **Project Title**  | Network Monitoring System with Real-Time Dashboard |
| **Student**        | S.W.G Mindana                                |
| **Index Number**   | GAL/2324/IT/F/0113                           |
| **Programme**      | Higher National Diploma — Information Technology |
| **Institute**      | Advanced Technological Institute, Galle      |
| **Supervisor**     | Mr. Chamith Samarawickrama                   |
| **Contact**        | 0769226443                                   |
| **Email**          | gihanmindana8@gmail.com                      |
| **Version**        | 1.0.0                                        |
| **Date**           | May 2026                                     |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Goals and Objectives](#3-goals-and-objectives)
4. [Scope](#4-scope)
5. [Stakeholders](#5-stakeholders)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [System Architecture](#8-system-architecture)
9. [Technology Stack](#9-technology-stack)
10. [Feature Specifications](#10-feature-specifications)
11. [User Interface Requirements](#11-user-interface-requirements)
12. [Data Requirements](#12-data-requirements)
13. [API Specifications](#13-api-specifications)
14. [Cisco Packet Tracer Integration](#14-cisco-packet-tracer-integration)
15. [Alert System Specification](#15-alert-system-specification)
16. [Project Timeline](#16-project-timeline)
17. [Limitations and Constraints](#17-limitations-and-constraints)
18. [Expected Outcomes](#18-expected-outcomes)
19. [Risks and Mitigation](#19-risks-and-mitigation)
20. [References](#20-references)

---

## 1. Project Overview

Modern computer networks consist of multiple connected devices such as laptops, smartphones, servers, and IoT devices. Monitoring these devices is essential to ensure network security, performance, and efficient resource utilization.

This document defines the complete product requirements for the **Network Monitoring System with Real-Time Dashboard** — a web-based system that monitors and visualizes network devices in real time within a Local Area Network (LAN). The system integrates a Python-based network scanner (Scapy), a Flask REST API backend, a React.js frontend dashboard, and Cisco Packet Tracer for network topology simulation and visualization.

### 1.1 Product Vision

To provide a simplified, user-friendly, and educational network monitoring solution that gives real-time visibility into LAN devices, traffic, and health — without the complexity of enterprise tools like Wireshark.

---

## 2. Problem Statement

In small-scale networks such as university labs or office environments, administrators frequently face difficulties in:

- **Identifying connected devices** — no easy way to see what is on the network
- **Monitoring network activity** — no live view of bandwidth or latency
- **Detecting unauthorized access** — new or unknown devices go unnoticed
- **Complexity of existing tools** — tools like Wireshark require advanced networking knowledge
- **Lack of integrated simulation** — no connection between theoretical topology design and real monitoring

There is a clear need for a simplified, educational, and visual network monitoring tool tailored for beginners and small network environments.

---

## 3. Goals and Objectives

### 3.1 Main Objective

To develop a web-based system that monitors and visualizes network devices on a LAN in real time via a modern React dashboard.

### 3.2 Specific Objectives

| # | Objective | Priority |
|---|-----------|----------|
| 1 | Detect all devices connected to the LAN using ARP scanning | Must Have |
| 2 | Display IP address, MAC address, and hostname per device | Must Have |
| 3 | Identify and report device status (online / offline) | Must Have |
| 4 | Monitor basic bandwidth usage per interface | Must Have |
| 5 | Detect new/unauthorized devices and generate alerts | Must Have |
| 6 | Provide a modern, interactive dashboard using React.js | Must Have |
| 7 | Simulate and visualize network topology using Cisco Packet Tracer | Must Have |
| 8 | Basic OS detection per device | Should Have |
| 9 | Store historical scan data in SQLite database | Should Have |
| 10 | Export device reports to CSV/PDF | Nice to Have |

---

## 4. Scope

### 4.1 In Scope

- LAN-based device discovery using ARP (Address Resolution Protocol)
- Real-time device status monitoring (ICMP ping)
- Bandwidth and traffic monitoring per network interface
- Alert system for threshold breaches and new device detection
- React.js web dashboard with charts, tables, and topology view
- Flask REST API connecting backend scanner to frontend
- SQLite database for data persistence
- Cisco Packet Tracer simulation for topology visualization

### 4.2 Out of Scope

- WAN / Internet monitoring
- Deep packet inspection (DPI)
- Mobile application
- SNMP-based monitoring
- Active exploitation or penetration testing features
- Multi-network / VLAN monitoring

---

## 5. Stakeholders

| Stakeholder | Role | Interest |
|-------------|------|----------|
| S.W.G Mindana | Developer / Student | Build and deliver the project |
| Mr. Chamith Samarawickrama | Supervisor | Academic oversight and evaluation |
| SLIATE Examiners | Evaluators | Grade the final submission |
| Network Administrators (target users) | End Users | Monitor and manage the LAN |
| Students / Lab Users | Secondary Users | Learn network monitoring concepts |

---

## 6. Functional Requirements

### 6.1 Device Discovery

| ID | Requirement |
|----|-------------|
| FR-01 | The system SHALL scan the LAN using ARP requests to discover all connected hosts |
| FR-02 | The system SHALL retrieve IP address, MAC address, and hostname for each discovered device |
| FR-03 | The system SHALL allow manual on-demand scans triggered by the user |
| FR-04 | The system SHALL support automatic periodic scanning at configurable intervals |
| FR-05 | The system SHALL display the total count of discovered devices on the dashboard |

### 6.2 Device Status Monitoring

| ID | Requirement |
|----|-------------|
| FR-06 | The system SHALL ping each discovered device using ICMP to determine online/offline status |
| FR-07 | The system SHALL display real-time ping latency (ms) per device |
| FR-08 | The system SHALL calculate and display uptime percentage per device |
| FR-09 | The system SHALL mark a device as offline after 3 consecutive failed ping attempts |
| FR-10 | The system SHALL refresh device status every 30 seconds automatically |

### 6.3 Bandwidth & Traffic Monitoring

| ID | Requirement |
|----|-------------|
| FR-11 | The system SHALL monitor inbound and outbound bandwidth (Mbps) per network interface |
| FR-12 | The system SHALL display a real-time rolling bandwidth chart (last 60 seconds) |
| FR-13 | The system SHALL show protocol distribution (TCP, UDP, HTTP, HTTPS, DNS, ICMP, ARP) |
| FR-14 | The system SHALL identify and display the top-5 bandwidth-consuming devices (Top Talkers) |
| FR-15 | The system SHALL display per-interface statistics (speed, errors, drops) |

### 6.4 Alert System

| ID | Requirement |
|----|-------------|
| FR-16 | The system SHALL generate a CRITICAL alert when a device becomes unreachable |
| FR-17 | The system SHALL generate a WARNING alert when device latency exceeds a configurable threshold (default: 30ms) |
| FR-18 | The system SHALL generate a NEW DEVICE alert when an unknown MAC address is detected on the network |
| FR-19 | The system SHALL display all active alerts in an Alert Center page |
| FR-20 | The system SHALL show alert level (Critical / Warning / New Device / Info), message, and timestamp |

### 6.5 Dashboard & UI

| ID | Requirement |
|----|-------------|
| FR-21 | The system SHALL display a summary dashboard with KPI cards (total devices, online, offline, avg latency, new devices) |
| FR-22 | The system SHALL provide a sidebar navigation with: Dashboard, Devices, Topology, Traffic, Performance, Alerts |
| FR-23 | The system SHALL include a Device Inventory table with search/filter functionality |
| FR-24 | The system SHALL display a Network Topology visualization panel |
| FR-25 | The system SHALL show a live clock and system status in the top bar |

### 6.6 Topology Visualization

| ID | Requirement |
|----|-------------|
| FR-26 | The system SHALL render a visual network topology diagram showing all discovered nodes |
| FR-27 | The topology SHALL represent the Cisco Packet Tracer simulation layout |
| FR-28 | Nodes SHALL be color-coded: green (online), red (offline), yellow (warning), purple (new/unknown) |
| FR-29 | The user SHALL be able to click on any topology node to view device details |
| FR-30 | The system SHALL include a PDU simulation log showing packet flow steps |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| ID | Requirement |
|----|-------------|
| NFR-01 | Dashboard SHALL load within 3 seconds on a standard LAN |
| NFR-02 | Live bandwidth chart SHALL update every 2 seconds with no visible lag |
| NFR-03 | ARP scan of a /24 subnet SHALL complete within 10 seconds |
| NFR-04 | API response time SHALL be under 500ms for all endpoints |

### 7.2 Usability

| ID | Requirement |
|----|-------------|
| NFR-05 | The interface SHALL be usable by someone with basic networking knowledge |
| NFR-06 | All status indicators SHALL use intuitive color coding (green/yellow/red) |
| NFR-07 | The dashboard SHALL be responsive and work on screens ≥ 1280px wide |

### 7.3 Reliability

| ID | Requirement |
|----|-------------|
| NFR-08 | The system SHALL continue monitoring even if one device scan fails |
| NFR-09 | SQLite database SHALL persist scan history across application restarts |

### 7.4 Security

| ID | Requirement |
|----|-------------|
| NFR-10 | The system SHALL only operate within the local LAN — no external network access |
| NFR-11 | The system SHALL NOT collect or transmit personal data |
| NFR-12 | ARP scanning SHALL only be used for discovery, not exploitation |

### 7.5 Maintainability

| ID | Requirement |
|----|-------------|
| NFR-13 | Code SHALL be modular — scanner, API, and frontend are independent layers |
| NFR-14 | The project SHALL include a README with setup and run instructions |

---

## 8. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LOCAL AREA NETWORK (LAN)              │
│   Devices: PCs, Servers, Printers, Cameras, APs, IoT    │
└───────────────────────┬─────────────────────────────────┘
                        │ ARP / ICMP
                        ▼
┌─────────────────────────────────────────────────────────┐
│           CISCO PACKET TRACER (Simulation)               │
│    Network topology design & PDU packet flow simulation  │
└───────────────────────┬─────────────────────────────────┘
                        │ Topology Export / Reference
                        ▼
┌─────────────────────────────────────────────────────────┐
│              PYTHON NETWORK SCANNER (Scapy)              │
│  - ARP scan for device discovery                        │
│  - ICMP ping for status & latency                       │
│  - psutil for bandwidth/interface stats                 │
│  - Scheduled periodic scanning (APScheduler)            │
└───────────────────────┬─────────────────────────────────┘
                        │ Writes to / Reads from
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  SQLITE DATABASE                         │
│  Tables: devices, scan_history, alerts, bandwidth_logs  │
└───────────────────────┬─────────────────────────────────┘
                        │ ORM / SQL Queries
                        ▼
┌─────────────────────────────────────────────────────────┐
│               FLASK REST API (Backend)                   │
│  Endpoints: /devices, /alerts, /bandwidth, /scan, /topo  │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP / JSON
                        ▼
┌─────────────────────────────────────────────────────────┐
│             REACT.JS DASHBOARD (Frontend)                │
│  Pages: Dashboard, Devices, Topology, Traffic,          │
│         Performance, Alerts, About                      │
│  Charts: recharts (AreaChart, BarChart, PieChart)       │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Technology Stack

### 9.1 Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React.js | 18.x | UI framework (component-based) |
| Recharts | 2.x | Charts and data visualization |
| CSS-in-JS / Tailwind | — | Styling |
| Fetch API | — | HTTP requests to Flask API |

### 9.2 Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Core backend language |
| Flask | 2.x | REST API framework |
| Flask-CORS | — | Cross-origin requests from React |
| APScheduler | 3.x | Periodic scan scheduling |

### 9.3 Networking Tools

| Technology | Purpose |
|------------|---------|
| Scapy | ARP scanning and packet analysis |
| psutil | Network interface bandwidth stats |
| socket | Hostname resolution |
| subprocess (ping) | ICMP latency measurement |
| Cisco Packet Tracer | Network simulation and topology design |

### 9.4 Database & Storage

| Technology | Purpose |
|------------|---------|
| SQLite | Lightweight local data storage |
| SQLAlchemy (optional) | ORM for database interaction |

---

## 10. Feature Specifications

### 10.1 ARP Scanner Module

```
Input:  Network CIDR (e.g., 192.168.1.0/24)
Output: List of {ip, mac, hostname, status, ping_ms}
Method: Scapy ARP broadcast → collect replies → resolve hostnames
```

**Python pseudocode:**
```python
from scapy.all import ARP, Ether, srp

def arp_scan(network="192.168.1.0/24"):
    arp = ARP(pdst=network)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether / arp
    result = srp(packet, timeout=2, verbose=0)[0]
    devices = []
    for sent, received in result:
        devices.append({
            "ip": received.psrc,
            "mac": received.hwsrc,
            "hostname": resolve_hostname(received.psrc)
        })
    return devices
```

### 10.2 Flask REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices` | Return all discovered devices |
| GET | `/api/devices/<ip>` | Return single device details |
| POST | `/api/scan` | Trigger a new ARP scan |
| GET | `/api/alerts` | Return all active alerts |
| GET | `/api/bandwidth` | Return current bandwidth stats |
| GET | `/api/topology` | Return topology node/edge data |
| GET | `/api/stats` | Return summary KPI statistics |

### 10.3 React Component Tree

```
App
├── TopBar (logo, student info, status pills, clock)
├── Sidebar (navigation, ARP scan button)
└── Main
    ├── DashboardPage
    │   ├── KpiStrip (5 KPI cards)
    │   ├── BandwidthAreaChart (recharts)
    │   ├── StatusDonutChart (recharts)
    │   ├── RecentDevicesTable
    │   └── LiveAlertsPanel
    ├── DevicesPage
    │   ├── SearchBar
    │   └── FullDeviceTable (IP, MAC, OS, Status, Ping, Uptime)
    ├── TopologyPage
    │   ├── PacketTracerInfoBanner
    │   ├── TopologyCanvas (HTML5 Canvas)
    │   ├── NodeInspectorPanel
    │   └── PDUSimulationLog
    ├── TrafficPage
    │   ├── BandwidthHistoryChart
    │   ├── ProtocolDistributionBarChart
    │   └── TopTalkersPanel
    ├── PerformancePage
    │   ├── InterfaceCards
    │   ├── LatencyBarChart
    │   └── PacketLossAreaChart
    ├── AlertsPage
    │   ├── AlertKpiStrip
    │   └── AlertList
    └── AboutPage
        ├── ProjectDetailsTable
        ├── TechStackBars
        ├── ObjectivesGrid
        └── ArchitectureFlow
```

---

## 11. User Interface Requirements

### 11.1 Design Principles

- **Dark theme** — optimized for network operation center (NOC) environments
- **Color coding** — Green (online), Red (offline), Yellow (warning), Purple (new/unknown), Cyan (primary accent)
- **Monospace font** — JetBrains Mono for technical data (IPs, MACs, latency)
- **Display font** — Syne for headings and KPI values
- **Real-time feel** — live updating charts, blinking status indicators, animated scan progress

### 11.2 Page Layout

```
┌──────────────── TOPBAR (Logo | Student Info | Status Pills | Clock) ───────────────┐
│  SIDEBAR   │                    MAIN CONTENT AREA                                  │
│            │  ┌─────────────────────────────────────────────────────────────────┐  │
│ ◈ Dashboard│  │  KPI STRIP (Total | Online | Offline | Latency | New Devices)   │  │
│ ⬡ Devices  │  ├──────────────────────────────────┬──────────────────────────────┤  │
│ ◉ Topology │  │  BANDWIDTH AREA CHART (2/3 width) │  STATUS DONUT + BARS (1/3)  │  │
│ ▲ Traffic  │  ├──────────────────────────────────┴──────────────────────────────┤  │
│ ◎ Perf.    │  │  DEVICE TABLE (1/2)               │  ALERTS PANEL (1/2)         │  │
│ ⚠ Alerts   │  └──────────────────────────────────┴──────────────────────────────┘  │
│ ℹ About    │                                                                        │
│            │                                                                        │
│ [ARP SCAN] │                                                                        │
└────────────┴────────────────────────────────────────────────────────────────────────┘
```

### 11.3 Status Indicators

| State | Color | Badge Label |
|-------|-------|-------------|
| Online | `#39ff88` (Green) | ▲ ONLINE |
| Offline | `#ff2d55` (Red) | ▼ OFFLINE |
| Warning | `#ffd60a` (Yellow) | ⚠ WARN |
| New Device | `#bf5af2` (Purple) | ★ NEW |

---

## 12. Data Requirements

### 12.1 Database Schema (SQLite)

**Table: `devices`**
```sql
CREATE TABLE devices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname    TEXT,
    ip_address  TEXT UNIQUE NOT NULL,
    mac_address TEXT,
    device_type TEXT,
    os_guess    TEXT,
    status      TEXT DEFAULT 'unknown',
    last_seen   DATETIME,
    first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Table: `ping_history`**
```sql
CREATE TABLE ping_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER REFERENCES devices(id),
    ping_ms     REAL,
    status      TEXT,
    checked_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Table: `alerts`**
```sql
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,   -- 'crit', 'warn', 'new', 'info'
    message     TEXT NOT NULL,
    device_ip   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved    INTEGER DEFAULT 0
);
```

**Table: `bandwidth_logs`**
```sql
CREATE TABLE bandwidth_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    interface    TEXT,
    bytes_in     INTEGER,
    bytes_out    INTEGER,
    recorded_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 12.2 Data Flow

```
ARP Scan → devices table → Flask API → React State → UI Render
ICMP Ping → ping_history table → Flask API → Chart Data
Alert Trigger → alerts table → Flask API → Alert Panel
psutil → bandwidth_logs table → Flask API → Bandwidth Chart
```

---

## 13. API Specifications

### GET `/api/devices`

**Response:**
```json
{
  "count": 17,
  "devices": [
    {
      "id": 1,
      "hostname": "gateway-01",
      "ip": "192.168.1.1",
      "mac": "A4:8C:01:FF:22:11",
      "type": "Router",
      "os": "Cisco IOS",
      "status": "up",
      "ping_ms": 3,
      "uptime_pct": 99.9,
      "last_seen": "2026-05-16T10:30:00"
    }
  ]
}
```

### GET `/api/alerts`

**Response:**
```json
{
  "total": 8,
  "critical": 1,
  "warning": 2,
  "new_devices": 1,
  "info": 4,
  "alerts": [
    {
      "id": 1,
      "level": "crit",
      "message": "printer-f1 — Host unreachable: 5 consecutive failures",
      "device_ip": "192.168.1.40",
      "created_at": "2026-05-16T10:28:00"
    }
  ]
}
```

### POST `/api/scan`

**Request:** `{}` (empty body triggers scan)

**Response:**
```json
{
  "status": "success",
  "devices_found": 17,
  "new_devices": 1,
  "scan_duration_ms": 4200,
  "timestamp": "2026-05-16T10:30:00"
}
```

---

## 14. Cisco Packet Tracer Integration

### 14.1 Purpose

Cisco Packet Tracer is used to:
1. **Design** the LAN topology (router, firewall, switch, servers, PCs, APs)
2. **Simulate** packet flows (PDU simulation) between devices
3. **Visualize** how data travels hop-by-hop across the network
4. **Export** the topology diagram for display in the React dashboard

### 14.2 Simulated Topology

```
Internet (Cloud)
      │
  Router-0 (192.168.1.1)
      │
  Firewall-0 (192.168.1.254)
      │
  Switch-0 (192.168.1.2)
  ┌───┴───────────────────────────┐
  │         │         │           │
Server-Web  Server-DB  Server-Mail  NAS
(1.10)      (1.11)     (1.12)      (1.60)
                                    │
                               ┌────┴────┐
                             AP-01     AP-02
                             (1.70)    (1.71)
```

### 14.3 PDU Simulation Steps

| Step | Action |
|------|--------|
| 1 | PC-0 sends ARP Request → broadcast (ff:ff:ff:ff:ff:ff) |
| 2 | Switch-0 floods frame to all ports |
| 3 | Server-Web replies with ARP Reply (its MAC address) |
| 4 | PC-0 records MAC → begins TCP 3-way handshake |
| 5 | SYN → Server-Web port 80 |
| 6 | SYN-ACK ← Server-Web responds |
| 7 | ACK → connection established |
| 8 | HTTP GET /index.html request sent |
| 9 | HTTP 200 OK response received |

---

## 15. Alert System Specification

### 15.1 Alert Levels

| Level | Color | Trigger Condition | Action |
|-------|-------|-------------------|--------|
| CRITICAL | Red | Device unreachable (3+ consecutive ping failures) | Toast notification + alert log |
| WARNING | Yellow | Latency > 30ms threshold | Alert log entry |
| NEW DEVICE | Purple | Unknown MAC address joins network | Toast + alert + highlighted table row |
| INFO | Cyan | Scan complete, device status change, port change | Alert log entry only |

### 15.2 Alert Thresholds (Configurable)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `latency_warn_ms` | 30 | Latency threshold for WARNING |
| `latency_crit_ms` | 100 | Latency threshold for CRITICAL |
| `ping_fail_count` | 3 | Consecutive failures before OFFLINE |
| `scan_interval_sec` | 30 | Auto-scan frequency |
| `new_device_notify` | true | Toast on new device detection |

---

## 16. Project Timeline

| Week | Tasks | Deliverable |
|------|-------|-------------|
| **Week 1** | Research, planning, environment setup | Project proposal, tech stack finalized |
| **Week 2** | ARP scan implementation using Scapy, ICMP ping module | Working `scanner.py` |
| **Week 3** | Flask REST API development, SQLite schema | Working API with `/devices`, `/scan` endpoints |
| **Week 4** | React UI development — Dashboard, Devices, Alerts pages | Frontend skeleton |
| **Week 5** | Integration (React ↔ Flask ↔ Scanner), Topology visualization, Cisco PT simulation | Full working prototype |
| **Week 6** | Testing, bug fixing, documentation, final presentation | Completed project + report |

---

## 17. Limitations and Constraints

| Limitation | Description |
|------------|-------------|
| **LAN Only** | System operates only within a Local Area Network — no WAN/Internet monitoring |
| **No Personal Data** | Cannot and does not retrieve personal data from devices |
| **OS Detection Accuracy** | OS guessing via TTL/fingerprinting is approximate, not guaranteed |
| **Device Blocking** | Some devices (firewalls, phones) may block ICMP or ARP — will appear offline |
| **Packet Tracer** | Cisco Packet Tracer is simulation-only — no real-time live data integration |
| **Admin Rights** | Scapy requires administrator/root privileges to send raw packets |
| **Single Subnet** | Current version scans a single /24 subnet only |

---

## 18. Expected Outcomes

Upon completion, the system will:

1. **Display real-time connected devices** — IP, MAC, hostname, type, OS, status, latency
2. **Provide a modern interactive dashboard** — built with React.js and recharts
3. **Monitor live bandwidth** — inbound/outbound Mbps per interface
4. **Generate actionable alerts** — for offline devices, high latency, and new unknown devices
5. **Visualize network topology** — interactive canvas-based diagram based on Cisco Packet Tracer design
6. **Simulate PDU packet flow** — educational step-by-step packet tracing
7. **Demonstrate practical skills** — in networking, Python backend, and React frontend development

---

## 19. Risks and Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Scapy requires root/admin rights | High | Medium | Document requirement; provide instructions |
| Some devices block ARP/ICMP | Medium | Low | Mark as "unknown" rather than failing |
| React-Flask CORS issues | Medium | Medium | Use Flask-CORS library |
| Packet Tracer version incompatibility | Low | Low | Use Packet Tracer 8.x, document version |
| SQLite write conflicts under load | Low | Low | Use WAL mode; single-writer design |
| Network topology changes between scans | Medium | Low | Re-scan on demand; periodic auto-scan |

---

## 20. References

- Python Scapy Documentation — https://scapy.readthedocs.io
- Flask Documentation — https://flask.palletsprojects.com
- React.js Documentation — https://react.dev
- Recharts Documentation — https://recharts.org
- Cisco Packet Tracer — https://www.netacad.com/courses/packet-tracer
- psutil Documentation — https://psutil.readthedocs.io
- SQLite Documentation — https://sqlite.org/docs.html
- W3Schools — https://www.w3schools.com
- YouTube — Network monitoring tutorials

---

*Document prepared by S.W.G Mindana | GAL/2324/IT/F/0113 | HND IT — Advanced Technological Institute, Galle*
