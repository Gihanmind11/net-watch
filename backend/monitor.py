"""Bandwidth monitoring and background scan scheduler."""

import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil

import database as db
import scanner


# ── Bandwidth Monitoring ─────────────────────────────────────────────────────

_prev_counters = {}
_prev_time = {}


def get_bandwidth():
    """Get current bandwidth usage per interface in Mbps."""
    counters = psutil.net_io_counters(pernic=True)
    iface_stats = psutil.net_if_stats()
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
                mbps_in = round(bytes_in_rate * 8 / 1_000_000, 2)
                mbps_out = round(bytes_out_rate * 8 / 1_000_000, 2)

                # Get interface speed for utilization calculation
                speed_mbps = 0
                if iface in iface_stats and iface_stats[iface].speed > 0:
                    speed_mbps = iface_stats[iface].speed

                # Calculate utilization %
                utilization = 0
                if speed_mbps > 0:
                    utilization = round((mbps_in + mbps_out) / speed_mbps * 100, 1)

                result[iface] = {
                    "interface": iface,
                    "bytes_in": round(bytes_in_rate),
                    "bytes_out": round(bytes_out_rate),
                    "mbps_in": mbps_in,
                    "mbps_out": mbps_out,
                    "speed_mbps": speed_mbps,
                    "utilization": utilization,
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
    """Periodic bandwidth logging to database with traffic alerts."""
    bw = get_bandwidth()
    for iface, data in bw.items():
        db.add_bandwidth_log(iface, data.get("bytes_in", 0), data.get("bytes_out", 0))

        # Traffic alerts
        util = data.get("utilization", 0)
        if util > 80:
            db.add_alert("crit", f"High bandwidth utilization on {iface}: {util}% (threshold: 80%)", iface)
        elif util > 60:
            db.add_alert("warn", f"Bandwidth utilization on {iface}: {util}%", iface)

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

        # Port scan all discovered devices in parallel
        port_results = {}
        with ThreadPoolExecutor(max_workers=50) as executor:
            port_futures = {executor.submit(scanner.scan_ports, dev["ip"]): dev["ip"] for dev in discovered}
            for future in as_completed(port_futures):
                ip = port_futures[future]
                try:
                    port_results[ip] = future.result()
                except Exception:
                    port_results[ip] = []

        for dev in discovered:
            is_new = dev["mac"] not in known_macs and dev["mac"] != "N/A"
            open_ports_str = scanner.format_ports(port_results.get(dev["ip"], []))
            device_id = db.upsert_device(
                ip=dev["ip"],
                mac=dev["mac"],
                device_name=dev["device_name"],
                device_type=_classify_device(dev),
                os_guess=dev.get("os_guess", "Unknown"),
                status="up",
                ping_ms=0,
                open_ports=open_ports_str,
            )

            if is_new:
                new_devices += 1
                db.add_alert("new", f"New device detected: {dev['device_name']} ({dev['ip']})", dev["ip"])

        # Ping all known devices in parallel
        devices = db.get_devices()
        ping_results = {}

        def _ping_device(device):
            ip = device["ip_address"]
            result = scanner.ping_host(ip)
            return ip, result, device

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(_ping_device, d) for d in devices]
            for future in as_completed(futures):
                try:
                    ip, result, device = future.result()
                    ping_results[ip] = (result, device)
                except Exception:
                    pass

        # Process results (failure tracking + alerts + DB updates)
        for device in devices:
            ip = device["ip_address"]
            if ip not in ping_results:
                continue
            result, _ = ping_results[ip]
            status = result["status"]
            ping_ms = result["ping_ms"]

            # Track consecutive failures
            if status == "down":
                _consecutive_failures[ip] = _consecutive_failures.get(ip, 0) + 1
                if _consecutive_failures[ip] >= 3:
                    status = "down"
                    if _consecutive_failures[ip] == 3:
                        db.add_alert("crit", f"{device['device_name']} ({ip}) — Host unreachable: 3 consecutive failures", ip)
            else:
                if ip in _consecutive_failures and _consecutive_failures[ip] >= 3:
                    db.add_alert("info", f"{device['device_name']} ({ip}) — Device back online", ip)
                _consecutive_failures[ip] = 0

            # Latency warning
            if status == "up" and ping_ms > 30:
                if ping_ms > 100:
                    db.add_alert("crit", f"{device['device_name']} ({ip}) — Critical latency: {ping_ms:.0f}ms", ip)
                else:
                    db.add_alert("warn", f"{device['device_name']} ({ip}) — High latency: {ping_ms:.0f}ms (threshold: 30ms)", ip)

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
    """Classify device type based on device_name, MAC OUI, and OS guess."""
    host = (dev.get("device_name") or "").lower()
    mac = (dev.get("mac") or "").upper()
    os_guess = (dev.get("os_guess") or "").lower()

    # By hostname keywords
    if any(k in host for k in ("router", "gateway", "gw", "rt-")):
        return "Router"
    if any(k in host for k in ("switch", "sw-", "sw_")):
        return "Switch"
    if any(k in host for k in ("firewall", "fw-", "fw_")):
        return "Firewall"
    if any(k in host for k in ("srv", "server", "dc-", "dns-")):
        return "Server"
    if "nas" in host:
        return "NAS"
    if any(k in host for k in ("ap-", "ap_", "wifi", "wap", "wlan")):
        return "Access Point"
    if any(k in host for k in ("cam", "camera", "ipc", "nvr")):
        return "Camera"
    if any(k in host for k in ("printer", "print", "mfp", "laserjet", "deskjet", "epson", "canon", "brother")):
        return "Printer"
    if any(k in host for k in ("phone", "voip", "sip-", "yealink", "polycom", "cisco-spa")):
        return "VoIP Phone"
    if any(k in host for k in ("laptop", "notebook", "macbook", "thinkpad")):
        return "Laptop"
    if any(k in host for k in ("desktop", "workstation", "ws-", "pc-")):
        return "Desktop PC"
    if any(k in host for k in ("android", "galaxy", "pixel", "redmi", "poco", "oneplus", "huawei", "honor", "oppo", "vivo", "realme")):
        return "Mobile Phone"
    if any(k in host for k in ("iphone", "ipad", "ipod")):
        return "Mobile Device"
    if any(k in host for k in ("fire-tv", "roku", "chromecast", "appletv", "smart-tv", "tv-")):
        return "Smart TV"
    if any(k in host for k in ("echo", "alexa", "google-home", "homepod")):
        return "Smart Speaker"
    if any(k in host for k in ("xbox", "playstation", "nintendo", "ps4", "ps5", "switch-")):
        return "Gaming Console"
    if any(k in host for k in ("espressif", "esp32", "esp8266", "arduino", "raspberry", "rpi")):
        return "IoT Device"

    # By MAC OUI classification
    if "printer" in os_guess:
        return "Printer"
    if "camera" in os_guess:
        return "Camera"
    # Android brand names (Samsung, Huawei, Xiaomi, OnePlus)
    if any(b in os_guess for b in ("samsung", "huawei", "xiaomi", "oneplus", "android")):
        return "Mobile Phone"
    if "ios" in os_guess:
        return "Mobile Device"
    if "macos" in os_guess:
        return "Mac"
    if "windows" in os_guess:
        return "Desktop PC"
    if "linux" in os_guess:
        return "Server"
    if "router" in os_guess or "cisco" in os_guess:
        return "Router"
    if "access point" in os_guess:
        return "Access Point"
    if "voip" in os_guess:
        return "VoIP Phone"
    if "network device" in os_guess:
        return "Network Device"
    if "google" in os_guess:
        return "Smart Device"

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
        cleanup_counter = 0
        while _scheduler_running:
            try:
                run_scan()
                log_bandwidth()

                # Run data retention every 10 cycles (5 minutes at 30s interval)
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    deleted = db.cleanup_old_data(hours=24)
                    if deleted > 0:
                        print(f"[scheduler] Cleaned up {deleted} old bandwidth records")
                    cleanup_counter = 0
            except Exception as e:
                print(f"[scheduler] Error: {e}")
            time.sleep(interval_sec)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    print(f"[scheduler] Background scan started (every {interval_sec}s)")
