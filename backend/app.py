"""Flask REST API for Network Monitoring System."""

import time
import threading
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from flask_cors import CORS

import database as db
import monitor
import scanner
from auth import (
    generate_access_token,
    generate_refresh_token,
    require_auth
)

app = Flask(__name__)
CORS(app, supports_credentials=True)

# Initialize database
db.init_db()


# ─── Rate Limiting Configuration ─────────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 15


# ─── Auth Routes ────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    """Full login flow: validation → rate limit → log attempt → tokens → permissions."""
    # 1. Backend Validation (username/password present)
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    username = data.get("username", "")
    password = data.get("password", "")
    client_ip = request.remote_addr or "unknown"

    if not username or not password:
        db.log_login_attempt(username, client_ip, False)
        return jsonify({"error": "Username and password are required"}), 400

    # 2. Rate Limiting Check
    failed_attempts = db.get_recent_failed_attempts(
        client_ip, window_minutes=RATE_LIMIT_WINDOW_MINUTES
    )
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        db.log_login_attempt(username, client_ip, False)
        return jsonify({
            "error": "Too many failed login attempts. Please try again later.",
            "retry_after": RATE_LIMIT_WINDOW_MINUTES
        }), 429

    # 3. Check user exists and verify password
    user = db.verify_user(username, password)

    # 4. Log login attempt
    success = user is not None
    db.log_login_attempt(username, client_ip, success)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    # 5. Check account active status
    if not user["active"]:
        return jsonify({"error": "Account is disabled"}), 403

    # 6. Update last login
    db.update_last_login(username)

    # 7. Generate tokens
    access_token = generate_access_token(
        username, user_id=user["id"], expires_in_minutes=60
    )
    refresh_token = generate_refresh_token()

    # 8. Store refresh token
    db.store_refresh_token(user_id=user["id"], token=refresh_token)

    # 9. Load user permissions
    permissions = db.get_user_permissions(user_id=user["id"])

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "permissions": permissions
        }
    }), 200


@app.route("/api/refresh", methods=["POST"])
def refresh():
    """Refresh access token using valid refresh token."""
    data = request.get_json()
    refresh_token = data.get("refresh_token") if data else None

    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400

    # Verify refresh token in DB
    stored_token = db.get_refresh_token(refresh_token)
    if not stored_token:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    # Get user details
    user = db.get_user_by_id(stored_token["user_id"])
    if not user or not user["active"]:
        return jsonify({"error": "Invalid user or account disabled"}), 403

    # Revoke old refresh token for security (single-use)
    db.revoke_refresh_token(refresh_token)

    # Generate new token pair
    new_access = generate_access_token(user["username"], user["id"])
    new_refresh = generate_refresh_token()
    db.store_refresh_token(user["id"], new_refresh)

    # Load user permissions
    permissions = db.get_user_permissions(user["id"])

    return jsonify({
        "access_token": new_access,
        "refresh_token": new_refresh,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "permissions": permissions
        }
    }), 200


@app.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    """Logout user by revoking refresh token."""
    data = request.get_json()
    refresh_token = data.get("refresh_token") if data else None

    if refresh_token:
        db.revoke_refresh_token(refresh_token)

    return jsonify({"status": "success"}), 200


# ─── Protected API Routes (require authentication) ───────────────────────────────
@app.route("/api/devices", methods=["GET"])
@require_auth
def get_devices():
    """Return all discovered devices."""
    devices = db.get_devices()
    result = []
    for d in devices:
        result.append({
            "id": d["id"],
            "device_name": d["device_name"] or d["ip_address"],
            "ip": d["ip_address"],
            "mac": d["mac_address"] or "N/A",
            "type": d["device_type"] or "Unknown",
            "os": d["os_guess"] or "Unknown",
            "status": d["status"],
            "ping_ms": d["ping_ms"] or 0,
            "uptime_pct": d["uptime_pct"] or 100.0,
            "open_ports": d["open_ports"] or "",
            "last_seen": d["last_seen"],
            "first_seen": d["first_seen"],
        })
    return jsonify({"count": len(result), "devices": result})


@app.route("/api/devices/reset", methods=["POST"])
@require_auth
def reset_devices():
    """Delete all devices and related data."""
    conn = db.get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM ping_history")
    cur.execute("DELETE FROM alerts")
    cur.execute("DELETE FROM devices")
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "deleted": deleted})


@app.route("/api/devices/<ip>", methods=["GET"])
@require_auth
def get_device(ip):
    """Return single device details."""
    d = db.get_device_by_ip(ip)
    if not d:
        return jsonify({"error": "Device not found"}), 404
    return jsonify({
        "id": d["id"],
        "device_name": d["device_name"] or d["ip_address"],
        "ip": d["ip_address"],
        "mac": d["mac_address"] or "N/A",
        "type": d["device_type"] or "Unknown",
        "os": d["os_guess"] or "Unknown",
        "status": d["status"],
        "ping_ms": d["ping_ms"] or 0,
        "uptime_pct": d["uptime_pct"] or 100.0,
        "open_ports": d["open_ports"] or "",
        "last_seen": d["last_seen"],
        "first_seen": d["first_seen"],
    })


@app.route("/api/scan", methods=["POST"])
@require_auth
def scan_network():
    """Trigger network scan and return results."""
    result = monitor.run_scan()
    return jsonify(result)


@app.route("/api/alerts", methods=["GET"])
@require_auth
def get_alerts():
    """Return all alerts."""
    alerts = db.get_alerts()
    return jsonify({"count": len(alerts), "alerts": alerts})


@app.route("/api/alerts/<int:alert_id>/resolve", methods=["POST"])
@require_auth
def resolve_alert(alert_id):
    """Mark alert as resolved."""
    success = db.resolve_alert(alert_id)
    if success:
        return jsonify({"status": "ok"})
    else:
        return jsonify({"error": "Alert not found"}), 404


@app.route("/api/topology", methods=["GET"])
@require_auth
def get_topology():
    """Return network topology data."""
    devices = db.get_devices()
    nodes = []
    links = []
    try:
        from scapy.arch import get_if_addr
        try:
            gateway_ip = ".".join(get_if_addr(scanner.get_default_interface()).split(".")[:3]) + ".1"
        except:
            gateway_ip = None
        if gateway_ip:
            nodes.append({
                "id": "gateway",
                "label": "Gateway",
                "ip": gateway_ip,
                "type": "router",
                "x": 400,
                "y": 200,
                "status": "up"
            })
    except Exception:
        pass
    for i, d in enumerate(devices):
        nodes.append({
            "id": str(d["id"]),
            "label": d["device_name"] or d["ip_address"],
            "ip": d["ip_address"],
            "type": "switch" if d["device_type"] == "Switch" else "server" if d["device_type"] == "Server" else "workstation",
            "x": 200 + (i % 3) * 200,
            "y": 350 + (i // 3) * 100,
            "status": d["status"]
        })
        if len(nodes) > 1:
            links.append({"source": "gateway" if nodes[0]["id"] == "gateway" else "0", "target": str(d["id"])})
    return jsonify({"nodes": nodes, "links": links})


@app.route("/api/traffic", methods=["GET"])
@require_auth
def get_traffic():
    """Return bandwidth traffic data."""
    traffic = monitor.get_bandwidth()
    return jsonify(traffic)


@app.route("/api/performance", methods=["GET"])
@require_auth
def get_performance():
    """Return performance statistics."""
    stats = db.get_stats()
    return jsonify(stats)


# ─── Background Monitoring Thread ────────────────────────────────────────────────
def background_monitor():
    """Continuously monitor network devices and update their status."""
    while True:
        try:
            monitor.monitor_all_devices()
        except Exception as e:
            print(f"Monitoring error: {e}")
        time.sleep(10)


monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
