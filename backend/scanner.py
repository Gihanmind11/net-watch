"""Network scanner module — ARP discovery, ICMP ping, hostname resolution."""

import subprocess
import platform
import socket
import re
import os
import sys
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def get_all_networks():
    """Detect ALL local network CIDRs across every interface (no filtering)."""
    networks = []
    seen = set()
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip.startswith("127."):
                        continue
                    parts = ip.split(".")
                    cidr = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
                    if cidr not in seen:
                        seen.add(cidr)
                        networks.append(cidr)
    except Exception:
        pass

    # Fallback: use socket to get local IP
    if not networks:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            parts = ip.split(".")
            networks.append(f"{parts[0]}.{parts[1]}.{parts[2]}.0/24")
        except Exception:
            networks.append("192.168.1.0/24")

    return networks


def get_default_network():
    """Return the primary local network CIDR (for backward compat)."""
    nets = get_all_networks()
    # Prefer 192.168.x.x
    for n in nets:
        if n.startswith("192.168."):
            return n
    return nets[0] if nets else "192.168.1.0/24"


def arp_scan(network=None):
    """Send ARP broadcast and collect responses across ALL networks.
    Returns list of {ip, mac, device_name, os_guess}.
    """
    if network is not None:
        networks = [network]
    else:
        networks = get_all_networks()

    if not SCAPY_AVAILABLE:
        all_devices = []
        for net in networks:
            all_devices.extend(_fallback_scan(net))
        return _deduplicate(all_devices)

    # Scan all networks with Scapy
    all_raw = []
    fallback_devices = []
    for net in networks:
        try:
            arp = ARP(pdst=net)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether / arp
            result = srp(packet, timeout=3, verbose=0)[0]
            for sent, received in result:
                all_raw.append((received.psrc, received.hwsrc.upper()))
        except Exception:
            # Layer 2 not available for this network — try ping fallback
            fallback_devices.extend(_fallback_scan(net))

    # Deduplicate by IP (keep first MAC seen)
    seen_ips = set()
    raw = []
    for ip, mac in all_raw:
        if ip not in seen_ips:
            seen_ips.add(ip)
            raw.append((ip, mac))

    # Parallel device name resolution + OS detection
    def _resolve(ip, mac):
        os_guess = guess_os_from_mac(mac)
        if os_guess == "Unknown":
            ping = ping_host(ip, count=1, timeout=1)
            if ping.get("status") == "up" and ping.get("ttl"):
                os_guess = guess_os_from_ttl(ping["ttl"])
        return {
            "ip": ip,
            "mac": mac,
            "device_name": resolve_hostname(ip),
            "os_guess": os_guess,
        }

    devices = list(fallback_devices)
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_resolve, ip, mac): ip for ip, mac in raw}
        for future in as_completed(futures):
            try:
                devices.append(future.result())
            except Exception:
                pass

    return _deduplicate(devices)


def _deduplicate(devices):
    """Remove duplicate devices by IP, keeping the first occurrence."""
    seen = set()
    result = []
    for d in devices:
        if d["ip"] not in seen:
            seen.add(d["ip"])
            result.append(d)
    return result


def _get_arp_table():
    """Read the system ARP table and return a dict of ip -> mac."""
    arp_map = {}
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            line = line.strip()
            parts = line.split()
            if len(parts) >= 2:
                ip = parts[0]
                mac = parts[1].upper()
                # Validate IP format
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                    # Skip broadcast/multicast
                    if mac not in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00", "FF-FF-FF-FF-FF-FF"):
                        # Normalize MAC format (replace - with :)
                        mac = mac.replace("-", ":")
                        arp_map[ip] = mac
    except Exception:
        pass
    return arp_map


def _fallback_scan(network):
    """Fallback: ping sweep when Scapy is unavailable (e.g., no root)."""
    base = network.rsplit(".", 1)[0]
    ips = [f"{base}.{i}" for i in range(1, 255)]
    devices = []

    def _ping_and_resolve(ip):
        result = ping_host(ip)
        if result["status"] == "up":
            return {
                "ip": ip,
                "mac": "N/A",  # Will be filled from ARP table
                "device_name": resolve_hostname(ip),
                "os_guess": guess_os_from_ttl(result.get("ttl", 64)),
                "ttl": result.get("ttl", 64),
            }
        return None

    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(_ping_and_resolve, ip): ip for ip in ips}
        for future in as_completed(futures):
            try:
                device = future.result()
                if device:
                    devices.append(device)
            except Exception:
                pass

    # Fill MAC addresses from system ARP table
    arp_table = _get_arp_table()
    for device in devices:
        if device["ip"] in arp_table:
            device["mac"] = arp_table[device["ip"]]
            # Re-guess OS from MAC if we got one
            mac_os = guess_os_from_mac(device["mac"])
            if mac_os != "Unknown":
                device["os_guess"] = mac_os

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
    """Guess OS/device type from real MAC OUI prefixes."""
    if not mac or mac == "N/A":
        return "Unknown"
    prefix = mac[:8].upper().replace("-", ":")

    # Real OUI prefixes from IEEE registry
    oui_map = {
        # Apple
        "00:03:93": "macOS", "00:0A:95": "macOS", "00:0D:93": "macOS",
        "00:17:F2": "macOS", "00:1B:63": "macOS", "00:1E:C2": "macOS",
        "00:26:08": "macOS", "00:26:BB": "macOS", "00:30:65": "macOS",
        "00:50:E4": "macOS", "00:C6:10": "macOS", "04:0C:CE": "macOS",
        "04:15:52": "macOS", "04:1E:64": "macOS", "04:26:65": "macOS",
        "04:54:53": "macOS", "04:69:F8": "macOS", "04:DB:56": "macOS",
        "04:D4:C4": "macOS", "04:F1:3E": "macOS", "08:00:07": "macOS",
        "08:66:98": "macOS", "08:6D:41": "macOS", "08:74:02": "macOS",
        "08:F4:AB": "macOS", "0C:3E:9F": "macOS", "0C:4D:E9": "macOS",
        "0C:74:C2": "macOS", "0C:77:1A": "macOS", "10:1C:0C": "macOS",
        "10:40:F3": "macOS", "10:41:7F": "macOS", "10:93:E9": "macOS",
        "10:DD:B1": "macOS", "14:10:9F": "macOS", "14:20:5E": "macOS",
        "14:7D:DA": "macOS", "14:8D:08": "macOS", "14:99:E2": "macOS",
        "14:BD:61": "macOS", "14:C2:13": "macOS", "18:20:32": "macOS",
        "18:34:51": "macOS", "18:65:90": "macOS", "18:AF:61": "macOS",
        "18:E1:CA": "macOS", "18:EE:69": "macOS", "1C:1A:C0": "macOS",
        "1C:36:BB": "macOS", "1C:5C:F2": "macOS", "1C:91:48": "macOS",
        "1C:9E:46": "macOS", "1C:AB:A7": "macOS", "1C:E6:2B": "macOS",
        "20:3C:AE": "macOS", "20:6E:9C": "macOS", "20:71:9E": "macOS",
        "20:78:F0": "macOS", "20:9B:CD": "macOS", "20:A2:E4": "macOS",
        "20:C9:D0": "macOS", "20:EE:28": "macOS", "24:1E:EB": "macOS",
        "24:24:0E": "macOS", "24:5B:A7": "macOS", "24:A0:74": "macOS",
        "24:A2:E1": "macOS", "24:AB:81": "macOS", "24:E0:28": "macOS",
        "24:F0:94": "macOS", "28:0B:5C": "macOS", "28:37:37": "macOS",
        "28:5A:EB": "macOS", "28:6A:B8": "macOS", "28:6A:BA": "macOS",
        "28:6C:07": "macOS", "28:A0:2B": "macOS", "28:CF:DA": "macOS",
        "28:CF:E9": "macOS", "28:E0:2C": "macOS", "28:E7:CF": "macOS",
        "28:F0:76": "macOS", "2C:1F:23": "macOS", "2C:20:0B": "macOS",
        "2C:33:61": "macOS", "2C:4D:79": "macOS", "2C:54:CF": "macOS",
        "2C:5B:B8": "macOS", "2C:61:F6": "macOS", "2C:B4:3A": "macOS",
        "2C:BE:08": "macOS", "2C:F0:A2": "macOS", "2C:F0:EE": "macOS",
        "30:10:E4": "macOS", "30:35:AD": "macOS", "30:57:14": "macOS",
        "30:63:6B": "macOS", "30:A8:DB": "macOS", "30:D5:87": "macOS",
        "30:F7:72": "macOS", "34:15:9E": "macOS", "34:23:BA": "macOS",
        "34:36:3B": "macOS", "34:51:C9": "macOS", "34:7C:25": "macOS",
        "34:A3:95": "macOS", "34:AB:37": "macOS", "34:C0:59": "macOS",
        "34:E2:FD": "macOS", "38:0F:4A": "macOS", "38:48:4C": "macOS",
        "38:53:9C": "iOS", "38:66:F0": "macOS", "38:71:DE": "macOS",
        "38:B5:4D": "macOS", "38:C9:86": "macOS", "38:F9:D3": "macOS",
        "3C:15:C2": "macOS", "3C:22:FB": "macOS", "3C:2E:FF": "macOS",
        "3C:2F:3A": "macOS", "3C:47:11": "macOS", "3C:5F:01": "macOS",
        "3C:7D:0A": "macOS", "3C:8B:FE": "macOS", "3C:97:0E": "macOS",
        "3C:AB:8E": "macOS", "3C:E0:72": "macOS", "40:30:04": "macOS",
        "40:33:1A": "iOS", "40:3C:FC": "macOS", "40:4D:7F": "macOS",
        "40:6C:8F": "macOS", "40:8B:07": "macOS", "40:9C:28": "macOS",
        "40:A6:D9": "macOS", "40:B3:95": "macOS", "40:D3:2D": "macOS",
        "40:E2:30": "macOS", "44:00:10": "macOS", "44:2A:60": "macOS",
        "44:4C:0C": "macOS", "44:65:0D": "macOS", "44:78:3E": "macOS",
        "44:D1:FA": "macOS", "44:FB:42": "macOS", "48:3B:38": "macOS",
        "48:43:7C": "macOS", "48:4B:AA": "macOS", "48:51:B7": "macOS",
        "48:60:BC": "macOS", "48:74:6E": "macOS", "48:A1:95": "macOS",
        "48:BF:6B": "macOS", "48:D7:05": "macOS", "48:E9:F1": "macOS",
        "4C:32:75": "macOS", "4C:57:CA": "macOS", "4C:74:BF": "macOS",
        "4C:7C:5F": "macOS", "4C:8D:79": "macOS", "4C:B1:9C": "macOS",
        "50:7A:55": "macOS", "50:EA:D6": "macOS", "54:26:96": "macOS",
        "54:33:CB": "macOS", "54:4E:90": "macOS", "54:72:4F": "macOS",
        "54:9A:11": "macOS", "54:AE:27": "macOS", "54:E4:3A": "macOS",
        "54:EA:A8": "macOS", "58:40:4E": "macOS", "58:55:CA": "macOS",
        "58:7F:57": "macOS", "58:B0:35": "macOS", "58:E2:8F": "macOS",
        "5C:59:48": "macOS", "5C:8D:4E": "macOS", "5C:95:AE": "macOS",
        "5C:96:9D": "macOS", "5C:F5:DA": "macOS", "5C:F7:E6": "macOS",
        "60:03:08": "macOS", "60:33:4B": "macOS", "60:69:44": "macOS",
        "60:92:17": "macOS", "60:A3:7D": "macOS", "60:F4:45": "macOS",
        "60:F8:1D": "macOS", "60:FA:CD": "macOS", "64:20:0C": "macOS",
        "64:4B:F0": "macOS", "64:5A:ED": "macOS", "64:70:02": "macOS",
        "64:9A:BE": "macOS", "64:A3:CB": "macOS", "64:A5:C3": "macOS",
        "64:B9:E8": "macOS", "64:E6:82": "macOS", "68:09:27": "macOS",
        "68:27:37": "macOS", "68:5B:35": "macOS", "68:64:4B": "macOS",
        "68:96:7B": "macOS", "68:9C:70": "macOS", "68:AB:1E": "macOS",
        "68:AE:20": "macOS", "68:D9:3C": "macOS", "68:DB:CA": "macOS",
        "68:FB:7E": "macOS", "6C:3E:6D": "macOS", "6C:40:08": "macOS",
        "6C:4D:73": "macOS", "6C:70:9F": "macOS", "6C:8D:C1": "macOS",
        "6C:94:F8": "macOS", "6C:96:CF": "macOS", "6C:AB:31": "macOS",
        "6C:C2:6B": "macOS", "70:11:24": "macOS", "70:14:A6": "macOS",
        "70:48:0F": "macOS", "70:56:81": "macOS", "70:70:0D": "macOS",
        "70:73:CB": "macOS", "70:A2:B3": "macOS", "70:CD:60": "macOS",
        "70:DE:E2": "macOS", "70:E7:2C": "macOS", "70:EC:E4": "macOS",
        "74:1B:B2": "macOS", "74:42:7F": "macOS", "74:8D:08": "macOS",
        "74:E1:9A": "macOS", "74:E2:F5": "macOS", "78:31:C1": "macOS",
        "78:3A:84": "macOS", "78:7B:8A": "macOS", "78:7E:61": "macOS",
        "78:88:6D": "macOS", "78:A3:E4": "macOS", "78:CA:39": "macOS",
        "78:D7:5F": "macOS", "78:FD:94": "macOS", "7C:01:91": "macOS",
        "7C:04:D0": "macOS", "7C:11:BE": "macOS", "7C:43:8F": "macOS",
        "7C:50:49": "macOS", "7C:6D:62": "macOS", "7C:7A:91": "macOS",
        "7C:B0:C2": "macOS", "7C:D1:C3": "macOS", "7C:F0:5F": "macOS",
        "7C:FA:DF": "macOS", "80:00:6E": "macOS", "80:49:71": "macOS",
        "80:92:9F": "macOS", "80:B0:3D": "macOS", "80:BE:05": "macOS",
        "80:D6:05": "macOS", "80:E6:50": "macOS", "80:ED:2C": "macOS",
        "84:29:99": "macOS", "84:38:35": "macOS", "84:41:67": "macOS",
        "84:7A:88": "macOS", "84:85:06": "macOS", "84:89:AD": "macOS",
        "84:B1:53": "macOS", "84:FC:FE": "macOS", "88:1F:A1": "macOS",
        "88:20:0D": "macOS", "88:53:95": "macOS", "88:63:DF": "macOS",
        "88:66:A5": "macOS", "88:6B:6E": "macOS", "88:C6:63": "macOS",
        "88:E6:60": "macOS", "88:E9:FE": "macOS", "8C:00:6D": "macOS",
        "8C:29:37": "macOS", "8C:2D:AA": "macOS", "8C:58:77": "macOS",
        "8C:7C:92": "macOS", "8C:7F:3B": "macOS", "8C:85:90": "macOS",
        "8C:8E:F2": "macOS", "8C:FA:BA": "macOS", "90:27:E4": "macOS",
        "90:49:FA": "macOS", "90:72:40": "macOS", "90:84:2B": "macOS",
        "90:B0:ED": "macOS", "90:B2:1F": "macOS", "90:C1:C6": "macOS",
        "90:FD:61": "macOS", "94:10:3E": "macOS", "94:16:25": "macOS",
        "94:E9:79": "macOS", "94:F6:A3": "macOS", "98:01:A7": "macOS",
        "98:5A:EB": "macOS", "98:9E:63": "macOS", "98:B8:E3": "macOS",
        "98:D6:BB": "macOS", "98:E0:D9": "macOS", "98:F0:AB": "macOS",
        "9C:04:EB": "macOS", "9C:20:7B": "macOS", "9C:35:EB": "macOS",
        "9C:4F:DA": "macOS", "9C:84:BF": "macOS", "9C:B4:38": "macOS",
        "9C:D2:1E": "macOS", "9C:F3:87": "macOS", "9C:F6:DD": "macOS",
        "A0:18:28": "macOS", "A0:4E:A7": "macOS", "A0:56:F3": "macOS",
        "A0:99:9B": "macOS", "A0:D7:95": "macOS", "A0:ED:CD": "macOS",
        "A4:5E:60": "macOS", "A4:67:06": "macOS", "A4:83:E7": "macOS",
        "A4:B1:97": "macOS", "A4:B8:05": "macOS", "A4:C3:61": "macOS",
        "A4:D1:8C": "macOS", "A4:D1:8F": "macOS", "A4:F1:E8": "macOS",
        "A8:20:66": "macOS", "A8:51:6B": "macOS", "A8:5C:2C": "macOS",
        "A8:66:7F": "macOS", "A8:86:DD": "macOS", "A8:88:08": "macOS",
        "A8:96:75": "macOS", "A8:BB:CF": "macOS", "A8:BE:27": "macOS",
        "A8:FA:D8": "macOS", "AC:1F:74": "macOS", "AC:29:3A": "macOS",
        "AC:3C:0B": "macOS", "AC:4E:91": "macOS", "AC:5F:3E": "macOS",
        "AC:61:EA": "macOS", "AC:7F:3E": "macOS", "AC:87:A3": "macOS",
        "AC:BC:32": "macOS", "AC:CF:5C": "macOS", "AC:DE:48": "macOS",
        "AC:E4:B5": "macOS", "AC:FD:EC": "macOS", "B0:34:95": "macOS",
        "B0:48:7A": "macOS", "B0:65:BD": "macOS", "B0:7D:47": "macOS",
        "B0:9F:BA": "macOS", "B0:BE:76": "macOS", "B0:CA:68": "macOS",
        "B4:18:D1": "macOS", "B4:4B:D2": "iOS", "B4:F0:AB": "macOS",
        "B4:F6:1C": "macOS", "B8:09:83": "macOS", "B8:17:C2": "macOS",
        "B8:41:A4": "macOS", "B8:53:AC": "macOS", "B8:63:4D": "macOS",
        "B8:78:2E": "macOS", "B8:81:98": "macOS", "B8:C1:11": "macOS",
        "B8:E8:56": "macOS", "B8:F6:B1": "macOS", "B8:FF:61": "macOS",
        "BC:3B:AF": "macOS", "BC:4C:C4": "macOS", "BC:52:B7": "macOS",
        "BC:54:36": "macOS", "BC:67:78": "macOS", "BC:6C:21": "macOS",
        "BC:92:6B": "macOS", "BC:9F:EF": "macOS", "BC:A9:20": "macOS",
        "BC:EC:5D": "macOS", "C0:1A:DA": "macOS", "C0:63:94": "macOS",
        "C0:84:7A": "macOS", "C0:9A:D0": "macOS", "C0:B6:58": "macOS",
        "C0:CC:F8": "macOS", "C0:CE:CD": "macOS", "C0:F2:FB": "macOS",
        "C4:2C:03": "macOS", "C4:61:8B": "macOS", "C4:69:F0": "macOS",
        "C4:B3:01": "macOS", "C8:1E:BF": "macOS", "C8:2A:14": "macOS",
        "C8:33:4B": "macOS", "C8:69:CD": "macOS", "C8:6F:1D": "macOS",
        "C8:85:50": "macOS", "C8:B1:EE": "macOS", "C8:BC:C8": "macOS",
        "C8:D0:83": "macOS", "C8:E0:EB": "macOS", "C8:F6:50": "macOS",
        "CC:08:8D": "macOS", "CC:20:E8": "macOS", "CC:25:EF": "macOS",
        "CC:2D:8C": "macOS", "CC:44:63": "macOS", "CC:78:5F": "macOS",
        "CC:7B:35": "macOS", "CC:C7:60": "macOS", "D0:03:4B": "macOS",
        "D0:23:DB": "macOS", "D0:33:11": "macOS", "D0:4F:7E": "macOS",
        "D0:81:7A": "macOS", "D0:A6:37": "macOS", "D0:C5:F3": "macOS",
        "D0:D2:B0": "macOS", "D4:61:9D": "macOS", "D4:61:DA": "macOS",
        "D4:90:9C": "macOS", "D4:9A:20": "macOS", "D4:A3:3D": "macOS",
        "D4:DC:CD": "macOS", "D8:00:4D": "macOS", "D8:1C:79": "macOS",
        "D8:30:62": "macOS", "D8:3C:69": "macOS", "D8:87:D5": "macOS",
        "D8:96:95": "macOS", "D8:9E:3F": "macOS", "D8:BB:2C": "macOS",
        "D8:CF:9C": "macOS", "D8:D1:CB": "macOS", "DC:0C:5C": "macOS",
        "DC:2B:2A": "macOS", "DC:2B:61": "macOS", "DC:37:45": "macOS",
        "DC:41:5F": "macOS", "DC:56:E7": "macOS", "DC:86:D8": "macOS",
        "DC:9B:9C": "macOS", "DC:A4:CA": "macOS", "DC:A9:04": "macOS",
        "E0:24:7F": "macOS", "E0:5F:45": "macOS", "E0:66:78": "macOS",
        "E0:AC:CB": "macOS", "E0:B9:BA": "macOS", "E0:C7:67": "macOS",
        "E0:C9:7A": "macOS", "E0:F5:C6": "macOS", "E0:F8:47": "macOS",
        "E4:25:E7": "macOS", "E4:2B:34": "macOS", "E4:8B:7F": "macOS",
        "E4:9A:DC": "macOS", "E4:C6:3D": "macOS", "E4:E0:A6": "macOS",
        "E8:06:88": "macOS", "E8:04:62": "macOS", "E8:2A:44": "macOS",
        "E8:36:17": "macOS", "E8:42:85": "macOS", "E8:44:7E": "macOS",
        "E8:78:29": "macOS", "E8:80:2E": "macOS", "E8:8D:28": "macOS",
        "E8:B2:AC": "macOS", "EC:35:86": "macOS", "EC:85:2F": "macOS",
        "F0:18:98": "macOS", "F0:24:75": "macOS", "F0:5B:7B": "macOS",
        "F0:72:EA": "macOS", "F0:98:9D": "macOS", "F0:99:B6": "macOS",
        "F0:B0:E7": "macOS", "F0:C1:F1": "macOS", "F0:D1:A9": "macOS",
        "F0:DB:E2": "macOS", "F0:DB:F8": "macOS", "F0:DC:E2": "macOS",
        "F4:0F:24": "macOS", "F4:37:B7": "macOS", "F4:55:9C": "macOS",
        "F4:5C:89": "macOS", "F4:F1:5A": "macOS", "F4:F9:51": "macOS",
        "F8:1E:DF": "macOS", "F8:27:93": "macOS", "F8:6E:CF": "macOS",
        "F8:FF:C2": "macOS", "FC:25:3F": "macOS", "FC:D8:48": "macOS",
        "FC:E9:98": "macOS",

        # Samsung
        "00:07:AB": "Samsung", "00:12:47": "Samsung", "00:15:99": "Samsung",
        "00:16:32": "Samsung", "00:17:D5": "Samsung", "00:18:AF": "Samsung",
        "00:1A:8A": "Samsung", "00:1B:98": "Samsung", "00:1C:43": "Samsung",
        "00:1D:25": "Samsung", "00:1E:58": "Samsung", "00:1E:E1": "Samsung",
        "00:1E:E2": "Samsung", "00:21:19": "Samsung", "00:21:4C": "Samsung",
        "00:21:D1": "Samsung", "00:21:D2": "Samsung", "00:23:39": "Samsung",
        "00:23:3A": "Samsung", "00:23:99": "Samsung", "00:23:D6": "Samsung",
        "00:23:D7": "Samsung", "00:24:54": "Samsung", "00:24:90": "Samsung",
        "00:24:91": "Samsung", "00:25:66": "Samsung", "00:25:67": "Samsung",
        "00:26:37": "Samsung", "00:26:5D": "Samsung", "18:22:7E": "Samsung",
        "24:4B:81": "Samsung", "30:CD:A7": "Samsung", "34:23:BA": "Samsung",
        "34:AA:8B": "Samsung", "38:01:97": "Samsung", "50:01:BB": "Samsung",
        "50:F5:20": "Samsung", "54:92:BE": "Samsung", "58:C3:8B": "Samsung",
        "5C:0A:5B": "Samsung", "5C:3C:27": "Samsung", "60:A1:0A": "Samsung",
        "60:D0:2C": "Samsung", "64:77:91": "Samsung", "68:27:37": "Samsung",
        "6C:F3:73": "Samsung", "74:45:CE": "Samsung", "78:25:AD": "Samsung",
        "78:40:E4": "Samsung", "78:52:1A": "Samsung", "78:BD:BC": "Samsung",
        "78:F8:82": "Samsung", "7C:0B:C6": "Samsung", "7C:F8:54": "Samsung",
        "80:65:6D": "Samsung", "84:25:DB": "Samsung", "84:38:38": "Samsung",
        "84:55:A5": "Samsung", "84:A4:66": "Samsung", "84:B5:41": "Samsung",
        "88:32:9B": "Samsung", "8C:71:F8": "Samsung", "90:18:7C": "Samsung",
        "90:F1:AA": "Samsung", "94:01:C2": "Samsung", "94:35:0A": "Samsung",
        "94:51:03": "Samsung", "94:B8:6D": "Samsung", "94:D7:71": "Samsung",
        "98:0C:82": "Samsung", "98:52:B1": "Samsung", "9C:02:98": "Samsung",
        "9C:3A:AF": "Samsung", "A0:07:98": "Samsung", "A0:0B:BA": "Samsung",
        "A0:82:1F": "Samsung", "A4:07:B6": "Samsung", "A4:84:31": "Samsung",
        "AC:36:13": "Samsung", "AC:5F:3E": "Samsung", "B0:47:BF": "Samsung",
        "B0:72:BF": "Samsung", "B0:EC:71": "Samsung", "B4:3A:28": "Samsung",
        "B4:79:A7": "Samsung", "B8:5E:7B": "Samsung", "B8:BC:1B": "Samsung",
        "BC:14:85": "Samsung", "BC:20:A4": "Samsung", "BC:44:86": "Samsung",
        "BC:72:B1": "Samsung", "BC:76:70": "Samsung", "BC:8C:CD": "Samsung",
        "C0:97:27": "Samsung", "C0:BD:D1": "Samsung", "C4:42:02": "Samsung",
        "C4:73:1E": "Samsung", "C8:14:51": "Samsung", "C8:38:70": "Samsung",
        "C8:BA:94": "Samsung", "CC:07:AB": "Samsung", "CC:3A:61": "Samsung",
        "D0:22:BE": "Samsung", "D0:25:98": "Samsung", "D0:59:E4": "Samsung",
        "D0:66:7B": "Samsung", "D0:87:E2": "Samsung", "D0:DB:32": "Samsung",
        "D4:88:90": "Samsung", "D8:57:EF": "Samsung", "D8:90:E8": "Samsung",
        "D8:C4:E9": "Samsung", "DC:71:44": "Samsung", "E0:99:71": "Samsung",
        "E0:CB:EE": "Samsung", "E0:DB:10": "Samsung", "E4:12:1D": "Samsung",
        "E4:7C:F9": "Samsung", "E4:92:FB": "Samsung", "E4:E0:C5": "Samsung",
        "E8:03:9A": "Samsung", "E8:50:8B": "Samsung", "EC:1F:72": "Samsung",
        "EC:9B:F3": "Samsung", "F0:08:F1": "Samsung", "F0:25:B7": "Samsung",
        "F0:5A:09": "Samsung", "F0:D7:AA": "Samsung", "F4:09:D8": "Samsung",
        "F4:42:8F": "Samsung", "F4:7B:5E": "Samsung", "F8:04:2E": "Samsung",
        "FC:A1:3E": "Samsung", "FC:F1:36": "Samsung",

        # Huawei
        "00:25:9E": "Huawei", "00:34:FE": "Huawei", "00:46:4B": "Huawei",
        "00:5A:13": "Huawei", "00:E0:FC": "Huawei", "04:27:58": "Huawei",
        "04:46:65": "Huawei", "04:BD:70": "Huawei", "04:C0:6F": "Huawei",
        "04:F9:38": "Huawei", "08:19:A6": "Huawei", "08:63:61": "Huawei",
        "08:7A:4C": "Huawei", "08:7B:AA": "Huawei", "08:CC:68": "Huawei",
        "08:E8:4F": "Huawei", "0C:37:DC": "Huawei", "0C:96:BF": "Huawei",
        "0C:D2:92": "Huawei", "10:1B:54": "Huawei", "10:44:00": "Huawei",
        "10:47:80": "Huawei", "10:51:72": "Huawei", "10:78:5B": "Huawei",
        "10:C6:1F": "Huawei", "14:57:9F": "Huawei", "14:89:FD": "Huawei",
        "14:B9:68": "Huawei", "18:05:36": "Huawei", "18:C5:8A": "Huawei",
        "18:DE:D7": "Huawei", "1C:1D:67": "Huawei", "1C:67:60": "Huawei",
        "1C:8E:5C": "Huawei", "1C:B7:2C": "Huawei", "1C:CF:65": "Huawei",
        "20:08:ED": "Huawei", "20:0B:C7": "Huawei", "20:2B:C1": "Huawei",
        "20:3C:AE": "Huawei", "20:4E:7F": "Huawei", "20:6E:9C": "Huawei",
        "20:A6:80": "Huawei", "20:F1:7C": "Huawei", "20:F3:A3": "Huawei",
        "24:09:95": "Huawei", "24:44:27": "Huawei", "24:69:A5": "Huawei",
        "24:DB:AC": "Huawei", "24:E5:AA": "Huawei", "28:31:52": "Huawei",
        "28:3C:E4": "Huawei", "28:41:21": "Huawei", "28:6E:D4": "Huawei",
        "28:A1:83": "Huawei", "28:CD:1C": "Huawei", "28:E3:47": "Huawei",
        "2C:AB:00": "Huawei", "2C:DC:AD": "Huawei", "30:0E:D5": "Huawei",
        "30:D1:7E": "Huawei", "30:F3:3A": "Huawei", "34:08:04": "Huawei",
        "34:29:12": "Huawei", "34:4B:50": "Huawei", "34:5B:98": "Huawei",
        "34:6A:C2": "Huawei", "34:7E:5C": "Huawei", "34:CD:BE": "Huawei",
        "34:E7:1C": "Huawei", "38:F8:89": "Huawei", "3C:47:11": "Huawei",
        "3C:5A:37": "Huawei", "3C:6A:9D": "Huawei", "3C:F8:08": "Huawei",
        "40:0D:10": "Huawei", "40:16:7E": "Huawei", "40:4D:8E": "Huawei",
        "40:5F:C2": "Huawei", "40:74:96": "Huawei", "40:CB:A8": "Huawei",
        "44:4B:5D": "Huawei", "44:55:B1": "Huawei", "44:6E:E5": "Huawei",
        "44:82:E5": "Huawei", "44:C3:46": "Huawei", "44:D8:84": "Huawei",
        "48:46:FB": "Huawei", "48:5A:3F": "Huawei", "48:AD:08": "Huawei",
        "48:DB:50": "Huawei", "48:E7:DA": "Huawei", "4C:1F:CC": "Huawei",
        "4C:54:27": "Huawei", "4C:74:03": "Huawei", "4C:8B:EF": "Huawei",
        "4C:B1:6C": "Huawei", "50:77:05": "Huawei", "50:A7:2B": "Huawei",
        "50:D4:F7": "Huawei", "54:25:EA": "Huawei", "54:39:68": "Huawei",
        "54:4A:16": "Huawei", "54:51:1B": "Huawei", "54:79:75": "Huawei",
        "54:A5:1B": "Huawei", "54:B8:0A": "Huawei", "54:E1:40": "Huawei",
        "58:1F:28": "Huawei", "58:2A:F7": "Huawei", "58:48:22": "Huawei",
        "58:60:5F": "Huawei", "58:76:C5": "Huawei", "58:7F:66": "Huawei",
        "5C:4C:A9": "Huawei", "5C:7D:5E": "Huawei", "5C:B1:3D": "Huawei",
        "5C:B3:F6": "Huawei", "5C:E0:C5": "Huawei", "60:08:10": "Huawei",
        "60:12:3C": "Huawei", "60:14:B3": "Huawei", "60:DE:44": "Huawei",
        "60:E7:01": "Huawei", "64:16:F0": "Huawei", "64:3E:8C": "Huawei",
        "64:6E:69": "Huawei", "64:A6:51": "Huawei", "64:DB:8B": "Huawei",
        "68:4F:64": "Huawei", "68:A0:F6": "Huawei", "6C:B7:49": "Huawei",
        "6C:D9:4C": "Huawei", "70:19:2F": "Huawei", "70:4E:66": "Huawei",
        "70:54:F5": "Huawei", "70:72:3C": "Huawei", "70:7B:E8": "Huawei",
        "70:8C:B6": "Huawei", "70:A8:E3": "Huawei", "70:E7:2C": "Huawei",
        "74:88:2A": "Huawei", "74:A0:63": "Huawei", "74:E5:43": "Huawei",
        "78:6A:89": "Huawei", "78:D7:52": "Huawei", "78:F5:57": "Huawei",
        "7C:11:CB": "Huawei", "7C:49:EB": "Huawei", "7C:60:97": "Huawei",
        "7C:72:E4": "Huawei", "7C:B7:33": "Huawei", "7C:E9:D3": "Huawei",
        "80:19:34": "Huawei", "80:38:BC": "Huawei", "80:71:7A": "Huawei",
        "80:B6:86": "Huawei", "80:D0:9B": "Huawei", "84:21:F1": "Huawei",
        "84:36:11": "Huawei", "84:5B:12": "Huawei", "84:79:73": "Huawei",
        "84:9F:B5": "Huawei", "84:A8:E4": "Huawei", "84:DB:AC": "Huawei",
        "88:01:F2": "Huawei", "88:12:4E": "Huawei", "88:28:B3": "Huawei",
        "88:53:D4": "Huawei", "88:66:39": "Huawei", "88:CF:98": "Huawei",
        "88:E3:AB": "Huawei", "8C:34:FD": "Huawei", "8C:79:F5": "Huawei",
        "90:17:AC": "Huawei", "90:21:55": "Huawei", "90:4E:2B": "Huawei",
        "90:67:1C": "Huawei", "90:76:9F": "Huawei", "90:B1:1C": "Huawei",
        "90:E2:BA": "Huawei", "94:04:9C": "Huawei", "94:77:2B": "Huawei",
        "94:DB:C9": "Huawei", "94:FE:22": "Huawei", "98:0D:2E": "Huawei",
        "98:22:EF": "Huawei", "98:4B:4A": "Huawei", "98:6C:F5": "Huawei",
        "98:E7:F5": "Huawei", "98:FD:B4": "Huawei", "9C:25:BE": "Huawei",
        "9C:32:CE": "Huawei", "9C:74:1A": "Huawei", "9C:A5:25": "Huawei",
        "9C:B6:D0": "Huawei", "A0:39:F7": "Huawei", "A0:51:0B": "Huawei",
        "A0:57:E3": "Huawei", "A0:63:91": "Huawei", "A0:82:C7": "Huawei",
        "A0:C5:89": "Huawei", "A4:05:9E": "Huawei", "A4:44:D1": "Huawei",
        "A4:99:47": "Huawei", "A4:BA:76": "Huawei", "A4:DC:BE": "Huawei",
        "A8:06:00": "Huawei", "A8:0C:63": "Huawei", "A8:C8:3A": "Huawei",
        "A8:E5:39": "Huawei", "AC:4E:91": "Huawei", "AC:60:89": "Huawei",
        "AC:CF:85": "Huawei", "AC:E2:15": "Huawei", "AC:E8:7B": "Huawei",
        "B0:5B:67": "Huawei", "B0:75:4D": "Huawei", "B0:89:00": "Huawei",
        "B0:E2:35": "Huawei", "B4:15:13": "Huawei", "B4:30:52": "Huawei",
        "B4:69:0F": "Huawei", "B4:74:4F": "Huawei", "B4:9D:0B": "Huawei",
        "B8:BC:1B": "Huawei", "B8:C1:11": "Huawei", "BC:25:E0": "Huawei",
        "BC:3E:13": "Huawei", "BC:76:5E": "Huawei", "BC:9C:C5": "Huawei",
        "C0:25:67": "Huawei", "C0:25:E6": "Huawei", "C0:48:E6": "Huawei",
        "C0:70:09": "Huawei", "C0:97:27": "Huawei", "C0:A5:3E": "Huawei",
        "C0:D0:12": "Huawei", "C4:05:28": "Huawei", "C4:07:2F": "Huawei",
        "C4:6A:B7": "Huawei", "C4:70:0B": "Huawei", "C4:86:E9": "Huawei",
        "C4:9A:02": "Huawei", "C4:B8:B4": "Huawei", "C8:51:95": "Huawei",
        "C8:6C:1E": "Huawei", "C8:77:82": "Huawei", "C8:94:BB": "Huawei",
        "C8:A8:23": "Huawei", "CC:07:AB": "Huawei", "CC:2D:8C": "Huawei",
        "CC:53:B5": "Huawei", "CC:96:A0": "Huawei", "CC:A2:23": "Huawei",
        "CC:CC:81": "Huawei", "D0:0E:A4": "Huawei", "D0:5B:A8": "Huawei",
        "D0:7A:B5": "Huawei", "D0:8B:7E": "Huawei", "D0:93:95": "Huawei",
        "D0:DF:C7": "Huawei", "D4:3D:2E": "Huawei", "D4:40:F0": "Huawei",
        "D4:61:2E": "Huawei", "D4:6A:A8": "Huawei", "D4:6E:5C": "Huawei",
        "D4:7B:B0": "Huawei", "D4:93:98": "Huawei", "D4:94:E8": "Huawei",
        "D4:AD:2D": "Huawei", "D4:B1:10": "Huawei", "D4:F5:EF": "Huawei",
        "D8:0F:99": "Huawei", "D8:10:CB": "Huawei", "D8:24:BD": "Huawei",
        "D8:29:16": "Huawei", "D8:30:62": "Huawei", "D8:38:0D": "Huawei",
        "D8:49:0B": "Huawei", "D8:8D:5C": "Huawei", "D8:90:E8": "Huawei",
        "D8:B1:2A": "Huawei", "D8:C4:6A": "Huawei", "D8:D4:3C": "Huawei",
        "DC:02:8E": "Huawei", "DC:0B:34": "Huawei", "DC:2B:CA": "Huawei",
        "DC:3C:F4": "Huawei", "DC:44:6D": "Huawei", "DC:4E:18": "Huawei",
        "DC:57:26": "Huawei", "DC:6D:CD": "Huawei", "DC:70:14": "Huawei",
        "DC:D2:FC": "Huawei", "E0:06:30": "Huawei", "E0:19:54": "Huawei",
        "E0:24:7F": "Huawei", "E0:30:05": "Huawei", "E0:3F:49": "Huawei",
        "E0:4F:43": "Huawei", "E0:60:66": "Huawei", "E0:75:0A": "Huawei",
        "E0:97:96": "Huawei", "E0:A3:AC": "Huawei", "E0:C3:77": "Huawei",
        "E0:DB:10": "Huawei", "E4:1C:4B": "Huawei", "E4:22:A5": "Huawei",
        "E4:35:C8": "Huawei", "E4:3E:D7": "Huawei", "E4:47:90": "Huawei",
        "E4:48:C7": "Huawei", "E4:5E:1B": "Huawei", "E4:68:A3": "Huawei",
        "E4:77:6B": "Huawei", "E4:7C:F9": "Huawei", "E4:8D:8C": "Huawei",
        "E4:92:FB": "Huawei", "E4:BE:ED": "Huawei", "E4:C2:D1": "Huawei",
        "E8:08:8B": "Huawei", "E8:11:CA": "Huawei", "E8:26:89": "Huawei",
        "E8:48:B8": "Huawei", "E8:5A:A7": "Huawei", "E8:68:19": "Huawei",
        "E8:6C:DA": "Huawei", "E8:8D:28": "Huawei", "E8:93:09": "Huawei",
        "E8:9F:80": "Huawei", "E8:B4:C8": "Huawei", "E8:CD:2D": "Huawei",
        "E8:E5:D6": "Huawei", "EC:10:7B": "Huawei", "EC:1F:72": "Huawei",
        "EC:38:8F": "Huawei", "EC:5C:68": "Huawei", "EC:9B:F3": "Huawei",
        "EC:CB:30": "Huawei", "EC:F4:BB": "Huawei", "F0:0E:1D": "Huawei",
        "F0:27:2D": "Huawei", "F0:43:47": "Huawei", "F0:4B:6A": "Huawei",
        "F0:5A:09": "Huawei", "F0:79:59": "Huawei", "F0:7B:CB": "Huawei",
        "F0:D4:F6": "Huawei", "F0:E7:7E": "Huawei", "F4:06:69": "Huawei",
        "F4:0E:83": "Huawei", "F4:38:14": "Huawei", "F4:41:56": "Huawei",
        "F4:4B:2A": "Huawei", "F4:55:9C": "Huawei", "F4:63:1F": "Huawei",
        "F4:9F:F3": "Huawei", "F4:C7:14": "Huawei", "F4:DC:F9": "Huawei",
        "F4:E4:AD": "Huawei", "F4:FC:32": "Huawei", "F8:01:13": "Huawei",
        "F8:0D:60": "Huawei", "F8:1D:78": "Huawei", "F8:4A:BF": "Huawei",
        "F8:A4:5F": "Huawei", "F8:E7:1E": "Huawei", "FC:11:86": "Huawei",
        "FC:3F:7C": "Huawei", "FC:48:EF": "Huawei", "FC:A2:2A": "Huawei",
        "FC:DB:B3": "Huawei", "FC:E8:06": "Huawei",

        # Xiaomi
        "0C:1D:AF": "Xiaomi", "18:59:36": "Xiaomi", "28:E3:1F": "Xiaomi",
        "34:80:B3": "Xiaomi", "50:64:2B": "Xiaomi", "58:44:98": "Xiaomi",
        "64:B4:73": "Xiaomi", "64:CC:2E": "Xiaomi", "74:23:44": "Xiaomi",
        "74:51:BA": "Xiaomi", "78:11:DC": "Xiaomi", "78:2E:EF": "Xiaomi",
        "7C:78:B2": "Xiaomi", "8C:BE:BE": "Xiaomi", "9C:99:A0": "Xiaomi",
        "A4:08:EA": "Xiaomi", "AC:C1:EE": "Xiaomi", "AC:F7:F3": "Xiaomi",
        "B0:E2:35": "Xiaomi", "B4:60:77": "Xiaomi", "B8:BC:5B": "Xiaomi",
        "C4:6A:B7": "Xiaomi", "D4:97:0B": "Xiaomi", "F0:B4:29": "Xiaomi",
        "F4:F5:24": "Xiaomi", "F4:F5:DB": "Xiaomi", "F8:A4:5F": "Xiaomi",
        "FC:64:BA": "Xiaomi",

        # Google
        "00:1A:11": "Google", "3C:5A:B4": "Google", "54:60:09": "Google",
        "64:BC:0C": "Google", "8C:F5:A3": "Google", "94:EB:2C": "Google",
        "A4:77:33": "Google", "F4:F5:D8": "Google", "FC:53:9E": "Google",

        # OnePlus
        "64:32:35": "OnePlus", "94:65:2D": "OnePlus", "B4:69:0F": "OnePlus",
        "C0:EE:40": "OnePlus", "D4:61:9D": "OnePlus",

        # Printer manufacturers
        "00:01:E6": "Printer", "00:04:EC": "Printer", "00:06:6A": "Printer",
        "00:09:47": "Printer", "00:0B:78": "Printer", "00:0C:6F": "Printer",
        "00:0D:3A": "Printer", "00:0E:7F": "Printer", "00:10:83": "Printer",
        "00:11:0A": "Printer", "00:11:85": "Printer", "00:12:79": "Printer",
        "00:13:21": "Printer", "00:14:38": "Printer", "00:15:99": "Printer",
        "00:16:ED": "Printer", "00:17:A4": "Printer", "00:18:FE": "Printer",
        "00:19:BB": "Printer", "00:1A:2B": "Printer", "00:1B:78": "Printer",
        "00:1C:DF": "Printer", "00:1D:72": "Printer", "00:1E:0B": "Printer",
        "00:1E:8F": "Printer", "00:1F:29": "Printer", "00:20:6B": "Printer",
        "00:21:B7": "Printer", "00:22:64": "Printer", "00:23:04": "Printer",
        "00:23:7D": "Printer", "00:24:56": "Printer", "00:25:53": "Printer",
        "00:26:73": "Printer", "00:27:13": "Printer", "00:28:3C": "Printer",
        "00:29:4A": "Printer", "00:2A:5F": "Printer", "00:2B:67": "Printer",
        "00:80:77": "Printer", "00:80:91": "Printer", "00:A0:BF": "Printer",
        "00:C0:B7": "Printer", "00:DB:DF": "Printer", "10:1C:0C": "Printer",
        "10:6F:3F": "Printer", "14:58:08": "Printer", "18:60:24": "Printer",
        "1C:7D:22": "Printer", "20:DF:B9": "Printer", "24:BE:05": "Printer",
        "28:18:78": "Printer", "2C:44:01": "Printer", "30:CD:A7": "Printer",
        "34:13:43": "Printer", "38:63:BB": "Printer", "3C:2A:F4": "Printer",
        "40:B6:B1": "Printer", "44:31:92": "Printer", "48:00:33": "Printer",
        "4C:32:75": "Printer", "50:1E:2D": "Printer", "54:42:49": "Printer",
        "58:20:59": "Printer", "5C:CF:7F": "Printer", "60:12:83": "Printer",
        "64:51:06": "Printer", "68:54:FD": "Printer", "6C:3B:6B": "Printer",
        "70:5A:0F": "Printer", "74:4D:28": "Printer", "78:72:5D": "Printer",
        "7C:2E:0D": "Printer", "80:CE:62": "Printer", "84:34:97": "Printer",
        "88:51:FB": "Printer", "8C:DC:D4": "Printer", "90:01:3E": "Printer",
        "94:57:A5": "Printer", "98:5A:EB": "Printer", "9C:32:CE": "Printer",
        "A0:51:0B": "Printer", "A4:5D:36": "Printer", "A8:20:66": "Printer",
        "AC:18:26": "Printer", "B0:5A:DA": "Printer", "B4:39:34": "Printer",
        "B8:AE:ED": "Printer", "BC:30:5B": "Printer", "C0:B8:83": "Printer",
        "C4:34:6B": "Printer", "C8:CB:B8": "Printer", "CC:3B:58": "Printer",
        "D0:73:D5": "Printer", "D4:85:64": "Printer", "D8:D0:90": "Printer",
        "DC:4A:3E": "Printer", "E0:55:3D": "Printer", "E4:95:6E": "Printer",
        "E8:65:49": "Printer", "EC:B1:D7": "Printer", "F0:27:2D": "Printer",
        "F4:3E:61": "Printer", "F8:54:B8": "Printer", "FC:E2:6C": "Printer",

        # Camera / IP Camera
        "00:12:16": "Camera", "00:1A:07": "Camera", "00:22:4D": "Camera",
        "00:40:8C": "Camera", "00:C0:09": "Camera", "28:57:67": "Camera",
        "2C:A1:57": "Camera", "30:91:8F": "Camera", "34:02:86": "Camera",
        "38:E8:DF": "Camera", "44:19:B6": "Camera", "48:02:2A": "Camera",
        "4C:BD:8F": "Camera", "54:C4:15": "Camera", "58:E8:76": "Camera",
        "60:3D:26": "Camera", "64:5D:92": "Camera", "6C:5A:B0": "Camera",
        "78:8C:B5": "Camera", "7C:83:34": "Camera", "88:9F:6F": "Camera",
        "94:E1:AC": "Camera", "98:02:D8": "Camera", "9C:32:CE": "Camera",
        "A4:14:37": "Camera", "B0:C5:54": "Camera", "B4:A5:AC": "Camera",
        "C0:56:E3": "Camera", "C4:F3:12": "Camera", "D8:EB:97": "Camera",
        "E0:50:8B": "Camera", "E4:F0:04": "Camera", "EC:71:DB": "Camera",
        "F0:78:16": "Camera",

        # Networking equipment
        "00:01:63": "Network Device", "00:01:C9": "Network Device",
        "00:02:6F": "Network Device", "00:03:6B": "Network Device",
        "00:04:27": "Network Device", "00:05:9A": "Network Device",
        "00:06:28": "Network Device", "00:07:7D": "Network Device",
        "00:08:A3": "Network Device", "00:09:5B": "Network Device",
        "00:0A:41": "Network Device", "00:0B:BE": "Network Device",
        "00:0C:42": "Network Device", "00:0D:BC": "Network Device",
        "00:0E:38": "Network Device", "00:0F:34": "Network Device",
        "00:10:DB": "Network Device", "00:12:CF": "Network Device",
        "00:13:46": "Network Device", "00:14:22": "Network Device",
        "00:15:2F": "Network Device", "00:16:01": "Network Device",
        "00:17:0E": "Network Device", "00:18:39": "Network Device",
        "00:19:2F": "Network Device", "00:1A:2F": "Network Device",
        "00:1B:21": "Network Device", "00:1C:0E": "Network Device",
        "00:1D:71": "Network Device", "00:1E:52": "Network Device",
        "00:1F:6C": "Network Device", "00:20:4A": "Network Device",
        "00:21:29": "Network Device", "00:22:0B": "Network Device",
        "00:23:02": "Network Device", "00:24:14": "Network Device",
        "00:25:84": "Network Device", "00:26:0B": "Network Device",
        "00:27:07": "Network Device", "00:28:15": "Network Device",
        "00:50:56": "Network Device", "00:E0:4C": "Network Device",
        "08:EA:44": "Network Device", "14:59:C0": "Network Device",
        "18:E8:29": "Network Device", "20:E5:2A": "Network Device",
        "24:05:0F": "Network Device", "24:5A:4C": "Network Device",
        "28:80:23": "Network Device", "2C:B0:5D": "Network Device",
        "30:46:9A": "Network Device", "34:97:F6": "Network Device",
        "38:2C:4A": "Network Device", "3C:8A:B0": "Network Device",
        "40:4A:03": "Network Device", "44:94:FC": "Network Device",
        "48:EE:0C": "Network Device", "4C:5E:0C": "Network Device",
        "50:6A:03": "Network Device", "54:04:A6": "Network Device",
        "58:EF:68": "Network Device", "5C:50:15": "Network Device",
        "60:38:E0": "Network Device", "64:F6:9D": "Network Device",
        "68:72:51": "Network Device", "6C:B0:CE": "Network Device",
        "70:4D:7B": "Network Device", "74:8E:08": "Network Device",
        "78:8A:20": "Network Device", "7C:8B:CA": "Network Device",
        "80:2A:A8": "Network Device", "84:74:60": "Network Device",
        "88:3D:24": "Network Device", "8C:3B:AD": "Network Device",
        "90:5C:44": "Network Device", "94:10:3E": "Network Device",
        "98:DE:D0": "Network Device", "9C:3D:CF": "Network Device",
        "A0:04:3E": "Network Device", "A4:2B:8C": "Network Device",
        "A8:58:40": "Network Device", "AC:4E:91": "Network Device",
        "B0:7E:11": "Network Device", "B4:2E:99": "Network Device",
        "B8:62:1F": "Network Device", "BC:FE:D9": "Network Device",
        "C0:25:E9": "Network Device", "C4:01:7C": "Network Device",
        "C8:60:00": "Network Device", "CC:50:E3": "Network Device",
        "D0:50:99": "Network Device", "D4:04:FF": "Network Device",
        "D8:07:B6": "Network Device", "D8:50:E6": "Network Device",
        "DC:9F:DB": "Network Device", "E0:2F:6D": "Network Device",
        "E4:F0:42": "Network Device", "E8:65:49": "Network Device",
        "EC:08:6B": "Network Device", "F0:7F:06": "Network Device",
        "F4:CF:E2": "Network Device", "F8:4A:BF": "Network Device",
        "FC:FB:FB": "Network Device",
    }
    return oui_map.get(prefix, "Unknown")


def guess_os_from_ttl(ttl):
    """Guess OS from TTL value."""
    if ttl <= 64:
        return "Linux"
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


# ── Port Scanning ────────────────────────────────────────────────────────────

# Common ports to scan — covers web, SSH, remote access, IoT, printers, etc.
COMMON_PORTS = [
    20, 21,    # FTP
    22,        # SSH
    23,        # Telnet
    25,        # SMTP
    53,        # DNS
    80,        # HTTP
    110,       # POP3
    135,       # MS-RPC
    139,       # NetBIOS
    143,       # IMAP
    443,       # HTTPS
    445,       # SMB
    993,       # IMAPS
    995,       # POP3S
    1723,      # PPTP
    3306,      # MySQL
    3389,      # RDP
    5432,      # PostgreSQL
    5900,      # VNC
    8080,      # HTTP Proxy
    8443,      # HTTPS Alt
    9100,      # Printer (RAW)
    554,       # RTSP (cameras)
    8081,      # Camera/NVR alt
    1883,      # MQTT (IoT)
    5000,      # UPnP
    7000,      # Chromecast
]

# Port -> friendly service name
PORT_SERVICE = {
    20: "FTP-Data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 135: "RPC", 139: "NetBIOS",
    143: "IMAP", 443: "HTTPS", 445: "SMB", 993: "IMAPS", 995: "POP3S",
    1723: "PPTP", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    5900: "VNC", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 9100: "Printer",
    554: "RTSP", 8081: "NVR", 1883: "MQTT", 5000: "UPnP", 7000: "Chromecast",
}


def _check_port(ip, port, timeout=0.5):
    """Try TCP connect to a single port. Returns port number if open, else None."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        if result == 0:
            return port
    except Exception:
        pass
    return None


def scan_ports(ip, ports=None, timeout=0.5):
    """Scan common ports on a host using TCP connect.
    Returns list of open port numbers, e.g. [22, 80, 443].
    """
    if ports is None:
        ports = COMMON_PORTS
    open_ports = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(_check_port, ip, p, timeout): p for p in ports}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    open_ports.append(result)
            except Exception:
                pass
    return sorted(open_ports)


def format_ports(port_list):
    """Convert list of port ints to a compact string: '22,80,443'."""
    return ",".join(str(p) for p in port_list) if port_list else ""


def parse_ports(port_str):
    """Convert '22,80,443' back to a list of ints."""
    if not port_str:
        return []
    return [int(p) for p in port_str.split(",") if p.strip().isdigit()]


def _parse_ttl(output):
    """Extract TTL from ping output."""
    match = re.search(r"TTL=(\d+)", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 64
