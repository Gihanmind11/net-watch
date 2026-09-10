"""Dependency-free SNMPv2c client + gateway (whole-LAN) traffic sampler.

Whole-LAN traffic cannot be observed from a single host on a switched network:
each switch port only carries the frames addressed to its own link. The
aggregate figure must come from the one device every LAN frame passes through —
the router/gateway — and routers expose interface byte counters over SNMP.

This module implements a minimal SNMPv2c client (BER-encoded, over UDP, no
third-party dependency) and a ``LanTrafficSampler`` that polls the gateway's
ifInOctets/ifOutOctets counters and converts counter deltas into Mbps.

Routers with SNMP disabled, wrong community strings or unsupported hardware
simply never answer; the sampler degrades to ``available: False`` and the
dashboard falls back to per-host counters. A cooldown avoids hammering a router
that does not respond.
"""

import random
import socket
import time
from datetime import datetime, timezone

from .config import get_settings

# RFC 2863 / RFC 1213 interface MIB objects.
_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"           # ifDescr          (OCTET STRING)
_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"           # ifSpeed          (bps)
_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"      # ifInOctets       (Counter32)
_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"     # ifOutOctets      (Counter32)
_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # ifHighSpeed      (Mbps)

_TIMEOUT_AFTER_FAILURE_SEC = 300  # cooldown before retrying a silent router


# ---------------- BER helpers ----------------

def _enc_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _enc_int(value: int) -> bytes:
    if value == 0:
        body = b"\x00"
    else:
        body = value.to_bytes((value.bit_length() + 8) // 8, "big", signed=True)
    return b"\x02" + _enc_len(len(body)) + body


def _enc_octet(data: bytes) -> bytes:
    return b"\x04" + _enc_len(len(data)) + data


def _enc_null() -> bytes:
    return b"\x05\x00"


def _enc_oid(oid: str) -> bytes:
    """Encode a dotted-decimal OID (e.g. '1.3.6.1.2.1.2.2.1.10')."""
    parts = [int(p) for p in oid.strip(".").split(".")]
    body = bytearray([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append((p & 0x7F) | 0x80)
            p >>= 7
        body.extend(reversed(chunk))
    return b"\x06" + _enc_len(len(body)) + bytes(body)


def _dec_tlv(data: bytes, i: int) -> tuple[int, bytes, int]:
    """Decode one (tag, value, next-index) triple at offset ``i``."""
    tag = data[i]
    i += 1
    length = data[i]
    i += 1
    if length & 0x80:
        n = length & 0x7F
        length = int.from_bytes(data[i : i + n], "big")
        i += n
    return tag, data[i : i + length], i + length


def _dec_oid(body: bytes) -> str:
    if not body:
        return ""
    first = body[0]
    parts = [0, first] if first < 40 else [1, first - 40] if first < 80 else [2, first - 80]
    val = 0
    for b in body[1:]:
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(val)
            val = 0
    return ".".join(str(p) for p in parts)


def _dec_value(tag: int, body: bytes):
    if tag == 0x02:  # INTEGER (signed)
        return int.from_bytes(body, "big", signed=True)
    if tag in (0x41, 0x42, 0x43, 0x46):  # Counter32 / Gauge32 / TimeTicks / Counter64
        return int.from_bytes(body, "big")
    if tag == 0x04:  # OCTET STRING
        try:
            return body.decode("utf-8", "replace")
        except Exception:
            return body.hex()
    if tag == 0x06:  # OID
        return _dec_oid(body)
    if tag == 0x40:  # IpAddress
        return ".".join(str(b) for b in body)
    if tag == 0x05:  # NULL
        return None
    return body.hex()


def _varbind(oid: str) -> bytes:
    inner = _enc_oid(oid) + _enc_null()
    return b"\x30" + _enc_len(len(inner)) + inner


def _build_request(version: int, community: str, pdu_tag: int, request_id: int, varbinds: list[bytes]) -> bytes:
    vb_list = b"".join(varbinds)
    pdu_body = _enc_int(request_id) + _enc_int(0) + _enc_int(0) + b"\x30" + _enc_len(len(vb_list)) + vb_list
    pdu = bytes([pdu_tag]) + _enc_len(len(pdu_body)) + pdu_body
    community_bytes = community.encode()
    msg_body = _enc_int(version) + _enc_octet(community_bytes) + pdu
    return b"\x30" + _enc_len(len(msg_body)) + msg_body


def _parse_response(data: bytes) -> tuple[int, list[tuple[str, object]]] | None:
    tag, body, _ = _dec_tlv(data, 0)
    if tag != 0x30:
        return None
    i = 0
    _, _, i = _dec_tlv(body, i)  # version
    _, _, i = _dec_tlv(body, i)  # community
    pdu_tag, pdu_body, _ = _dec_tlv(body, i)
    if pdu_tag != 0xA2:  # GetResponse
        return None
    j = 0
    _, _, j = _dec_tlv(pdu_body, j)  # request-id
    _, err_body, j = _dec_tlv(pdu_body, j)  # error-status
    error_status = int.from_bytes(err_body, "big", signed=True)
    _, _, j = _dec_tlv(pdu_body, j)  # error-index
    _, vb_list_body, _ = _dec_tlv(pdu_body, j)
    out: list[tuple[str, object]] = []
    k = 0
    while k < len(vb_list_body):
        _, vb_body, k = _dec_tlv(vb_list_body, k)
        m = 0
        _, oid_body, m = _dec_tlv(vb_body, m)
        vtag, val_body, _ = _dec_tlv(vb_body, m)
        out.append((_dec_oid(oid_body), _dec_value(vtag, val_body)))
    return error_status, out


def _udp_exchange(host: str, port: int, packet: bytes, timeout: float) -> bytes | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (host, port))
            data, _ = sock.recvfrom(65535)
            return data
        finally:
            sock.close()
    except OSError:
        return None


def _request_id() -> int:
    return random.randint(1, 0x7FFFFFFF)


def _version_int(version: str) -> int:
    return 0 if str(version).lower() in ("1", "v1", "snmpv1") else 1


def snmp_get(
    host: str,
    oids: list[str],
    community: str = "public",
    version: str = "2c",
    port: int = 161,
    timeout: float = 1.0,
) -> dict[str, object] | None:
    """SNMPv2c GET for several OIDs in one request. None on any failure."""
    packet = _build_request(_version_int(version), community, 0xA0, _request_id(), [_varbind(o) for o in oids])
    data = _udp_exchange(host, port, packet, timeout)
    if data is None:
        return None
    parsed = _parse_response(data)
    if parsed is None:
        return None
    error_status, varbinds = parsed
    if error_status:
        return None
    return {oid: val for oid, val in varbinds}


def snmp_walk(
    host: str,
    base_oid: str,
    community: str = "public",
    version: str = "2c",
    port: int = 161,
    timeout: float = 1.0,
    max_rows: int = 256,
) -> list[tuple[str, object]]:
    """Walk a table with GETNEXT until the base subtree is exhausted."""
    root = base_oid.rstrip(".")
    rows: list[tuple[str, object]] = []
    current = root
    while len(rows) < max_rows:
        packet = _build_request(_version_int(version), community, 0xA1, _request_id(), [_varbind(current)])
        data = _udp_exchange(host, port, packet, timeout)
        if data is None:
            return []
        parsed = _parse_response(data)
        if parsed is None:
            return []
        error_status, varbinds = parsed
        if error_status or not varbinds:
            return rows
        oid, value = varbinds[0]
        if not (oid == root or oid.startswith(root + ".")):
            return rows
        if oid == current:  # no progress (agent returned the same OID)
            return rows
        rows.append((oid, value))
        current = oid
    return rows


# ---------------- LAN traffic sampler ----------------

class LanTrafficSampler:
    """Poll the gateway's interface counters and turn deltas into Mbps.

    Interface names/speeds are fetched once per host and cached; octet counters
    are fetched every sample. After a failure a cooldown suppresses retries so a
    non-SNMP router is not hammered.
    """

    def __init__(self) -> None:
        self._prev_in: dict[str, int] = {}
        self._prev_out: dict[str, int] = {}
        self._prev_ts = 0.0
        self._meta_host = ""
        self._names: dict[str, str] = {}
        self._speeds: dict[str, int] = {}
        self._cooldown_until = 0.0
        self._last: dict | None = None

    def last_snapshot(self) -> dict | None:
        return self._last

    def _store(self, payload: dict) -> dict:
        self._last = payload
        return payload

    def _load_meta(self, host: str) -> None:
        if host == self._meta_host and self._names:
            return
        s = get_settings()
        names: dict[str, str] = {}
        for oid, val in snmp_walk(host, _IF_DESCR, s.snmp_community, s.snmp_version, s.snmp_port, s.snmp_timeout_sec):
            if isinstance(val, str):
                names[oid.rsplit(".", 1)[-1]] = val.strip()
        speeds: dict[str, int] = {}
        for oid, val in snmp_walk(host, _IF_HIGH_SPEED, s.snmp_community, s.snmp_version, s.snmp_port, s.snmp_timeout_sec):
            if isinstance(val, int):
                speeds[oid.rsplit(".", 1)[-1]] = val
        if not names:
            for oid, val in snmp_walk(host, _IF_SPEED, s.snmp_community, s.snmp_version, s.snmp_port, s.snmp_timeout_sec):
                if isinstance(val, int):
                    idx = oid.rsplit(".", 1)[-1]
                    speeds[idx] = speeds.get(idx) or max(1, val // 1_000_000)
        self._names, self._speeds, self._meta_host = names, speeds, host

    def sample(self, host: str) -> dict:
        """Sample the router at ``host``; returns the snapshot dict."""
        s = get_settings()
        if not s.snmp_enabled:
            return self._store({"available": False, "source": "snmp", "reason": "disabled"})
        if not host:
            return self._store({"available": False, "source": "snmp", "reason": "no_gateway"})
        now = time.monotonic()
        if now < self._cooldown_until:
            return self._store(self._last or {"available": False, "source": "snmp", "reason": "cooldown"})

        in_rows = snmp_walk(host, _IF_IN_OCTETS, s.snmp_community, s.snmp_version, s.snmp_port, s.snmp_timeout_sec)
        if not in_rows:
            self._cooldown_until = now + _TIMEOUT_AFTER_FAILURE_SEC
            return self._store({"available": False, "source": "snmp", "reason": "no_response", "gateway": host})
        out_rows = snmp_walk(host, _IF_OUT_OCTETS, s.snmp_community, s.snmp_version, s.snmp_port, s.snmp_timeout_sec)
        if not out_rows:
            self._cooldown_until = now + _TIMEOUT_AFTER_FAILURE_SEC
            return self._store({"available": False, "source": "snmp", "reason": "no_response", "gateway": host})
        self._load_meta(host)

        def _table(rows: list[tuple[str, object]]) -> dict[str, int]:
            return {oid.rsplit(".", 1)[-1]: int(val) for oid, val in rows if isinstance(val, int)}

        cur_in = _table(in_rows)
        cur_out = _table(out_rows)

        if not self._prev_ts:
            self._prev_in, self._prev_out, self._prev_ts = cur_in, cur_out, now
            return self._store({"available": True, "source": "snmp", "gateway": host, "warming_up": True})

        dt = max(now - self._prev_ts, 0.001)
        deltas = []
        for idx, cur in cur_in.items():
            prev = self._prev_in.get(idx)
            if prev is None:
                continue
            d_in = max(0, cur - prev)
            d_out = max(0, cur_out.get(idx, 0) - self._prev_out.get(idx, 0))
            mbps_in = d_in * 8 / dt / 1e6
            mbps_out = d_out * 8 / dt / 1e6
            deltas.append({"index": idx, "mbps_in": mbps_in, "mbps_out": mbps_out})

        self._prev_in, self._prev_out, self._prev_ts = cur_in, cur_out, now

        if not deltas:
            return self._store({"available": False, "source": "snmp", "reason": "empty", "gateway": host})

        desired = s.snmp_interface.strip()
        if desired:
            pick = next(
                (d for d in deltas if self._names.get(d["index"]) == desired or d["index"] == desired),
                None,
            ) or max(deltas, key=lambda d: d["mbps_in"] + d["mbps_out"])
        else:
            pick = max(deltas, key=lambda d: d["mbps_in"] + d["mbps_out"])

        idx = pick["index"]
        speed = self._speeds.get(idx, 0) or 0
        utilization = round((pick["mbps_in"] + pick["mbps_out"]) / max(speed, 0.01) * 100, 1) if speed else 0.0
        return self._store(
            {
                "available": True,
                "source": "snmp",
                "gateway": host,
                "interface": self._names.get(idx) or f"if{idx}",
                "interface_index": idx,
                "mbps_in": round(pick["mbps_in"], 2),
                "mbps_out": round(pick["mbps_out"], 2),
                "speed_mbps": speed,
                "utilization": round(min(utilization, 99.0), 1),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
