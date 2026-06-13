"""SQLite database layer for Network Monitoring System."""

import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

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
            open_ports  TEXT DEFAULT '',
            last_seen   DATETIME,
            first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add open_ports column if table already existed without it
    try:
        c.execute("ALTER TABLE devices ADD COLUMN open_ports TEXT DEFAULT ''")
    except Exception:
        pass  # Column already exists

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

    # Add index on recorded_at for faster bandwidth history queries
    c.execute("CREATE INDEX IF NOT EXISTS idx_bandwidth_recorded ON bandwidth_logs(recorded_at)")

    # Create users table for authentication
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME
        )
    """)

    # Migration 1: Add 'active' column to users table if missing
    try:
        c.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass

    # Create login_attempts table for tracking login attempts
    c.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create index for fast login attempt queries
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_login_attempts_ip
        ON login_attempts(ip_address, attempt_time)
    """)

    # Create refresh_tokens table
    c.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            revoked INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create index for fast refresh token lookup
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token
        ON refresh_tokens(token)
    """)

    # Insert default admin user if no users exist yet
    c.execute("SELECT COUNT(*) as count FROM users")
    if c.fetchone()["count"] == 0:
        default_password_hash = generate_password_hash("admin123", method="pbkdf2:sha256")
        c.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        """, ("admin", default_password_hash, "admin"))

    conn.commit()
    conn.close()


# ── Data Retention ───────────────────────────────────────────────────────────

def cleanup_old_data(hours=24):
    """Delete bandwidth_logs older than specified hours."""
    conn = get_conn()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    deleted = conn.execute("DELETE FROM bandwidth_logs WHERE recorded_at < ?", (cutoff,)).rowcount
    conn.commit()
    conn.close()
    return deleted


# ── Device CRUD ──────────────────────────────────────────────────────────────

def upsert_device(ip, mac=None, device_name=None, device_type=None, os_guess=None, status="up", ping_ms=0, open_ports=""):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM devices WHERE ip_address=?", (ip,)).fetchone()

    if existing:
        device_id = existing["id"]
        conn.execute("""
            UPDATE devices SET device_name=COALESCE(?,device_name), mac_address=COALESCE(?,mac_address),
            device_type=?, os_guess=?,
            status=?, ping_ms=?, open_ports=?, last_seen=?
            WHERE id=?
        """, (device_name, mac, device_type, os_guess, status, ping_ms, open_ports, now, device_id))
    else:
        c = conn.execute("""
            INSERT INTO devices (device_name, ip_address, mac_address, device_type, os_guess, status, ping_ms, open_ports, last_seen)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (device_name, ip, mac, device_type, os_guess, status, ping_ms, open_ports, now))
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


def resolve_alert(alert_id):
    conn = get_conn()
    conn.execute("UPDATE alerts SET resolved=1 WHERE id=?", (alert_id,))
    changes = conn.total_changes
    conn.commit()
    conn.close()
    return changes > 0


def clear_all_alerts():
    conn = get_conn()
    conn.execute("UPDATE alerts SET resolved=1 WHERE resolved=0")
    conn.commit()
    conn.close()


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


# ── User Management ───────────────────────────────────────────────────────

def get_user_by_username(username):
    """Get a user by username. Returns user dict or None.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def verify_user(username, password):
    """Check username and password. Returns user dict or None.
    """
    user = get_user_by_username(username)
    if not user:
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def create_user(username, password, role="admin"):
    """Create a new user. Returns new user dict or None if username exists.
    """
    if get_user_by_username(username):
        return None

    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    conn = get_conn()
    try:
        c = conn.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        """, (username, password_hash, role))
        user_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

    return get_user_by_username(username)


def update_last_login(username):
    """Update user's last_login time to now.
    """
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute("""
        UPDATE users SET last_login = ? WHERE username = ?
    """, (now, username))
    conn.commit()
    conn.close()


# ── Login Attempts ───────────────────────────────────────────────────────────

def log_login_attempt(username, ip_address, success):
    """Log a login attempt."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO login_attempts (username, ip_address, success)
        VALUES (?, ?, ?)
    """, (username, ip_address, 1 if success else 0))
    conn.commit()
    conn.close()


def get_recent_failed_attempts(ip_address, window_minutes=15):
    """Get number of failed login attempts in the last window_minutes minutes."""
    conn = get_conn()
    cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    result = conn.execute("""
        SELECT COUNT(*) AS count
        FROM login_attempts
        WHERE ip_address = ? AND success = 0 AND attempt_time >= ?
    """, (ip_address, cutoff)).fetchone()
    count = result["count"]
    conn.close()
    return count


# ── Refresh Tokens ─────────────────────────────────────────────────────────────

def store_refresh_token(user_id, token, expires_in_days=7):
    """Store a refresh token in the database."""
    expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()
    conn = get_conn()
    conn.execute("""
        INSERT INTO refresh_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token, expires_at))
    conn.commit()
    conn.close()


def get_refresh_token(token):
    """Get a valid refresh token (not expired, not revoked). Returns token dict or None."""
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    row = conn.execute("""
        SELECT * FROM refresh_tokens
        WHERE token = ? AND revoked = 0 AND expires_at > ?
    """, (token, now)).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_refresh_token(token):
    """Revoke a refresh token."""
    conn = get_conn()
    conn.execute("""
        UPDATE refresh_tokens SET revoked = 1 WHERE token = ?
    """, (token,))
    conn.commit()
    conn.close()


def revoke_all_user_refresh_tokens(user_id):
    """Revoke all refresh tokens for a user."""
    conn = get_conn()
    conn.execute("""
        UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()


# ── User Permissions (for future use) ──────────────────────────────────────────

def get_user_permissions(user_id):
    """Get permissions for a user based on role. Returns list of permissions."""
    user = get_user_by_username(get_user_by_id(user_id)["username"])
    if not user:
        return []
    
    # Simple role-based permissions for now
    permissions_map = {
        "admin": [
            "devices:read",
            "devices:write",
            "alerts:read",
            "alerts:write",
            "traffic:read",
            "performance:read",
            "topology:read",
            "scan:run"
        ]
    }
    return permissions_map.get(user["role"], [])


def get_user_by_id(user_id):
    """Get a user by their user ID."""
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM users WHERE id = ?
    """, (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

