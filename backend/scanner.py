"""Network scanner module — ARP discovery, ICMP ping, hostname resolution."""

import subprocess
import platform
import socket
import re
import os
import sys
import io

try:
    # Suppress scapy's "No libpcap provider available" warning on import
    _stderr_backup = sys.stderr
    sys.stderr = io.StringIO()
    try:
        from scapy.all import ARP, Ether, srp, sr, IP, ICMP, conf
        conf.verb = 0
    finally:
        sys.stderr = _stderr_backup
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


def get_default_network():
    """Auto-detect the local network CIDR."""
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip = addr.address
                    # Assume /24 subnet
                    parts = ip.split(".")
                    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        pass
    return "192.168.1.0/24"


def arp_scan(network=None):
    """Send ARP broadcast and collect responses.
    Returns list of {ip, mac, hostname, os_guess}.
    """
    if network is None:
        network = get_default_network()

    if not SCAPY_AVAILABLE:
        return _fallback_scan(network)

    try:
        arp = ARP(pdst=network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = ether / arp
        result = srp(packet, timeout=3, verbose=0)[0]

        devices = []
        for sent, received in result:
            ip = received.psrc
            mac = received.hwsrc.upper()
            hostname = resolve_hostname(ip)
            os_guess = guess_os_from_mac(mac)
            devices.append({
                "ip": ip,
                "mac": mac,
                "hostname": hostname,
                "os_guess": os_guess,
            })
        return devices
    except Exception:
        # Layer 2 not available (no WinPcap/Npcap) — silently use ping fallback
        return _fallback_scan(network)


def _fallback_scan(network):
    """Fallback: ping sweep when Scapy is unavailable (e.g., no root)."""
    base = network.rsplit(".", 1)[0]
    devices = []
    for i in range(1, 255):
        ip = f"{base}.{i}"
        result = ping_host(ip)
        if result["status"] == "up":
            devices.append({
                "ip": ip,
                "mac": "N/A",
                "hostname": resolve_hostname(ip),
                "os_guess": guess_os_from_ttl(result.get("ttl", 64)),
            })
    return devices


def ping_host(ip, count=1, timeout=1):
    """Ping a host using system ping command.
    Returns {status, ping_ms, ttl}.
    """
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"

    try:
        cmd = ["ping", param, str(count), timeout_param, str(timeout), ip]
        output = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)

        if output.returncode == 0:
            ping_ms = _parse_ping_ms(output.stdout)
            ttl = _parse_ttl(output.stdout)
            return {"status": "up", "ping_ms": ping_ms, "ttl": ttl}
        else:
            return {"status": "down", "ping_ms": 0, "ttl": 0}
    except (subprocess.TimeoutExpired, Exception):
        return {"status": "down", "ping_ms": 0, "ttl": 0}


def resolve_hostname(ip):
    """Reverse DNS lookup for hostname."""
    try:
        hostname = socket.getfqdn(ip)
        if hostname == ip:
            # Try NETBIOS/nbtstat on Windows
            if platform.system().lower() == "windows":
                try:
                    out = subprocess.run(
                        ["nbtstat", "-A", ip],
                        capture_output=True, text=True, timeout=2
                    )
                    for line in out.stdout.split("\n"):
                        if "UNIQUE" in line or "GROUP" in line:
                            parts = line.split()
                            if parts and len(parts[0]) > 0:
                                return parts[0].strip()
                except Exception:
                    pass
            return ip
        return hostname
    except Exception:
        return ip


def guess_os_from_mac(mac):
    """Guess OS/device type from MAC OUI prefix."""
    if not mac or mac == "N/A":
        return "Unknown"
    prefix = mac[:8].upper()
    oui_map = {
        "A4:8C:01": "Cisco IOS",
        "B0:CD:02": "Cisco IOS",
        "D0:DC:12": "Cisco IOS",
        "C2:EF:03": "Linux Server",
        "D4:10:04": "Linux Server",
        "E6:32:05": "Linux Server",
        "F8:54:06": "Windows",
        "0A:76:07": "Windows",
        "1C:98:08": "Windows",
        "2E:BA:09": "macOS",
        "40:DC:0A": "Printer",
        "52:FE:0B": "Camera",
        "64:10:0C": "Camera",
        "76:32:0D": "NAS/Linux",
        "88:54:0E": "Access Point",
        "9A:76:0F": "Access Point",
        "AC:98:10": "VoIP Phone",
        "BE:BA:11": "VoIP Phone",
    }
    return oui_map.get(prefix, "Unknown")


def guess_os_from_ttl(ttl):
    """Guess OS from TTL value."""
    if ttl <= 64:
        return "Linux/macOS"
    elif ttl <= 128:
        return "Windows"
    else:
        return "Network Device"


def _parse_ping_ms(output):
    """Extract average ping time from ping output."""
    # Windows: "Average = 4ms"  /  Linux: "rtt min/avg/max/mdev = 4.1/4.2/4.3/0.1"
    match = re.search(r"Average\s*=\s*(\d+)", output)
    if match:
        return float(match.group(1))
    match = re.search(r"min/avg/max.*=\s*[\d.]+/([\d.]+)/", output)
    if match:
        return float(match.group(1))
    match = re.search(r"time[=<](\d+\.?\d*)", output)
    if match:
        return float(match.group(1))
    return 0


def _parse_ttl(output):
    """Extract TTL from ping output."""
    match = re.search(r"TTL=(\d+)", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 64
