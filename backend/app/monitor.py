"""Interface bandwidth sampling (psutil) and optional protocol sniffing (Scapy)."""

import platform
import subprocess
import threading
import time

import psutil

from .config import get_settings

settings = get_settings()

# `netsh` spawns a process, so cache its result briefly: the interfaces
# endpoint is polled and the negotiated rate rarely changes second-to-second.
_WIFI_RATES_TTL = 3.0
_wifi_rates_cache: dict[str, dict[str, float]] = {}
_wifi_rates_ts = float("-inf")


def wifi_link_rates() -> dict[str, dict[str, float]]:
    """Live WiFi link rates (Mbps) keyed by adapter name.

    psutil's `net_if_stats().speed` is a driver-reported nominal figure — often
    `0` for WiFi adapters and never the rate actually negotiated right now.
    `netsh wlan show interfaces` (Windows) reports the real RX/TX link rates,
    so we parse those instead. Returns `{}` off-Windows or when no wireless
    adapter is present.
    """
    global _wifi_rates_cache, _wifi_rates_ts
    now = time.monotonic()
    if now - _wifi_rates_ts < _WIFI_RATES_TTL:
        return _wifi_rates_cache
    if platform.system().lower() != "windows":
        return {}
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return _wifi_rates_cache

    rates: dict[str, dict[str, float]] = {}
    name = ""
    current: dict[str, float] = {}
    for raw in proc.stdout.splitlines():
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "name":
            name = value
            current = {}
        elif name and key in ("receive rate (mbps)", "transmit rate (mbps)"):
            try:
                current["receive_rate" if key.startswith("receive") else "transmit_rate"] = float(value.split()[0])
            except (ValueError, IndexError):
                continue
            rates[name] = current
    _wifi_rates_cache = rates
    _wifi_rates_ts = now
    return rates


class BandwidthSampler:
    """Deltas of per-interface byte counters -> Mbps rates."""

    def __init__(self) -> None:
        self._prev: dict[str, psutil._common.snetio] | None = None
        self._prev_ts: float | None = None
        self._last: list[dict] = []

    def snapshot(self) -> list[dict]:
        counters = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        now = time.monotonic()

        if self._prev is None or self._prev_ts is None:
            self._prev = counters
            self._prev_ts = now
            return []

        dt = max(now - self._prev_ts, 0.001)
        out: list[dict] = []
        for name, cur in counters.items():
            prev = self._prev.get(name)
            if prev is None:
                continue
            speed = getattr(stats.get(name), "speed", 0) or 0  # Mbps
            mbps_in = max(0.0, (cur.bytes_recv - prev.bytes_recv)) * 8 / dt / 1e6
            mbps_out = max(0.0, (cur.bytes_sent - prev.bytes_sent)) * 8 / dt / 1e6
            utilization = round((mbps_in + mbps_out) / max(speed, 0.01) * 100, 1) if speed else 0.0
            out.append(
                {
                    "interface": name,
                    "mbps_in": mbps_in,
                    "mbps_out": mbps_out,
                    "speed_mbps": speed,
                    "utilization": min(utilization, 99.0),
                    "bytes_sec_in": int(max(0, cur.bytes_recv - prev.bytes_recv)),
                    "bytes_sec_out": int(max(0, cur.bytes_sent - prev.bytes_sent)),
                    "total_in": cur.bytes_recv,
                    "total_out": cur.bytes_sent,
                    "packets_in": cur.packets_recv,
                    "packets_out": cur.packets_sent,
                    "errors_in": cur.errin,
                    "errors_out": cur.errout,
                    "drops_in": cur.dropin,
                    "drops_out": cur.dropout,
                }
            )
        self._prev = counters
        self._prev_ts = now
        self._last = out
        return out

    def last_snapshot(self) -> list[dict]:
        return self._last

    def interface_details(self) -> list[dict]:
        counters = psutil.net_io_counters(pernic=True)
        stats = psutil.net_if_stats()
        rates = wifi_link_rates()
        out = []
        for name, counter in counters.items():
            st = stats.get(name)
            speed = getattr(st, "speed", 0) or 0
            rx = rates.get(name, {}).get("receive_rate")
            tx = rates.get(name, {}).get("transmit_rate")
            if rx and tx:
                # Real negotiated WiFi link rate (RX/TX), far more honest than
                # the driver's nominal `speed`, which is 0 for many adapters.
                speed_label = f"{rx:.0f}/{tx:.0f} Mbps"
            else:
                speed_label = f"{speed // 1000} Gbps" if speed >= 1000 else f"{speed} Mbps"
            out.append(
                {
                    "name": name,
                    "speed": speed_label,
                    "wifi_rx_mbps": rx,
                    "wifi_tx_mbps": tx,
                    "total_in": counter.bytes_recv,
                    "total_out": counter.bytes_sent,
                    "errors": counter.errin + counter.errout,
                    "status": "UP" if st and st.isup else "DOWN",
                }
            )
        return out


class ProtocolMonitor:
    """Background Scapy sniff thread aggregating per-protocol packet counts.

    Optional (SNIFFING_ENABLED=true). Needs admin/root rights; degrades to zeros.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.counts: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Diffie-Hellman over finite fields .*")
                from scapy.all import sniff  # noqa: F401
        except Exception:
            self.enabled = False
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Diffie-Hellman over finite fields .*")
                from scapy.all import sniff

            sniff(prn=self._count, store=False, stop_filter=lambda _p: self._stop.is_set())
        except Exception:
            self.enabled = False

    def _count(self, packet) -> None:
        proto = self._classify(packet)
        self.counts[proto] = self.counts.get(proto, 0) + 1

    @staticmethod
    def _classify(packet) -> str:
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Diffie-Hellman over finite fields .*")
                from scapy.all import ARP, ICMP, IP, TCP, UDP
        except Exception:
            return "OTHER"
        if packet.haslayer(ARP):
            return "ARP"
        if packet.haslayer(IP):
            ip = packet[IP]
            if ip.proto == 6 and packet.haslayer(TCP):
                dport = packet[TCP].dport
                if dport in (80, 8080):
                    return "HTTP"
                if dport == 443:
                    return "HTTPS"
                return "TCP"
            if ip.proto == 17 and packet.haslayer(UDP):
                dport = packet[UDP].dport
                if dport == 53:
                    return "DNS"
                return "UDP"
            if ip.proto == 1 and packet.haslayer(ICMP):
                return "ICMP"
            return "OTHER"
        return "OTHER"

    def stats(self) -> dict:
        return {p: self.counts.get(p, 0) for p in ("TCP", "UDP", "HTTP", "HTTPS", "DNS", "ICMP", "ARP")}
