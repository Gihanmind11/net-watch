"""SQLite database layer for Network Monitoring System."""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "netmon.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname    TEXT,
            ip_address  TEXT UNIQUE NOT NULL,
            mac_address TEXT,
            device_type TEXT DEFAULT 'Unknown',
            os_guess    TEXT,
            status      TEXT DEFAULT 'unknown',
            ping_ms     REAL DEFAULT 0,
            uptime_pct  REAL DEFAULT 100.0,
            last_seen   DATETIME,
            first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ping_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   INTEGER REFERENCES devices(id),
            ping_ms     REAL,
            status      TEXT,
            checked_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            level       TEXT NOT NULL,
            message     TEXT NOT NULL,
            device_ip   TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved    INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bandwidth_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            interface    TEXT,
            bytes_in     INTEGER,
            bytes_out    INTEGER,
            recorded_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ── Device CRUD ──────────────────────────────────────────────────────────────

def upsert_device(ip, mac=None, hostname=None, device_type=None, os_guess=None, status="up", ping_ms=0):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM devices WHERE ip_address=?", (ip,)).fetchone()

    if existing:
        device_id = existing["id"]
        conn.execute("""
            UPDATE devices SET hostname=COALESCE(?,hostname), mac_address=COALESCE(?,mac_address),
            device_type=COALESCE(?,device_type), os_guess=COALESCE(?,os_guess),
            status=?, ping_ms=?, last_seen=?
            WHERE id=?
        """, (hostname, mac, device_type, os_guess, status, ping_ms, now, device_id))
    else:
        c = conn.execute("""
            INSERT INTO devices (hostname, ip_address, mac_address, device_type, os_guess, status, ping_ms, last_seen)
            VALUES (?,?,?,?,?,?,?,?)
        """, (hostname, ip, mac, device_type, os_guess, status, ping_ms, now))
        device_id = c.lastrowid

    conn.commit()
    conn.close()
    return device_id


def get_devices():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM devices ORDER BY ip_address").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_device_by_ip(ip):
    conn = get_conn()
    row = conn.execute("SELECT * FROM devices WHERE ip_address=?", (ip,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_device_status(ip, status, ping_ms=0):
    conn = get_conn()
    now = datetime.utcnow().isoformat()

    # Update uptime: track last N pings and calculate percentage
    device = conn.execute("SELECT id FROM devices WHERE ip_address=?", (ip,)).fetchone()
    if device:
        device_id = device["id"]
        conn.execute("UPDATE devices SET status=?, ping_ms=?, last_seen=? WHERE id=?",
                     (status, ping_ms, now, device_id))

        # Insert ping history
        conn.execute("INSERT INTO ping_history (device_id, ping_ms, status, checked_at) VALUES (?,?,?,?)",
                     (device_id, ping_ms, status, now))

        # Calculate uptime from last 100 pings
        rows = conn.execute(
            "SELECT status FROM ping_history WHERE device_id=? ORDER BY id DESC LIMIT 100",
            (device_id,)
        ).fetchall()
        if rows:
            up_count = sum(1 for r in rows if r["status"] == "up")
            uptime = round(up_count / len(rows) * 100, 1)
            conn.execute("UPDATE devices SET uptime_pct=? WHERE id=?", (uptime, device_id))

    conn.commit()
    conn.close()


# ── Ping History ─────────────────────────────────────────────────────────────

def add_ping(device_id, ping_ms, status):
    conn = get_conn()
    conn.execute("INSERT INTO ping_history (device_id, ping_ms, status) VALUES (?,?,?)",
                 (device_id, ping_ms, status))
    conn.commit()
    conn.close()


# ── Alerts ───────────────────────────────────────────────────────────────────

def add_alert(level, message, device_ip=None):
    conn = get_conn()
    conn.execute("INSERT INTO alerts (level, message, device_ip) VALUES (?,?,?)",
                 (level, message, device_ip))
    conn.commit()
    conn.close()


def get_alerts(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts WHERE resolved=0 ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alert_counts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT level, COUNT(*) as cnt FROM alerts WHERE resolved=0 GROUP BY level"
    ).fetchall()
    conn.close()
    counts = {r["level"]: r["cnt"] for r in rows}
    return {
        "total": sum(counts.values()),
        "critical": counts.get("crit", 0),
        "warning": counts.get("warn", 0),
        "new_devices": counts.get("new", 0),
        "info": counts.get("info", 0),
    }


# ── Bandwidth ────────────────────────────────────────────────────────────────

def add_bandwidth_log(interface, bytes_in, bytes_out):
    conn = get_conn()
    conn.execute("INSERT INTO bandwidth_logs (interface, bytes_in, bytes_out) VALUES (?,?,?)",
                 (interface, bytes_in, bytes_out))
    conn.commit()
    conn.close()


def get_bandwidth_history(interface=None, minutes=5):
    conn = get_conn()
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    if interface:
        rows = conn.execute(
            "SELECT * FROM bandwidth_logs WHERE interface=? AND recorded_at>=? ORDER BY recorded_at",
            (interface, cutoff)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bandwidth_logs WHERE recorded_at>=? ORDER BY recorded_at",
            (cutoff,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stats ────────────────────────────────────────────────────────────────────

def get_stats():
    conn = get_conn()
    devices = conn.execute("SELECT status, COUNT(*) as cnt FROM devices GROUP BY status").fetchall()
    total = conn.execute("SELECT COUNT(*) as cnt FROM devices").fetchone()["cnt"]
    avg_ping = conn.execute(
        "SELECT AVG(ping_ms) as avg FROM devices WHERE status='up' AND ping_ms>0"
    ).fetchone()["avg"] or 0

    status_map = {r["status"]: r["cnt"] for r in devices}
    conn.close()

    return {
        "total_devices": total,
        "online": status_map.get("up", 0),
        "offline": status_map.get("down", 0),
        "warning": status_map.get("warn", 0),
        "new_devices": status_map.get("new", 0),
        "avg_latency": round(avg_ping, 1),
    }


# ── Known MACs tracking ─────────────────────────────────────────────────────

def get_known_macs():
    conn = get_conn()
    rows = conn.execute("SELECT mac_address FROM devices WHERE mac_address IS NOT NULL").fetchall()
    conn.close()
    return {r["mac_address"] for r in rows}
