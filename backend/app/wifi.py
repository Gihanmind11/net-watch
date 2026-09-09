"""Wi-Fi / hotspot status via OS commands (no admin rights needed).

Windows : `netsh wlan show interfaces` + `netsh wlan show networks`
Linux   : `nmcli -t device wifi list` (fallback `iw dev <iface> link`)
macOS   : /usr/sbin/airport -I + -s (fallback `system_profiler SPAirPortDataType`)

When no WLAN adapter — or no tool — is available, every field degrades
gracefully so the dashboard stays functional (Ethernet uplink, CI
containers, headless servers).
"""

import json
import os
import platform
import re
import subprocess
import threading
import time

_SYSTEM = platform.system().lower()  # "windows" | "linux" | "darwin"

_LOCK = threading.Lock()
_CACHE: dict = {"payload": None, "ts": 0.0}
_TTL = 5.0  # seconds; scanner commands take ~0.5-2s and the UI polls every 5s

_BSSID_RE = r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}"


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout or ""
    except Exception:
        return ""


def _dbm_to_pct(dbm: int) -> int:
    """Rough RSSI → quality mapping: -50 dBm+ ≈ 100 %, -85 dBm ≈ 30 %."""
    return int(max(0, min(100, 2 * (dbm + 100))))


def _band(chan: int) -> str:
    return "2.4 GHz" if 0 < chan <= 14 else "5 GHz" if chan else "—"


# ---------------------------------------------------------------- Windows

def _parse_interfaces(out: str) -> dict | None:
    """Parse `netsh wlan show interfaces` (English output)."""
    def field(name: str) -> str:
        m = re.search(rf"^\s*{re.escape(name)}\s*:\s*(.+)$", out, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    ssid = field("SSID")
    if not ssid:
        return None

    bssid = field("BSSID")
    m = re.search(rf"({_BSSID_RE})", bssid)
    bssid = m.group(1).replace("-", ":").upper() if m else bssid

    sig = field("Signal")
    sig_m = re.search(r"\d+", sig)

    return {
        "ssid": ssid,
        "bssid": bssid,
        "signal": int(sig_m.group()) if sig_m else 0,
        "channel": field("Channel") or "—",
        "state": field("State") or "connected",
        "radio_type": field("Radio type") or "—",
        "authentication": field("Authentication") or "Open",
        "rx_rate": field("Receive rate (Mbps)") or "—",
        "tx_rate": field("Transmit rate (Mbps)") or "—",
    }


def _visible_networks() -> int:
    """Count SSIDs listed by `netsh wlan show networks`."""
    out = _run(["netsh", "wlan", "show", "networks"])
    return len(re.findall(r"^\s*SSID \d+", out, re.MULTILINE))


def _windows_note(out: str) -> str:
    """Human-readable hint when netsh withholds WLAN data. Windows 11 24H2
    gates WLAN queries behind the Location privacy setting — with it off,
    netsh answers with the location/elevation error instead of interface info."""
    low = out.lower()
    if _LOC_BLOCK_RE.search(out):
        return ("Windows blocked WLAN info: turn ON Location services "
                "(Settings > Privacy & security > Location) and restart the backend.")
    if "no wireless interface" in low:
        return "No wireless adapter found on this machine."
    return ""


_LOC_BLOCK_RE = re.compile(r"location|wlanqueryinterface|elevation", re.IGNORECASE)

_FALLBACK_NOTE = ("Windows is blocking Wi-Fi radio queries (the Location master switch is OFF "
                  "for this PC). Network name, security and link speed are read from system "
                  "logs instead; signal %, BSSID, channel and nearby-AP count need the Location "
                  "master switch ON (Settings > Privacy & security > Location) or an "
                  "administrator terminal for the backend.")

_PS_SNAPSHOT = (
    "$a = Get-NetAdapter | Where-Object Status -eq 'Up' | "
    "Select-Object Name, InterfaceDescription, LinkSpeed; "
    "$p = Get-NetConnectionProfile | "
    "Select-Object Name, InterfaceAlias, IPv4Connectivity; "
    "$e = Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational'; "
    "Id=8001,8003} -MaxEvents 8 -ErrorAction SilentlyContinue | "
    "Sort-Object TimeCreated -Descending | Select-Object -First 1 Id, Message; "
    "@{ adapters = @($a); profiles = @($p); wlanev = $e } | ConvertTo-Json -Compress -Depth 5"
)


def _ps_snapshot() -> tuple[list, list, dict | None]:
    """One PowerShell round-trip: Up adapters + NLM connection profiles + the
    newest WLAN-AutoConfig connect/disconnect event. None of these touch the
    WLAN API, so all work with Location OFF (the 24H2 privacy gate only blocks
    WLAN queries)."""
    out = _run(["powershell", "-NoProfile", "-Command", _PS_SNAPSHOT], timeout=25)
    try:
        data = json.loads(out)
    except Exception:
        return [], [], None
    if not isinstance(data, dict):
        return [], [], None
    adapters = data.get("adapters") or []
    profiles = data.get("profiles") or []
    if isinstance(adapters, dict):
        adapters = [adapters]
    if isinstance(profiles, dict):
        profiles = [profiles]
    ev = data.get("wlanev")
    return ([a for a in adapters if isinstance(a, dict)],
            [p for p in profiles if isinstance(p, dict)],
            ev if isinstance(ev, dict) else None)


def _is_wifi_adapter(name: str, desc: str) -> bool:
    text = f"{name} {desc}".lower()
    return any(k in text for k in ("wi-fi", "wireless", "wlan", "802.11"))


def _link_mbps(link: str) -> str:
    """'866.7 Mbps' / '1 Gbps' → Mbps number string."""
    m = re.search(r"([\d.]+)\s*(Gbps|Mbps|Kbps)", link, re.IGNORECASE)
    if not m:
        return "—"
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "gbps":
        val *= 1000
    elif unit == "kbps":
        val /= 1000
    return f"{val:g}"


def _event_conn(ev: dict | None) -> dict | None:
    """Extract connection metadata from the newest WLAN-AutoConfig event.
    Event 8001 ('connected to a wireless network') carries SSID / PHY type /
    authentication / encryption as plain text; 8003 means the newest state is
    'disconnected'. The event log is not subject to the Location gate, but it
    only updates at (re)connect time — no live signal or BSSID."""
    if not ev or ev.get("Id") != 8001:
        return None
    msg = str(ev.get("Message") or "")

    def fld(name: str) -> str:
        m = re.search(rf"^\s*{re.escape(name)}\s*:\s*(.+)$", msg, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    ssid = fld("SSID")
    if not ssid:
        return None
    auth, enc = fld("Authentication"), fld("Encryption")
    return {
        "ssid": ssid,
        "radio_type": fld("PHY Type") or "—",
        "authentication": f"{auth} ({enc})" if auth and enc else (auth or "—"),
    }


def _windows_fallback() -> dict | None:
    """Location-independent connection snapshot for Windows 11 24H2+.
    NLM + adapters give the connection type, network name and link speed; the
    WLAN-AutoConfig event log adds the SSID, radio type and security suite of
    the current connection. Signal, BSSID, channel and nearby APs genuinely
    require the Location master switch and degrade to '—'."""
    adapters, profiles, ev = _ps_snapshot()
    if not adapters and not ev:
        return None
    by_alias = {p.get("InterfaceAlias"): p for p in profiles}

    def rank(a: dict) -> tuple[int, int]:
        p = by_alias.get(a.get("Name")) or {}
        online = 1 if p.get("IPv4Connectivity") == "Internet" else 0
        is_wifi = 1 if _is_wifi_adapter(str(a.get("Name", "")),
                                        str(a.get("InterfaceDescription", ""))) else 0
        return (online, is_wifi)

    best = max(adapters, key=rank) if adapters else {}
    prof = by_alias.get(best.get("Name")) or {}
    wifi_ad = bool(ev) or _is_wifi_adapter(str(best.get("Name", "")),
                                           str(best.get("InterfaceDescription", "")))
    speed = _link_mbps(str(best.get("LinkSpeed") or ""))

    conn = {
        "ssid": "",
        "bssid": "",
        "signal": 0,
        "channel": "—",
        "state": "connected",
        "radio_type": "—",
        "authentication": "—",
        "rx_rate": speed,
        "tx_rate": speed,
        "connection_type": "wifi" if wifi_ad else "ethernet",
    }
    if wifi_ad:
        conn["ssid"] = str(prof.get("Name") or "").strip()
        enrich = _event_conn(ev)
        if enrich:
            # event log is the authoritative connect-time record
            conn.update(enrich)
    return conn


# ---------------------------------------------------------------- Linux

_NMCLI_LINE = re.compile(
    rf"^(yes|no):(.+?):({_BSSID_RE}):(\d+):(\d+):(.+?):(.*)$"
)


def _parse_nmcli(out: str) -> tuple[dict | None, int]:
    """Parse `nmcli -t device wifi list`; the ACTIVE=yes line is the current
    connection. Returns (connection, visible-ssid-count)."""
    conn: dict | None = None
    visible = 0
    for line in out.splitlines():
        m = _NMCLI_LINE.match(line.strip())
        if not m:
            continue
        visible += 1
        if m.group(1) == "yes" and conn is None:
            chan = int(m.group(5))
            rate = m.group(6).split()[0] if m.group(6) else "—"
            conn = {
                "ssid": m.group(2).replace("\\:", ":"),
                "bssid": m.group(3).upper(),
                "signal": int(m.group(4)),
                "channel": str(chan) if chan else "—",
                "radio_type": _band(chan),
                "authentication": m.group(7) or "Open",
                "rx_rate": rate,
                "tx_rate": rate,
            }
    return conn, visible


def _iw_fallback() -> dict | None:
    """`iw dev <iface> link` fallback when NetworkManager is absent."""
    dev = re.search(r"Interface\s+(\S+)", _run(["iw", "dev"], timeout=5))
    if not dev:
        return None
    link = _run(["iw", "dev", dev.group(1), "link"], timeout=5)
    bssid = re.search(rf"Connected to ({_BSSID_RE})", link, re.IGNORECASE)
    ssid = re.search(r"^\s*SSID: (.+)$", link, re.MULTILINE)
    if not (bssid and ssid):
        return None

    dbm = re.search(r"signal: (-?\d+)", link)
    freq = re.search(r"freq: (\d+)", link)
    tx = re.search(r"tx bitrate: ([\d.]+)", link)
    rx = re.search(r"rx bitrate: ([\d.]+)", link)

    chan = 0
    if freq:
        f = int(freq.group(1))
        chan = round((f - 2407) / 5) if 2400 < f < 2500 else round((f - 5000) / 5) if f > 4900 else 0

    return {
        "ssid": ssid.group(1).strip(),
        "bssid": bssid.group(1).upper(),
        "signal": _dbm_to_pct(int(dbm.group(1))) if dbm else 0,
        "channel": str(chan) if chan else "—",
        "radio_type": _band(chan),
        "authentication": "—",  # iw link does not expose the auth suite
        "rx_rate": rx.group(1) if rx else "—",
        "tx_rate": tx.group(1) if tx else "—",
    }


def _linux_payload() -> tuple[dict | None, int]:
    conn, visible = _parse_nmcli(_run(
        ["nmcli", "-t", "--escape", "yes", "-f", "ACTIVE,SSID,BSSID,SIGNAL,CHAN,RATE,SECURITY",
         "device", "wifi", "list"], timeout=12))
    if conn is None:
        conn = _iw_fallback()
    return conn, visible


# ---------------------------------------------------------------- macOS

_AIRPORT = "/usr/sbin/airport"  # removed on some newer macOS builds


def _parse_airport(out: str) -> dict | None:
    """Parse `airport -I`. Note: on macOS 14+ the SSID may show as
    `<redacted>` unless the calling app has Location permission."""
    def field(name: str) -> str:
        m = re.search(rf"^\s*{re.escape(name)}:\s*(.+)$", out, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    if field("state") != "running":
        return None
    bssid = field("BSSID")
    if not re.fullmatch(_BSSID_RE, bssid):
        return None

    rssi = field("agrCtlRSSI")
    chan_m = re.match(r"(\d+)", field("channel"))
    rate = field("lastTxRate")
    ssid = field("SSID")

    return {
        "ssid": ssid if ssid and ssid != "<redacted>" else "—",
        "bssid": bssid.upper(),
        "signal": _dbm_to_pct(int(rssi)) if re.fullmatch(r"-?\d+", rssi) else 0,
        "channel": chan_m.group(1) if chan_m else "—",
        "radio_type": _band(int(chan_m.group(1))) if chan_m else "—",
        "authentication": field("security").upper() or "Open",
        "rx_rate": rate or "—",
        "tx_rate": rate or "—",
    }


def _system_profiler_conn() -> dict | None:
    """Fallback without the airport binary (no signal strength available)."""
    out = _run(["system_profiler", "SPAirPortDataType", "-json"], timeout=25)
    if not out:
        return None
    try:
        data = json.loads(out)["SPAirPortDataType"][0]
        current = data.get("spairport_current_network_information") or {}
    except Exception:
        return None
    for ssid, net in current.items():
        chan_m = re.match(r"(\d+)", str(net.get("spairport_current_network_channel", "")))
        return {
            "ssid": ssid,
            "bssid": str(net.get("spairport_current_network_BSSID", "")).upper(),
            "signal": 0,
            "channel": chan_m.group(1) if chan_m else "—",
            "radio_type": str(net.get("spairport_current_network_PHY_Mode", "—")),
            "authentication": "—",
            "rx_rate": "—",
            "tx_rate": "—",
        }
    return None


def _macos_payload() -> tuple[dict | None, int]:
    conn = None
    visible = 0
    if os.path.exists(_AIRPORT):
        conn = _parse_airport(_run([_AIRPORT, "-I"], timeout=8))
        scan = _run([_AIRPORT, "-s"], timeout=15)
        visible = len(re.findall(_BSSID_RE, scan))
    if conn is None:
        conn = _system_profiler_conn()
    return conn, visible


# ---------------------------------------------------------------- shared

def _is_hotspot(bssid: str) -> bool:
    """Phone hotspots use locally-administered (randomized) BSSID MACs —
    the second-least-significant bit of the first octet is set (e.g. a2:...).
    Infrastructure APs almost always carry a burned-in globally-unique MAC."""
    try:
        return bool(int(bssid[:2], 16) & 0x02)
    except (ValueError, IndexError):
        return False


def _hotspot_clients() -> int:
    """Other Wi-Fi clients visible in the ARP cache (excl. the hotspot host
    itself), i.e. devices sharing the same AP as this machine."""
    try:
        from .scanner import arp_cache_hosts, current_gateway, get_network_cidr

        gateway = current_gateway()
        hosts = [h["ip"] for h in arp_cache_hosts(get_network_cidr()) if h["ip"] != gateway]
        return len(hosts)
    except Exception:
        return 0


def wifi_payload() -> dict:
    """Snapshot of the current Wi-Fi connection, hotspot and visible APs."""
    with _LOCK:
        now = time.monotonic()
        if _CACHE["payload"] is not None and now - _CACHE["ts"] < _TTL:
            return _CACHE["payload"]

        info: dict = {
            "connected": False,
            "state": "disconnected",
            "ssid": "",
            "bssid": "",
            "signal": 0,
            "channel": "—",
            "radio_type": "—",
            "authentication": "—",
            "rx_rate": "—",
            "tx_rate": "—",
            "visible_networks": 0,
            "hotspot_active": False,
            "hotspot_clients": 0,
            "note": "",
            "connection_type": "—",
        }

        parsed = None
        visible = 0
        note = ""
        if _SYSTEM == "windows":
            raw = _run(["netsh", "wlan", "show", "interfaces"])
            note = _windows_note(raw)
            parsed = _parse_interfaces(raw)
            if parsed:
                visible = _visible_networks()
            else:
                # netsh withheld data (Location gate, no adapter, …) —
                # fall back to the Location-independent connection snapshot
                fb = _windows_fallback()
                if fb:
                    parsed = fb
                    if not note or note.startswith("Windows blocked"):
                        note = _FALLBACK_NOTE
                elif not note:
                    note = "No network connection detected on this machine."
        elif _SYSTEM == "darwin":
            parsed, visible = _macos_payload()
        else:
            parsed, visible = _linux_payload()

        if parsed:
            info["connected"] = True
            info.update(parsed)
            info["state"] = parsed.get("state", "connected")
            info["visible_networks"] = visible
            info["hotspot_active"] = _is_hotspot(parsed["bssid"])
            info["hotspot_clients"] = _hotspot_clients()
            info["connection_type"] = parsed.get("connection_type", "wifi")
        info["note"] = note

        _CACHE["payload"] = info
        _CACHE["ts"] = now
        return info
