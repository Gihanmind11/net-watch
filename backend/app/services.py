"""Application services shared by API routers and the background scheduler."""

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from . import models
from .config import get_settings
from .database import SessionLocal
from .events import get_broker
from .monitor import BandwidthSampler, ProtocolMonitor
from .scanner import arp_table, get_default_gateway, get_network_cidr, ping_host, run_discovery, usable_unicast_mac

settings = get_settings()

bandwidth_sampler = BandwidthSampler()
protocol_monitor = ProtocolMonitor(settings.sniffing_enabled)

_gateway_cache: dict[str, float] = {"ip": "", "ts": 0.0}
_GATEWAY_CACHE_TTL = 30.0


def current_gateway() -> str:
    """Default gateway (the hotspot host) with a short TTL cache."""
    now = time.monotonic()
    if now - _gateway_cache["ts"] > _GATEWAY_CACHE_TTL:
        _gateway_cache["ip"] = get_default_gateway()
        _gateway_cache["ts"] = now
    return _gateway_cache["ip"]


def utcnow() -> datetime:
    return models.utcnow()


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


async def publish(event_type: str, payload: dict) -> None:
    broker = get_broker()
    if broker is not None:
        await broker.publish({"type": event_type, "payload": payload})


# ---------------- payload builders ----------------

def device_payload(device: models.Device) -> dict:
    return {
        "id": device.id,
        "device_name": device.hostname or device.ip_address,
        "hostname": device.hostname or device.ip_address,
        "ip": device.ip_address,
        "mac": device.mac_address or "",
        "type": device.device_type or "Device",
        "os": device.os_guess or "",
        "status": device.status or "unknown",
        "ping_ms": round(device.ping_ms or 0.0, 1),
        "uptime_pct": round(device.uptime_pct or 0.0, 1),
        "open_ports": device.open_ports or "",
        "last_seen": device.last_seen.isoformat(timespec="seconds") if device.last_seen else None,
        "first_seen": device.first_seen.isoformat(timespec="seconds") if device.first_seen else None,
        "vendor": device.vendor or "",
        "is_gateway": bool(device.ip_address and device.ip_address == current_gateway()),
    }


def devices_payload() -> dict:
    with SessionLocal() as db:
        devices = db.scalars(select(models.Device).order_by(models.Device.ip_address)).all()
    items = [device_payload(d) for d in devices]
    return {"count": len(items), "devices": items}


def alert_payload(alert: models.Alert) -> dict:
    return {
        "id": alert.id,
        "level": alert.level,
        "message": alert.message,
        "device_ip": alert.device_ip or None,
        "created_at": alert.created_at.isoformat(timespec="seconds") if alert.created_at else None,
    }


def alerts_payload() -> dict:
    with SessionLocal() as db:
        alerts = db.scalars(
            select(models.Alert)
            .where(models.Alert.resolved == 0)
            .order_by(models.Alert.created_at.desc())
            .limit(100)
        ).all()
    items = [alert_payload(a) for a in alerts]
    return {
        "count": len(items),
        "alerts": items,
        "critical": sum(1 for a in items if a["level"] == "crit"),
        "warning": sum(1 for a in items if a["level"] == "warn"),
        "new": sum(1 for a in items if a["level"] == "new"),
        "new_devices": sum(1 for a in items if a["level"] == "new"),
        "info": sum(1 for a in items if a["level"] == "info"),
    }


def stats_payload() -> dict:
    with SessionLocal() as db:
        devices = db.scalars(select(models.Device)).all()
        new_count = db.scalar(
            select(func.count())
            .select_from(models.Alert)
            .where(models.Alert.level == "new", models.Alert.resolved == 0)
        )
    online = sum(1 for d in devices if d.status == "up")
    offline = sum(1 for d in devices if d.status == "down")
    warning = sum(1 for d in devices if d.status == "warn")
    live = [d for d in devices if d.status in ("up", "warn")]
    avg = round(sum(d.ping_ms or 0 for d in live) / len(live), 1) if live else 0.0
    return {
        "total_devices": len(devices),
        "online": online,
        "offline": offline,
        "warning": warning,
        "avg_latency": avg,
        "new_devices": int(new_count or 0),
    }


def bandwidth_payload() -> dict:
    current: dict[str, dict] = {}
    for s in bandwidth_sampler.last_snapshot():
        current[s["interface"]] = {
            "interface": s["interface"],
            "mbps_in": round(s["mbps_in"], 2),
            "mbps_out": round(s["mbps_out"], 2),
            "speed_mbps": s["speed_mbps"],
            "utilization": round(min(s["utilization"], 99.0), 1),
            "total_in": s["total_in"],
            "total_out": s["total_out"],
            "packets_in": s["packets_in"],
            "packets_out": s["packets_out"],
            "errors_in": s["errors_in"],
            "errors_out": s["errors_out"],
            "drops_in": s["drops_in"],
            "drops_out": s["drops_out"],
        }
    with SessionLocal() as db:
        rows = db.scalars(
            select(models.BandwidthLog).order_by(models.BandwidthLog.recorded_at.desc()).limit(72)
        ).all()
    history = [
        {
            "recorded_at": r.recorded_at.isoformat(timespec="seconds"),
            "bytes_in": r.bytes_in,
            "bytes_out": r.bytes_out,
        }
        for r in reversed(rows)
    ]
    return {"current": current, "history": history, "protocols": protocol_monitor.stats()}


def interfaces_payload() -> dict:
    return {"interfaces": bandwidth_sampler.interface_details()}


def top_talkers_payload() -> dict:
    with SessionLocal() as db:
        rows = db.scalars(
            select(models.BandwidthLog).order_by(models.BandwidthLog.recorded_at.desc()).limit(300)
        ).all()
    totals: dict[str, dict] = {}
    for row in rows:
        t = totals.setdefault(row.interface, {"sent_mb": 0.0, "recv_mb": 0.0})
        t["recv_mb"] += row.bytes_in / 1e6
        t["sent_mb"] += row.bytes_out / 1e6
    talkers = [
        {"device_name": name, "ip": "", "sent_mb": round(t["sent_mb"], 1), "recv_mb": round(t["recv_mb"], 1)}
        for name, t in totals.items()
    ]
    talkers.sort(key=lambda x: x["sent_mb"] + x["recv_mb"], reverse=True)
    return {"talkers": talkers[:5]}


_CORE_TYPES = {"Router", "Firewall", "Switch", "Access Point"}
_TYPE_MAP = {"Router": "router", "Firewall": "firewall", "Switch": "switch", "Access Point": "ap", "Server": "server"}


def topology_payload() -> dict:
    with SessionLocal() as db:
        devices = db.scalars(select(models.Device).order_by(models.Device.ip_address)).all()
    if not devices:
        return {"nodes": [], "edges": []}

    core = [d for d in devices if d.device_type in _CORE_TYPES or d.ip_address.endswith(".1") or d.ip_address.endswith(".254")]
    leaves = [d for d in devices if d not in core]

    nodes: list[dict] = []
    edges: list[list[str]] = []
    core_positions = [(450, 60), (450, 160), (450, 260)]
    for i, d in enumerate(core):
        x, y = core_positions[i % len(core_positions)]
        nodes.append(_topology_node(d, x, y))

    leaf_cols = [200, 310, 420, 530, 640, 750]
    for i, d in enumerate(leaves):
        x = leaf_cols[i % len(leaf_cols)]
        y = 340 + (i // len(leaf_cols)) * 130
        nodes.append(_topology_node(d, x, y))

    if core:
        for i in range(len(core) - 1):
            edges.append([f"d{core[i].id}", f"d{core[i + 1].id}"])
        parent = f"d{core[0].id}"
    elif leaves:
        parent = f"d{leaves[0].id}"
    else:
        parent = None
    if parent:
        for d in leaves:
            edges.append([parent, f"d{d.id}"])
    return {"nodes": nodes, "edges": edges}


def _topology_node(device: models.Device, x: int, y: int) -> dict:
    status = device.status if device.status in ("up", "warn", "down") else "down"
    return {
        "id": f"d{device.id}",
        "label": device.hostname or device.ip_address,
        "ip": device.ip_address,
        "type": _TYPE_MAP.get(device.device_type, "device"),
        "x": x,
        "y": y,
        "status": status,
    }


# ---------------- background jobs ----------------

_CIDR_SETTING_KEY = "last_detected_network_cidr"


def _get_setting(db, key: str) -> str:
    row = db.get(models.AppSetting, key)
    return row.value if row is not None else ""


def _set_setting(db, key: str, value: str) -> None:
    row = db.get(models.AppSetting, key)
    if row is None:
        db.add(models.AppSetting(key=key, value=value))
    else:
        row.value = value


def _upsert_device(db, entry: dict):
    device = db.scalar(select(models.Device).where(models.Device.ip_address == entry["ip"]))
    is_new = device is None
    status = entry.get("status") or "unknown"
    if device is None:
        device = models.Device(
            ip_address=entry["ip"],
            mac_address=entry.get("mac") or "",
            hostname=entry.get("hostname") or entry["ip"],
            device_type=entry.get("device_type") or "",
            os_guess=entry.get("os") or "",
            vendor=entry.get("vendor") or "",
            status=status,
            first_seen=utcnow(),
            last_seen=utcnow(),
        )
        db.add(device)
    else:
        if not device.mac_address and entry.get("mac"):
            device.mac_address = entry["mac"]
        if not device.hostname and entry.get("hostname"):
            device.hostname = entry["hostname"]
        if not device.vendor and entry.get("vendor"):
            device.vendor = entry["vendor"]
        # Always refresh type/OS from the latest discovery: an earlier scan may
        # have stored a wrong guess (e.g. a Windows box misread as Android via
        # a TTL-64 probe) and it must be corrected, not kept forever.
        if entry.get("device_type"):
            device.device_type = entry["device_type"]
        if entry.get("os"):
            device.os_guess = entry["os"]
        if status == "up" and device.status in ("unknown", "down"):
            device.status = "up"
            device.fail_count = 0
        device.last_seen = utcnow()
    return device, is_new


async def run_scan() -> dict:
    """Full discovery cycle. Returns ScanResult-shaped payload."""
    start = time.perf_counter()
    cidr = await asyncio.to_thread(get_network_cidr)
    found = await asyncio.to_thread(run_discovery, cidr)
    new_devices = 0
    with SessionLocal() as db:
        prev_cidr = _get_setting(db, _CIDR_SETTING_KEY)
        if prev_cidr and prev_cidr != cidr:
            # Network changed: drop every previously known device so only
            # real devices of the new network are shown.
            db.execute(delete(models.PingHistory))
            db.execute(delete(models.Alert))
            db.execute(delete(models.Device))
        _set_setting(db, _CIDR_SETTING_KEY, cidr)
        found_ips = {e["ip"] for e in found}
        for entry in found:
            device, is_new = _upsert_device(db, entry)
            if is_new:
                new_devices += 1
                db.add(
                    models.Alert(
                        level="new",
                        message=f"{device.hostname or device.ip_address} ({device.ip_address}) — New device joined network",
                        device_ip=device.ip_address,
                    )
                )
        if found:
            # Keep only real, currently connected devices: drop anything that
            # was not seen in this discovery AND has been quiet past the grace
            # window. Wireless clients (phones, IoT behind home broadband
            # routers) sleep often and vanish from ARP/ping briefly, so a
            # single missed scan is not proof of disconnection.
            grace_cutoff = utcnow() - timedelta(seconds=settings.stale_device_grace_sec)
            stale = [
                d
                for d in db.scalars(select(models.Device)).all()
                if d.ip_address not in found_ips and (d.last_seen or utcnow()) < grace_cutoff
            ]
            if stale:
                stale_ids = [d.id for d in stale]
                stale_ips = [d.ip_address for d in stale]
                db.execute(delete(models.PingHistory).where(models.PingHistory.device_id.in_(stale_ids)))
                db.execute(delete(models.Alert).where(models.Alert.device_ip.in_(stale_ips)))
                db.execute(delete(models.Device).where(models.Device.id.in_(stale_ids)))
        db.commit()
    duration = int((time.perf_counter() - start) * 1000)
    result = {
        "status": "complete",
        "network_cidr": cidr,
        "devices_found": len(found),
        "new_devices": new_devices,
        "scan_duration_ms": duration,
        "timestamp": iso_now(),
    }
    await publish("scan", result)
    await publish("devices", devices_payload())
    await publish("alerts", alerts_payload())
    await publish("stats", stats_payload())
    return result


async def run_ping_cycle() -> None:
    """Ping every known device, update status/uptime, raise latency & offline alerts.

    When ICMP fails, the system ARP table is consulted: many real devices
    (phones, printers, IoT) silently drop ping probes while remaining
    connected at Layer 2. A fresh unicast MAC entry counts as evidence of
    connectivity, so the device is kept "up" (with the last known latency)
    instead of being flapped to "down".
    """
    with SessionLocal() as db:
        devices = db.scalars(select(models.Device)).all()
    if not devices:
        return

    sem = asyncio.Semaphore(settings.max_concurrent_pings)

    async def check(device: models.Device):
        async with sem:
            # Unicast the probe straight to the known MAC when we have one —
            # avoids Scapy's broadcast fallback for unresolved neighbors.
            return device, await asyncio.to_thread(ping_host, device.ip_address, 1000, device.mac_address or "")

    results = await asyncio.gather(*(check(d) for d in devices))
    now = utcnow()

    # One ARP read per cycle (cheap) to arbitrate ICMP failures.
    need_arp = any(reply is None for _d, reply in results)
    arp_cache = arp_table() if need_arp else {}

    with SessionLocal() as db:
        history: list[models.PingHistory] = []
        for device, reply in results:
            live = db.get(models.Device, device.id)
            if live is None:
                continue
            if reply is None and arp_cache:
                mac = arp_cache.get(live.ip_address, "")
                if usable_unicast_mac(mac):
                    # L2-reachable (ping-blocked device): keep alive without
                    # inventing a fake latency value.
                    live.total_checks += 1
                    live.total_ups += 1
                    live.fail_count = 0
                    if live.status == "down":
                        live.status = "up"
                        db.add(
                            models.Alert(
                                level="info",
                                message=f"{live.hostname} ({live.ip_address}) — Device recovered",
                                device_ip=live.ip_address,
                            )
                        )
                    history.append(models.PingHistory(device_id=live.id, ping_ms=live.ping_ms or 0.0, status=live.status, checked_at=now))
                    live.last_seen = now
                    continue
            live.total_checks += 1
            if reply is None:
                live.fail_count += 1
                live.ping_ms = 0.0
                if live.fail_count >= settings.ping_fail_count and live.status != "down":
                    live.status = "down"
                    db.add(
                        models.Alert(
                            level="crit",
                            message=f"{live.hostname} ({live.ip_address}) — Host unreachable: {live.fail_count} consecutive failures",
                            device_ip=live.ip_address,
                        )
                    )
                history.append(models.PingHistory(device_id=live.id, ping_ms=0.0, status="down", checked_at=now))
            else:
                ms, ttl = reply
                live.fail_count = 0
                live.ping_ms = ms
                live.total_ups += 1
                if live.status == "down":
                    live.status = "up"
                    db.add(
                        models.Alert(
                            level="info",
                            message=f"{live.hostname} ({live.ip_address}) — Device recovered",
                            device_ip=live.ip_address,
                        )
                    )
                if ms >= settings.latency_crit_ms:
                    if live.status != "warn":
                        live.status = "warn"
                        db.add(
                            models.Alert(
                                level="crit",
                                message=f"{live.hostname} ({live.ip_address}) — High latency: {ms:.0f}ms (threshold: {settings.latency_crit_ms}ms)",
                                device_ip=live.ip_address,
                            )
                        )
                elif ms >= settings.latency_warn_ms:
                    if live.status != "warn":
                        live.status = "warn"
                        db.add(
                            models.Alert(
                                level="warn",
                                message=f"{live.hostname} ({live.ip_address}) — Latency spike: {ms:.0f}ms detected (threshold: {settings.latency_warn_ms}ms)",
                                device_ip=live.ip_address,
                            )
                        )
                elif live.status == "warn":
                    live.status = "up"
                history.append(models.PingHistory(device_id=live.id, ping_ms=ms, status=live.status, checked_at=now))
            live.uptime_pct = round(100.0 * live.total_ups / max(1, live.total_checks), 1)
            live.last_seen = now
        db.add_all(history)
        db.commit()

    await publish("devices", devices_payload())
    await publish("alerts", alerts_payload())
    await publish("stats", stats_payload())


async def run_bandwidth_cycle() -> None:
    snapshots = await asyncio.to_thread(bandwidth_sampler.snapshot)
    if not snapshots:
        return
    with SessionLocal() as db:
        db.add_all(
            models.BandwidthLog(
                interface=s["interface"],
                bytes_in=int(s["bytes_sec_in"]),
                bytes_out=int(s["bytes_sec_out"]),
                recorded_at=utcnow(),
            )
            for s in snapshots
        )
        db.commit()
    await publish("bandwidth", bandwidth_payload())


async def cleanup_old_logs() -> None:
    cutoff = utcnow() - timedelta(days=settings.history_retention_days)
    alert_cutoff = utcnow() - timedelta(days=30)
    with SessionLocal() as db:
        db.execute(delete(models.BandwidthLog).where(models.BandwidthLog.recorded_at < cutoff))
        db.execute(delete(models.PingHistory).where(models.PingHistory.checked_at < cutoff))
        db.execute(delete(models.Alert).where(models.Alert.resolved == 1, models.Alert.created_at < alert_cutoff))
        db.commit()


# ---------------- demo seed ----------------

_DEMO_DEVICES = [
    {"hostname": "gateway-01", "ip_address": "192.168.1.1", "mac_address": "A4:8C:01:FF:22:11", "device_type": "Router", "os_guess": "RouterOS", "status": "up", "ping_ms": 4.0, "uptime_pct": 99.9, "open_ports": "80,443,22", "vendor": "Cisco"},
    {"hostname": "core-switch", "ip_address": "192.168.1.2", "mac_address": "B0:CD:02:AA:33:44", "device_type": "Switch", "os_guess": "SwitchOS", "status": "up", "ping_ms": 2.0, "uptime_pct": 99.8, "open_ports": "22,23", "vendor": "Cisco"},
    {"hostname": "srv-web-01", "ip_address": "192.168.1.10", "mac_address": "C2:EF:03:BB:55:66", "device_type": "Server", "os_guess": "Ubuntu Server 22.04", "status": "up", "ping_ms": 8.0, "uptime_pct": 99.5, "open_ports": "80,443,22"},
    {"hostname": "srv-db-01", "ip_address": "192.168.1.11", "mac_address": "D4:10:04:CC:77:88", "device_type": "Server", "os_guess": "Ubuntu Server 22.04", "status": "up", "ping_ms": 6.0, "uptime_pct": 99.7, "open_ports": "3306,22"},
    {"hostname": "srv-mail", "ip_address": "192.168.1.12", "mac_address": "E6:32:05:DD:99:AA", "device_type": "Server", "os_guess": "Debian 12", "status": "warn", "ping_ms": 42.0, "uptime_pct": 97.2, "open_ports": "25,587,993,22"},
    {"hostname": "workstation-01", "ip_address": "192.168.1.20", "mac_address": "F8:54:06:EE:BB:CC", "device_type": "PC", "os_guess": "Windows 11 Pro", "status": "up", "ping_ms": 12.0, "uptime_pct": 95.1, "open_ports": "135,445,3389"},
    {"hostname": "workstation-02", "ip_address": "192.168.1.21", "mac_address": "0A:76:07:FF:DD:EE", "device_type": "PC", "os_guess": "Windows 10 Pro", "status": "up", "ping_ms": 15.0, "uptime_pct": 92.3, "open_ports": "135,445"},
    {"hostname": "workstation-03", "ip_address": "192.168.1.22", "mac_address": "1C:98:08:00:FF:11", "device_type": "PC", "os_guess": "Windows 11 Pro", "status": "up", "ping_ms": 11.0, "uptime_pct": 94.8, "open_ports": "135,445"},
    {"hostname": "laptop-ceo", "ip_address": "192.168.1.30", "mac_address": "2E:BA:09:11:22:33", "device_type": "Laptop", "os_guess": "macOS Sonoma", "status": "up", "ping_ms": 22.0, "uptime_pct": 78.5, "open_ports": "22,5900"},
    {"hostname": "printer-floor1", "ip_address": "192.168.1.40", "mac_address": "40:DC:0A:22:44:55", "device_type": "Printer", "os_guess": "Firmware", "status": "down", "ping_ms": 0.0, "uptime_pct": 81.0, "open_ports": ""},
    {"hostname": "ip-cam-01", "ip_address": "192.168.1.50", "mac_address": "52:FE:0B:33:66:77", "device_type": "Camera", "os_guess": "Firmware", "status": "up", "ping_ms": 18.0, "uptime_pct": 99.1, "open_ports": "80,554"},
    {"hostname": "ip-cam-02", "ip_address": "192.168.1.51", "mac_address": "64:10:0C:44:88:99", "device_type": "Camera", "os_guess": "Firmware", "status": "down", "ping_ms": 0.0, "uptime_pct": 85.3, "open_ports": ""},
    {"hostname": "nas-storage", "ip_address": "192.168.1.60", "mac_address": "76:32:0D:55:AA:BB", "device_type": "NAS", "os_guess": "Synology DSM", "status": "up", "ping_ms": 9.0, "uptime_pct": 99.6, "open_ports": "80,443,5000,22"},
    {"hostname": "wifi-ap-01", "ip_address": "192.168.1.70", "mac_address": "88:54:0E:66:CC:DD", "device_type": "Access Point", "os_guess": "Firmware", "status": "up", "ping_ms": 5.0, "uptime_pct": 99.3, "open_ports": "80"},
    {"hostname": "wifi-ap-02", "ip_address": "192.168.1.71", "mac_address": "9A:76:0F:77:EE:FF", "device_type": "Access Point", "os_guess": "Firmware", "status": "warn", "ping_ms": 88.0, "uptime_pct": 96.0, "open_ports": "80"},
    {"hostname": "phone-ext-101", "ip_address": "192.168.1.80", "mac_address": "AC:98:10:88:11:22", "device_type": "VoIP", "os_guess": "Firmware", "status": "up", "ping_ms": 7.0, "uptime_pct": 98.2, "open_ports": "5060,5061"},
    {"hostname": "phone-ext-102", "ip_address": "192.168.1.81", "mac_address": "BE:BA:11:99:33:44", "device_type": "VoIP", "os_guess": "Firmware", "status": "up", "ping_ms": 8.0, "uptime_pct": 97.9, "open_ports": "5060,5061"},
    {"hostname": "firewall", "ip_address": "192.168.1.254", "mac_address": "D0:DC:12:AA:55:66", "device_type": "Firewall", "os_guess": "pfSense", "status": "up", "ping_ms": 3.0, "uptime_pct": 99.9, "open_ports": "443,22"},
]

_DEMO_ALERTS = [
    {"level": "crit", "message": "srv-mail (192.168.1.12) — High latency: 42ms (threshold: 30ms)", "device_ip": "192.168.1.12"},
    {"level": "warn", "message": "wifi-ap-02 (192.168.1.71) — Latency spike: 88ms detected", "device_ip": "192.168.1.71"},
    {"level": "warn", "message": "printer-floor1 (192.168.1.40) — Host unreachable, 3 consecutive failures", "device_ip": "192.168.1.40"},
    {"level": "info", "message": "ip-cam-02 (192.168.1.51) — Device went offline", "device_ip": "192.168.1.51"},
    {"level": "new", "message": "workstation-05 (192.168.1.24) — New device joined network", "device_ip": "192.168.1.24"},
    {"level": "info", "message": "core-switch — Port 14 link state change: UP", "device_ip": "192.168.1.2"},
    {"level": "info", "message": "Scheduled scan completed — 18 of 24 hosts responded"},
]


def seed_demo_if_empty() -> None:
    """Populate demo devices/alerts so the dashboard is usable before the first real scan."""
    if not settings.demo_seed_enabled:
        return
    with SessionLocal() as db:
        if db.scalar(select(models.Device.id).limit(1)) is not None:
            return
        for row in _DEMO_DEVICES:
            db.add(models.Device(**row))
        for row in _DEMO_ALERTS:
            db.add(models.Alert(**row))
        now = utcnow()
        for i in range(72):
            db.add(
                models.BandwidthLog(
                    interface="eth0",
                    bytes_in=int(3.5e6),
                    bytes_out=int(1.6e6),
                    recorded_at=now - timedelta(seconds=(71 - i) * 5),
                )
            )
        db.commit()