"""Bandwidth monitoring and background scan scheduler."""

import time
import threading
from datetime import datetime

import psutil

import database as db
import scanner


# ── Bandwidth Monitoring ─────────────────────────────────────────────────────

_prev_counters = {}
_prev_time = {}


def get_bandwidth():
    """Get current bandwidth usage per interface in Mbps."""
    counters = psutil.net_io_counters(pernic=True)
    now = time.time()
    result = {}

    for iface, stats in counters.items():
        if iface == "lo" or iface.startswith("Loopback"):
            continue

        key = iface
        if key in _prev_counters:
            dt = now - _prev_time[key]
            if dt > 0:
                bytes_in_rate = (stats.bytes_recv - _prev_counters[key].bytes_recv) / dt
                bytes_out_rate = (stats.bytes_sent - _prev_counters[key].bytes_sent) / dt
                result[iface] = {
                    "interface": iface,
                    "bytes_in": round(bytes_in_rate),
                    "bytes_out": round(bytes_out_rate),
                    "mbps_in": round(bytes_in_rate * 8 / 1_000_000, 2),
                    "mbps_out": round(bytes_out_rate * 8 / 1_000_000, 2),
                    "total_in": stats.bytes_recv,
                    "total_out": stats.bytes_sent,
                    "packets_in": stats.packets_recv,
                    "packets_out": stats.packets_sent,
                    "errors_in": stats.errin,
                    "errors_out": stats.errout,
                    "drops_in": stats.dropin,
                    "drops_out": stats.dropout,
                }

        _prev_counters[key] = stats
        _prev_time[key] = now

    return result


def get_interfaces():
    """Get interface card information."""
    stats = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()
    iface_list = []

    for name, stat in stats.items():
        if name == "lo" or name.startswith("Loopback"):
            continue

        ip_addr = "N/A"
        if name in addrs:
            for addr in addrs[name]:
                if addr.family.name == "AF_INET":
                    ip_addr = addr.address
                    break

        iface_list.append({
            "name": name,
            "ip": ip_addr,
            "speed": _get_iface_speed(name),
            "total_in": stat.bytes_recv,
            "total_out": stat.bytes_sent,
            "packets_in": stat.packets_recv,
            "packets_out": stat.packets_sent,
            "errors": stat.errin + stat.errout,
            "drops": stat.dropin + stat.dropout,
            "status": "UP",
        })

    return iface_list


def _get_iface_speed(name):
    """Try to get interface speed."""
    try:
        stats = psutil.net_if_stats()
        if name in stats and stats[name].speed > 0:
            return f"{stats[name].speed} Mbps"
    except Exception:
        pass
    return "N/A"


def log_bandwidth():
    """Periodic bandwidth logging to database."""
    bw = get_bandwidth()
    for iface, data in bw.items():
        db.add_bandwidth_log(iface, data.get("bytes_in", 0), data.get("bytes_out", 0))
    return bw


# ── Background Scanner ───────────────────────────────────────────────────────

_scan_lock = threading.Lock()
_consecutive_failures = {}


def run_scan(network=None):
    """Execute a full scan cycle: ARP discovery + ping all devices."""
    with _scan_lock:
        start = time.time()
        discovered = scanner.arp_scan(network)
        known_macs = db.get_known_macs()
        new_devices = 0

        for dev in discovered:
            is_new = dev["mac"] not in known_macs and dev["mac"] != "N/A"
            device_id = db.upsert_device(
                ip=dev["ip"],
                mac=dev["mac"],
                hostname=dev["hostname"],
                device_type=_classify_device(dev),
                os_guess=dev.get("os_guess", "Unknown"),
                status="up",
                ping_ms=0,
            )

            if is_new:
                new_devices += 1
                db.add_alert("new", f"New device detected: {dev['hostname']} ({dev['ip']})", dev["ip"])

        # Ping all known devices
        devices = db.get_devices()
        for device in devices:
            ip = device["ip_address"]
            result = scanner.ping_host(ip)
            status = result["status"]
            ping_ms = result["ping_ms"]

            # Track consecutive failures
            if status == "down":
                _consecutive_failures[ip] = _consecutive_failures.get(ip, 0) + 1
                if _consecutive_failures[ip] >= 3:
                    status = "down"
                    if _consecutive_failures[ip] == 3:
                        db.add_alert("crit", f"{device['hostname']} ({ip}) — Host unreachable: 3 consecutive failures", ip)
            else:
                if ip in _consecutive_failures and _consecutive_failures[ip] >= 3:
                    db.add_alert("info", f"{device['hostname']} ({ip}) — Device back online", ip)
                _consecutive_failures[ip] = 0

            # Latency warning
            if status == "up" and ping_ms > 30:
                if ping_ms > 100:
                    db.add_alert("crit", f"{device['hostname']} ({ip}) — Critical latency: {ping_ms:.0f}ms", ip)
                else:
                    db.add_alert("warn", f"{device['hostname']} ({ip}) — High latency: {ping_ms:.0f}ms (threshold: 30ms)", ip)

            db.update_device_status(ip, status, ping_ms)

        duration_ms = round((time.time() - start) * 1000)
        return {
            "status": "success",
            "devices_found": len(discovered),
            "new_devices": new_devices,
            "scan_duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }


def _classify_device(dev):
    """Classify device type based on hostname/MAC."""
    host = (dev.get("hostname") or "").lower()
    mac = (dev.get("mac") or "").upper()

    if "router" in host or "gateway" in host or "gw" in host:
        return "Router"
    if "switch" in host or "sw" in host:
        return "Switch"
    if "firewall" in host or "fw" in host:
        return "Firewall"
    if "srv" in host or "server" in host:
        return "Server"
    if "nas" in host:
        return "NAS"
    if "ap" in host or "wifi" in host:
        return "Access Point"
    if "cam" in host:
        return "Camera"
    if "printer" in host or "print" in host:
        return "Printer"
    if "phone" in host or "voip" in host:
        return "VoIP"
    if "laptop" in host:
        return "Laptop"
    if "workstation" in host or "ws" in host or "pc" in host:
        return "PC"

    # Guess from MAC OUI
    os_guess = dev.get("os_guess", "")
    if "Cisco" in os_guess:
        return "Router"
    if "Printer" in os_guess:
        return "Printer"
    if "Camera" in os_guess:
        return "Camera"
    if "Access Point" in os_guess:
        return "Access Point"
    if "VoIP" in os_guess:
        return "VoIP"

    return "Unknown"


# ── Scheduler ────────────────────────────────────────────────────────────────

_scheduler_running = False


def start_scheduler(interval_sec=30):
    """Start background periodic scanning."""
    global _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True

    def _loop():
        while _scheduler_running:
            try:
                run_scan()
                log_bandwidth()
            except Exception as e:
                print(f"[scheduler] Error: {e}")
            time.sleep(interval_sec)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    print(f"[scheduler] Background scan started (every {interval_sec}s)")
