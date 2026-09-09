"""Interface bandwidth sampling (psutil) and optional protocol sniffing (Scapy)."""

import threading
import time

import psutil

from .config import get_settings

settings = get_settings()


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
        out = []
        for name, counter in counters.items():
            st = stats.get(name)
            speed = getattr(st, "speed", 0) or 0
            speed_label = f"{speed // 1000} Gbps" if speed >= 1000 else f"{speed} Mbps"
            out.append(
                {
                    "name": name,
                    "speed": speed_label,
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
