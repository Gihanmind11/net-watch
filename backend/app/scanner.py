"""Device discovery: Scapy ARP scan with automatic fallbacks.

Layered discovery (robust on machines without raw-packet admin rights):
  1. Scapy ARP scan      (needs admin/root + Npcap/libpcap)
  2. ICMP ping sweep     (subprocess ping, works without admin on most OSes)
  3. System ARP cache    (`arp -a` / `ip neigh`) — merged in as a discovery
                         source, not just for MAC enrichment. Wireless clients
                         (phones, tablets, IoT, smart TVs behind a home
                         broadband router) often ignore ICMP and ARP probes,
                         yet their MACs stay in the cache after any exchange
                         through the router.

Each discovered entry is enriched with:
  - real MAC address (ARP reply or system ARP table)
  - vendor (OUI lookup)
  - hostname (reverse DNS)
  - device type (gateway / router / phone / tablet / computer / ...)
  - OS guess (TTL fingerprint + hostname + vendor hints)
"""

import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .config import get_settings

settings = get_settings()

try:
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Diffie-Hellman over finite fields .*")
        from scapy.all import ARP, Ether, ICMP, IP, sr1, srp

    HAVE_SCAPY = True

    # Scapy logs "MAC address to reach destination not found. Using
    # broadcast." for every IP probe sent without a resolved neighbor —
    # normal behaviour on a fresh cache, pure console noise here.
    import logging

    for _scapy_log in ("scapy.runtime", "scapy.sendrecv"):
        logging.getLogger(_scapy_log).setLevel(logging.ERROR)
except Exception:
    HAVE_SCAPY = False

_IS_WINDOWS = platform.system().lower() == "windows"

# OUI prefixes -> vendor. Ordered by first 6 hex digits of the MAC.
_VENDOR_OUIS = {
    "A4:8C:01": "Cisco",
    "B0:CD:02": "Cisco",
    "00:1A:A9": "Hewlett Packard",
    "00:1B:21": "Intel",
    "3C:D9:2B": "Dell",
    "F8:75:A4": "Dell",
    "00:16:CB": "Apple",
    "3C:22:FB": "Apple",
    "A4:83:E7": "Apple",
    "F0:18:98": "Apple",
    "70:9E:29": "Samsung",
    "00:23:24": "Samsung",
    "5C:E8:EB": "Samsung",
    "88:66:5A": "TP-Link",
    "50:C7:BF": "TP-Link",
    "F4:F2:6D": "TP-Link",
    "00:0C:29": "VMware",
    "00:50:56": "VMware",
    "08:00:27": "Oracle VirtualBox",
    "44:4C:A8": "Google",
    "9C:FC:E8": "Google",
    "B4:5D:50": "Xiaomi",
    "64:CC:2E": "Xiaomi",
    "28:6C:07": "Xiaomi",
    "48:0F:CF": "Huawei",
    "00:E0:FC": "Huawei",
    "8C:1F:64": "Huawei",
    "F0:9F:C2": "D-Link",
    "28:10:7B": "D-Link",
    "C0:3F:0E": "Netgear",
    "20:E5:2A": "Netgear",
    "AC:84:C6": "Netgear",
    "50:46:4D": "Motorola",
    "00:9A:CD": "HMD/Nokia",
    "04:C5:A4": "Tecno",
    "A0:CE:C8": "Infinix",
    "B0:41:1A": "Sony",
    "F8:95:C7": "Oppo",
    "2C:8A:72": "Oppo",
    "FC:64:BA": "OnePlus",
    "40:88:05": "LG",
    "58:C3:8B": "Asus",
    "04:D9:F5": "Asus",
    "E8:48:B8": "Asus",
    "00:22:FB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    "B8:27:EB": "Raspberry Pi",
}

# Vendors that are almost always network infrastructure
_ROUTER_VENDORS = {"Cisco", "TP-Link", "Netgear", "D-Link", "Huawei", "Asus", "Linksys"}


def get_network_cidr() -> str:
    """Auto-detect the active local network from OS interfaces.

    Picks the interface whose subnet contains the default gateway (the real
    uplink), falling back to the first private non-link-local IPv4 interface,
    then to the NETWORK_CIDR env setting. Uses the real netmask when available.
    """
    try:
        import psutil
    except ImportError:
        return settings.network_cidr

    candidates: list[ipaddress.IPv4Network] = []
    for _name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family != socket.AF_INET or addr.address.startswith("127."):
                continue
            try:
                net = ipaddress.ip_network(f"{addr.address}/{addr.netmask}", strict=False)
            except (ValueError, TypeError):
                net = ipaddress.ip_network(f"{addr.address}/24", strict=False)
            if net.network_address.is_link_local:
                # Skip disconnected-adapter APIPA subnets (169.254.0.0/16) —
                # common on home machines with unused Ethernet ports.
                continue
            candidates.append(net)

    if not candidates:
        return settings.network_cidr

    gateway = get_default_gateway()
    if gateway:
        try:
            gw_ip = ipaddress.ip_address(gateway)
            for net in candidates:
                if gw_ip in net:
                    return str(net)
        except ValueError:
            pass

    # Home broadband routers hand out RFC1918 space (192.168.x, 10.x, 172.16-31.x).
    private = [n for n in candidates if n.network_address.is_private]
    return str(private[0] if private else candidates[0])


def get_default_gateway() -> str:
    """Best-effort default gateway IP via routing table (no admin needed).

    IPv4-only: IPv6 link-local gateways (fe80::...) are ignored so the
    returned address always matches the LAN device inventory.
    """
    try:
        if _IS_WINDOWS:
            # `route print -4` is the most reliable IPv4-only gateway source.
            out = subprocess.run(
                ["route", "print", "-4"], capture_output=True, text=True, timeout=10
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                # "0.0.0.0          0.0.0.0      192.168.8.1    192.168.8.102     25"
                if (
                    len(parts) >= 3
                    and parts[0] == "0.0.0.0"
                    and parts[1] == "0.0.0.0"
                    and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[2])
                    and parts[2] != "0.0.0.0"
                ):
                    return parts[2]
            # Fallback: ipconfig, IPv4 gateways only.
            out = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=10
            ).stdout
            for line in out.splitlines():
                if "Default Gateway" in line and ":" in line:
                    gw = line.split(":", 1)[1].strip()
                    if gw and re.match(r"^\d+\.\d+\.\d+\.\d+$", gw):
                        return gw
        else:
            out = subprocess.run(
                ["ip", "route"], capture_output=True, text=True, timeout=10
            ).stdout
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def arp_table() -> dict[str, str]:
    """Real IP -> MAC map from the system ARP cache (works without admin)."""
    table: dict[str, str] = {}
    try:
        if _IS_WINDOWS:
            out = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=10
            ).stdout
            # "  10.156.40.23          7e-19-36-80-1f-ab     dynamic"
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                    mac = parts[1].replace("-", ":")
                    if re.match(r"^[0-9a-fA-F:]{17}$", mac):
                        table[parts[0]] = mac.lower()
        else:
            out = subprocess.run(
                ["ip", "neigh"], capture_output=True, text=True, timeout=10
            ).stdout
            # "10.156.40.23 lladdr 7e:19:36:80:1f:ab REACHABLE"
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
                    if parts[1] == "lladdr" and re.match(r"^[0-9a-fA-F:]{17}$", parts[2]):
                        table[parts[0]] = parts[2].lower()
    except Exception:
        pass
    return table


def usable_unicast_mac(mac: str) -> bool:
    """Filter ARP junk: all-zero, broadcast and multicast MACs."""
    if not re.match(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$", mac):
        return False
    try:
        first_octet = int(mac[:2], 16)
    except ValueError:
        return False
    if first_octet & 0x01:  # multicast/broadcast bit set
        return False
    return mac != "00:00:00:00:00:00"


def randomized_mac(mac: str) -> bool:
    """True when the MAC is locally administered — i.e. a per-network
    randomized address. Phones/tablets randomize their WiFi MAC by default
    (Android/iOS), so this is strong evidence of a mobile client whenever no
    other fingerprint (TTL/vendor/hostname) is available."""
    if not usable_unicast_mac(mac):
        return False
    try:
        return bool(int(mac[:2], 16) & 0x02)  # locally administered bit
    except ValueError:
        return False


def arp_cache_hosts(cidr: str, table: dict[str, str] | None = None) -> list[dict]:
    """Devices from the system ARP cache filtered to `cidr`.

    This is the richest source of wireless clients on home broadband
    networks: phones, tablets and IoT devices that ignore ICMP and ARP
    probes still show up in the cache of the monitoring host after any
    exchange through the router.
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    if table is None:
        table = arp_table()
    hosts: list[dict] = []
    for ip, mac in table.items():
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr not in network or addr.is_multicast or addr.is_loopback:
            continue
        if addr in (network.network_address, network.broadcast_address):
            continue
        if not usable_unicast_mac(mac):
            continue
        hosts.append({"ip": ip, "mac": mac})
    return hosts


def arp_scan(cidr: str, timeout: float = 3.0) -> list[dict]:
    """Scapy ARP sweep. Returns [{'ip', 'mac'}]. Empty on failure/insufficient rights."""
    if not HAVE_SCAPY:
        return []
    try:
        arp = ARP(pdst=cidr)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        answered, _ = srp(ether / arp, timeout=timeout, verbose=0)
        return [{"ip": recv.psrc, "mac": recv.hwsrc} for _sent, recv in answered]
    except Exception:
        return []


def arp_probe(ip: str, timeout: float = 1.5) -> bool:
    """Live ARP request for one IP: True only if the host answers right now.

    This replaces the system ARP cache as liveness evidence in the ping
    cycle. Cache entries linger for minutes after a client leaves the network
    (e.g. a phone with WiFi switched off), which used to keep devices "up"
    long after they were gone. An ARP reply, by contrast, is fresh proof the
    host is reachable at Layer 2.
    """
    if not HAVE_SCAPY:
        return False
    try:
        answered, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip), timeout=timeout, verbose=0)
        return any(recv.psrc == ip and usable_unicast_mac(recv.hwsrc) for _sent, recv in answered)
    except Exception:
        return False


def _run_ping(ip: str, timeout_ms: int = 1000) -> bool:
    try:
        if _IS_WINDOWS:
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2)
        return proc.returncode == 0
    except Exception:
        return False


def ping_sweep(cidr: str, concurrency: int = 64) -> list[dict]:
    """ICMP ping sweep fallback. Returns [{'ip', 'mac': ''}]."""
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    hosts = [str(h) for h in network.hosts()][:512]
    found: list[str] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = pool.map(_run_ping, hosts)
        for host, ok in zip(hosts, results):
            if ok:
                found.append(host)
    return [{"ip": ip, "mac": ""} for ip in found]


def resolve_hostname(ip: str, timeout: float = 2.0) -> str:
    """Reverse DNS with a hard timeout.

    Windows' resolver waits ~9.5s per address-less host (DNS + NetBIOS +
    LLMNR probes), which can stall the whole scan cycle on home networks
    full of clients without PTR records. The lookup runs in a throwaway
    thread that is abandoned after `timeout` seconds.
    """
    result: list[str] = []

    def _lookup() -> None:
        try:
            result.append(socket.gethostbyaddr(ip)[0])
        except Exception:
            pass

    import threading

    worker = threading.Thread(target=_lookup, daemon=True)
    worker.start()
    worker.join(timeout)
    if not result:
        return ""
    return result[0].split(".")[0]


def oui_vendor(mac: str) -> str:
    prefix = mac.upper().replace("-", ":")[:8]
    return _VENDOR_OUIS.get(prefix, "")


def guess_os(ttl: int | None, hostname: str = "", vendor: str = "") -> str:
    """OS fingerprint: hostname hints first, then vendor, then TTL."""
    name = (hostname or "").lower()
    # Windows default machine names are DESKTOP-XXXX, LAPTOP-XXXX, PC-XXXX or
    # WIN-<12 hex chars> (the auto-generated form when no name is set). These
    # hostname hints are far more reliable than the TTL fingerprint below,
    # which is often spoofed by stacks that echo the request's TTL.
    if (
        name.startswith(("desktop-", "laptop-", "pc-", "win-"))
        or "windows" in name
        or "microsoft" in name
    ):
        return "Windows"
    if name.startswith("android-") or "android" in name:
        return "Android"
    if "iphone" in name:
        return "iOS"
    if "ipad" in name:
        return "iPadOS"
    if name.startswith(("macbook", "imac", "mac-mini")) or "mac" in name:
        return "macOS"
    if ttl is None:
        return ""
    if ttl == 255:
        return "Router OS"
    if ttl <= 64:
        if vendor == "Apple":
            return "macOS/iOS"
        return "Linux/Android"
    if ttl <= 128:
        return "Windows"
    return "Network device"


def classify_device(
    ip: str,
    gateway: str,
    mac: str = "",
    hostname: str = "",
    ttl: int | None = None,
    vendor: str = "",
) -> str:
    """Best-effort device type from gateway IP, vendor, hostname and TTL."""
    if ip == gateway:
        return "Gateway"
    if ttl == 255 or vendor in _ROUTER_VENDORS:
        return "Router"
    name = (hostname or "").lower()
    if "ipad" in name:
        return "Tablet"
    if "iphone" in name or "android-" in name or "galaxy" in name or "redmi" in name:
        return "Phone"
    if name.startswith(("desktop-", "laptop-", "pc-", "workstation", "win-", "macbook")) or "imac" in name or "windows" in name or "microsoft" in name:
        return "Computer"
    if "print" in name or vendor in ("Hewlett Packard",):
        return "Printer"
    if ttl is None and randomized_mac(mac):
        # No ICMP/TTL evidence, but the host uses a randomized (locally
        # administered) MAC — the default for phones/tablets, which also
        # tend to ignore ICMP. Report it as a mobile client instead of the
        # generic "Device" bucket.
        return "Mobile/Tablet"
    if ttl is None:
        return "Device"
    if ttl == 255:
        return "Network device"
    if ttl <= 64:
        return "Mobile/Tablet"
    if ttl <= 128:
        return "Computer"
    return "Device"


def ping_host(ip: str, timeout_ms: int = 1000, dst_mac: str = "") -> tuple[float, int | None] | None:
    """ICMP echo via Scapy (TTL + latency), falling back to subprocess ping.

    When `dst_mac` is supplied the echo request is framed with `Ether(dst=...)`
    so Scapy sends a unicast frame instead of falling back to a broadcast
    "MAC address ... not found" probe. Returns (latency_ms, ttl) or None when
    the host is unreachable.
    """
    if HAVE_SCAPY:
        try:
            # Probe with TTL 128 (the Windows default): some network stacks
            # echo the *request's* TTL in the ICMP reply, so a probe sent with
            # Scapy's default TTL=64 would fingerprint a Windows host as a
            # TTL-64 Linux/Android device.
            pkt = IP(dst=ip, ttl=128) / ICMP()
            if dst_mac and usable_unicast_mac(dst_mac):
                pkt = Ether(dst=dst_mac) / pkt
            reply = sr1(pkt, timeout=timeout_ms / 1000, verbose=0)
            if reply is not None and reply.haslayer(ICMP):
                ms = round((reply.time - pkt.sent_time) * 1000, 1)
                return max(ms, 0.1), int(reply.ttl)
        except Exception:
            pass
    try:
        if _IS_WINDOWS:
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2)
        if proc.returncode != 0:
            return None
        output = proc.stdout
        ms_match = re.search(r"time[=<]([\d.]+)\s*ms", output)
        ttl_match = re.search(r"TTL=(\d+)", output, re.IGNORECASE)
        ms = float(ms_match.group(1)) if ms_match else 0.0
        ttl = int(ttl_match.group(1)) if ttl_match else None
        return max(ms, 0.1), ttl
    except Exception:
        return None


def scan_ports(ip: str, ports: list[int] | None = None, timeout: float | None = None) -> str:
    """TCP connect-scan one host; return open ports as "80,443,22"-style text.

    `connect_ex` completes a full TCP handshake, so it needs no raw-socket
    privileges (unlike a SYN scan) and works on Windows without Npcap. A single
    short timeout per port bounds hosts that silently drop packets instead of
    sending RST.
    """
    ports = ports if ports is not None else settings.port_scan_port_list
    timeout = timeout if timeout is not None else settings.port_scan_timeout_sec
    opened: list[int] = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                if sock.connect_ex((ip, port)) == 0:
                    opened.append(port)
        except OSError:
            continue
    return ",".join(str(p) for p in opened)


def _enrich_entry(entry: dict, gateway: str, arp_cache: dict[str, str] | None = None) -> dict:
    """Fill hostname, real MAC, vendor, TTL, latency, type and OS for one host."""
    ip = entry["ip"]
    entry["hostname"] = resolve_hostname(ip)
    if not entry.get("mac"):
        entry["mac"] = (arp_cache if arp_cache is not None else arp_table()).get(ip, "")
    entry["vendor"] = oui_vendor(entry["mac"]) if entry.get("mac") else ""
    reply = ping_host(ip, dst_mac=entry.get("mac") or "")
    ttl = None
    if reply is not None:
        ttl = reply[1]
        entry["ping_ms"] = reply[0]
        entry["status"] = "up"
    elif entry.get("mac"):
        # No ICMP reply but a real unicast MAC: the device is reachable at
        # Layer 2 (typical for phones/printers/IoT that block ping). Report
        # it as up immediately instead of leaving "unknown" until the next
        # ping cycle.
        entry["status"] = "up"
    entry["ttl"] = ttl
    entry["device_type"] = classify_device(ip, gateway, entry.get("mac") or "", entry["hostname"], ttl, entry["vendor"])
    entry["os"] = guess_os(ttl, entry["hostname"], entry["vendor"])
    # Only reachable hosts are worth probing; setting the key only when a scan
    # ran lets _upsert_device keep the last known ports for a host that is
    # merely asleep instead of wiping them.
    if settings.port_scan_enabled and entry.get("status") == "up":
        entry["open_ports"] = scan_ports(ip)
    return entry


def run_discovery(cidr: str) -> list[dict]:
    """Full discovery: ARP scan first, ping sweep fallback, then enrich.

    The system ARP cache is always merged in (one `arp -a` call per run).
    On wireless home networks many clients sleep through ICMP and ARP
    probes but remain registered in the cache, so they are still shown as
    connected devices.
    """
    cache = arp_table()
    by_ip: dict[str, dict] = {}
    for entry in arp_scan(cidr):
        by_ip.setdefault(entry["ip"], entry)
    if not by_ip:
        for entry in ping_sweep(cidr):
            by_ip.setdefault(entry["ip"], entry)
    for entry in arp_cache_hosts(cidr, cache):
        existing = by_ip.get(entry["ip"])
        if existing is None:
            by_ip[entry["ip"]] = entry
        elif not existing.get("mac") and entry.get("mac"):
            existing["mac"] = entry["mac"]
    gateway = get_default_gateway()
    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(lambda e: _enrich_entry(e, gateway, cache), by_ip.values()))