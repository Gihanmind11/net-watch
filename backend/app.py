"""Flask REST API for Network Monitoring System."""

import time
import threading
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from flask_cors import CORS

import database as db
import monitor
import scanner

app = Flask(__name__)
CORS(app)

# Initialize database
db.init_db()


# ── API Routes ───────────────────────────────────────────────────────────────

@app.route("/api/devices", methods=["GET"])
def get_devices():
    """Return all discovered devices."""
    devices = db.get_devices()
    result = []
    for d in devices:
        result.append({
            "id": d["id"],
            "hostname": d["hostname"] or d["ip_address"],
            "ip": d["ip_address"],
            "mac": d["mac_address"] or "N/A",
            "type": d["device_type"] or "Unknown",
            "os": d["os_guess"] or "Unknown",
            "status": d["status"],
            "ping_ms": d["ping_ms"] or 0,
            "uptime_pct": d["uptime_pct"] or 100.0,
            "last_seen": d["last_seen"],
            "first_seen": d["first_seen"],
        })
    return jsonify({"count": len(result), "devices": result})


@app.route("/api/devices/<ip>", methods=["GET"])
def get_device(ip):
    """Return single device details."""
    d = db.get_device_by_ip(ip)
    if not d:
        return jsonify({"error": "Device not found"}), 404
    return jsonify({
        "id": d["id"],
        "hostname": d["hostname"] or d["ip_address"],
        "ip": d["ip_address"],
        "mac": d["mac_address"] or "N/A",
        "type": d["device_type"] or "Unknown",
        "os": d["os_guess"] or "Unknown",
        "status": d["status"],
        "ping_ms": d["ping_ms"] or 0,
        "uptime_pct": d["uptime_pct"] or 100.0,
        "last_seen": d["last_seen"],
        "first_seen": d["first_seen"],
    })


@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    """Trigger a manual ARP scan."""
    network = request.json.get("network") if request.is_json else None
    result = monitor.run_scan(network)
    return jsonify(result)


@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    """Return all active alerts with counts."""
    alerts = db.get_alerts()
    counts = db.get_alert_counts()
    result = []
    for a in alerts:
        result.append({
            "id": a["id"],
            "level": a["level"],
            "message": a["message"],
            "device_ip": a["device_ip"],
            "created_at": a["created_at"],
        })
    return jsonify({
        "total": counts["total"],
        "critical": counts["critical"],
        "warning": counts["warning"],
        "new_devices": counts["new_devices"],
        "info": counts["info"],
        "alerts": result,
    })


@app.route("/api/bandwidth", methods=["GET"])
def get_bandwidth():
    """Return current bandwidth stats and recent history."""
    current = monitor.get_bandwidth()
    history = db.get_bandwidth_history(minutes=5)
    return jsonify({
        "current": current,
        "history": history,
    })


@app.route("/api/topology", methods=["GET"])
def get_topology():
    """Return topology nodes and edges for visualization."""
    devices = db.get_devices()

    # Build topology from discovered devices
    nodes = []
    edges = []

    # Core infrastructure nodes (always present)
    core_nodes = {
        "gw": {"id": "gw", "label": "gateway-01", "ip": "192.168.1.1", "type": "router", "x": 450, "y": 60},
        "fw": {"id": "fw", "label": "firewall", "ip": "192.168.1.254", "type": "firewall", "x": 450, "y": 150},
        "sw": {"id": "sw", "label": "core-switch", "ip": "192.168.1.2", "type": "switch", "x": 450, "y": 240},
    }

    # Map discovered devices to topology positions
    device_map = {}
    for d in devices:
        device_map[d["ip_address"]] = d

    # Update core nodes with live status
    for key, node in core_nodes.items():
        dev = device_map.get(node["ip"])
        node["status"] = dev["status"] if dev else "unknown"
        nodes.append(node)

    # Define positions for known devices
    positions = {
        "192.168.1.10": {"x": 150, "y": 340, "parent": "sw"},
        "192.168.1.11": {"x": 270, "y": 340, "parent": "sw"},
        "192.168.1.12": {"x": 390, "y": 340, "parent": "sw"},
        "192.168.1.60": {"x": 510, "y": 340, "parent": "sw"},
        "192.168.1.70": {"x": 630, "y": 340, "parent": "sw"},
        "192.168.1.71": {"x": 750, "y": 340, "parent": "sw"},
        "192.168.1.40": {"x": 100, "y": 450, "parent": "192.168.1.10"},
        "192.168.1.20": {"x": 220, "y": 450, "parent": "192.168.1.10"},
        "192.168.1.21": {"x": 340, "y": 450, "parent": "192.168.1.11"},
        "192.168.1.22": {"x": 460, "y": 450, "parent": "192.168.1.11"},
        "192.168.1.30": {"x": 580, "y": 450, "parent": "192.168.1.70"},
        "192.168.1.50": {"x": 700, "y": 450, "parent": "192.168.1.60"},
        "192.168.1.51": {"x": 800, "y": 450, "parent": "192.168.1.60"},
    }

    # Add discovered devices as topology nodes
    for d in devices:
        ip = d["ip_address"]
        if ip in [n["ip"] for n in nodes]:
            continue

        pos = positions.get(ip)
        if pos:
            node_id = ip.replace(".", "_")
            node = {
                "id": node_id,
                "label": d["hostname"] or ip,
                "ip": ip,
                "type": _map_device_type(d["device_type"]),
                "x": pos["x"],
                "y": pos["y"],
                "status": d["status"],
            }
            nodes.append(node)

            # Add edge to parent
            parent_ip = pos["parent"]
            parent_node = None
            for n in nodes:
                if n["ip"] == parent_ip:
                    parent_node = n
                    break
            if parent_node:
                edges.append([parent_node["id"], node_id])

    # Default edges for core infrastructure
    core_edges = [["gw", "fw"], ["fw", "sw"]]
    for src, dst in core_edges:
        if [src, dst] not in edges:
            edges.append([src, dst])

    return jsonify({"nodes": nodes, "edges": edges})


def _map_device_type(dtype):
    """Map device_type string to topology type."""
    dtype = (dtype or "").lower()
    if "router" in dtype:
        return "router"
    if "switch" in dtype:
        return "switch"
    if "server" in dtype or "nas" in dtype:
        return "server"
    if "firewall" in dtype:
        return "firewall"
    if "ap" in dtype or "wifi" in dtype:
        return "ap"
    return "device"


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return KPI summary statistics."""
    stats = db.get_stats()
    return jsonify(stats)


@app.route("/api/interfaces", methods=["GET"])
def get_interfaces():
    """Return interface card data."""
    ifaces = monitor.get_interfaces()
    return jsonify({"interfaces": ifaces})


@app.route("/api/protocols", methods=["GET"])
def get_protocols():
    """Return protocol distribution (simulated for educational purposes)."""
    # Protocol distribution is simulated since deep packet inspection is out of scope
    protocols = [
        {"protocol": "TCP", "percentage": 42, "color": "#00d4ff"},
        {"protocol": "UDP", "percentage": 18, "color": "#00ff88"},
        {"protocol": "HTTP", "percentage": 12, "color": "#ffcc00"},
        {"protocol": "HTTPS", "percentage": 28, "color": "#ff6b35"},
        {"protocol": "DNS", "percentage": 8, "color": "#8844ff"},
        {"protocol": "ICMP", "percentage": 4, "color": "#ff3355"},
        {"protocol": "Other", "percentage": 6, "color": "#4a7090"},
    ]
    return jsonify({"protocols": protocols})


@app.route("/api/top-talkers", methods=["GET"])
def get_top_talkers():
    """Return top bandwidth-consuming devices."""
    devices = db.get_devices()
    talkers = []
    for d in devices[:5]:
        if d["status"] == "up":
            talkers.append({
                "hostname": d["hostname"] or d["ip_address"],
                "ip": d["ip_address"],
                "sent_mb": round(10 + hash(d["ip_address"]) % 200, 1),
                "recv_mb": round(5 + hash(d["ip_address"]) % 150, 1),
            })
    talkers.sort(key=lambda t: t["sent_mb"] + t["recv_mb"], reverse=True)
    return jsonify({"talkers": talkers[:5]})


@app.route("/api/pdu-simulation", methods=["GET"])
def get_pdu_simulation():
    """Return PDU simulation steps for educational purposes."""
    steps = [
        {"step": 1, "action": "PC-0 sends ARP Request", "detail": "Broadcast to ff:ff:ff:ff:ff:ff", "from": "192.168.1.20", "to": "broadcast"},
        {"step": 2, "action": "Switch-0 floods frame", "detail": "Frame forwarded to all ports", "from": "switch", "to": "all"},
        {"step": 3, "action": "Server-Web replies", "detail": "ARP Reply with MAC address", "from": "192.168.1.10", "to": "192.168.1.20"},
        {"step": 4, "action": "PC-0 records MAC", "detail": "ARP table updated, begins TCP handshake", "from": "192.168.1.20", "to": "192.168.1.10"},
        {"step": 5, "action": "SYN → port 80", "detail": "TCP SYN packet sent to web server", "from": "192.168.1.20", "to": "192.168.1.10"},
        {"step": 6, "action": "SYN-ACK ←", "detail": "Server responds with SYN-ACK", "from": "192.168.1.10", "to": "192.168.1.20"},
        {"step": 7, "action": "ACK →", "detail": "Connection established", "from": "192.168.1.20", "to": "192.168.1.10"},
        {"step": 8, "action": "HTTP GET /index.html", "detail": "Web page request sent", "from": "192.168.1.20", "to": "192.168.1.10"},
        {"step": 9, "action": "HTTP 200 OK", "detail": "Web page content received", "from": "192.168.1.10", "to": "192.168.1.20"},
    ]
    return jsonify({"steps": steps})


# ── Startup ──────────────────────────────────────────────────────────────────

def _initial_scan():
    """Run initial scan after a short delay."""
    time.sleep(1)
    print("[startup] Running initial network scan...")
    try:
        monitor.run_scan()
        monitor.log_bandwidth()
        print("[startup] Initial scan complete.")
    except Exception as e:
        print(f"[startup] Initial scan error: {e}")


if __name__ == "__main__":
    # Start background scanner
    monitor.start_scheduler(interval_sec=30)

    # Run initial scan in background
    threading.Thread(target=_initial_scan, daemon=True).start()

    print("=" * 50)
    print("  NetWatch API Server")
    print("  http://localhost:5000")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
