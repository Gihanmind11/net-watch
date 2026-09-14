"""Historical traffic, bucketed in memory and persisted to Supabase Storage.

The Traffic page's "Historical Traffic" chart needs a time series, but Supabase
Storage is object storage with no server-side querying — so the series is
written as one JSON document per UTC hour under the ``bandwidth/`` prefix and
read back with plain object reads::

    netwatch/bandwidth/2026-09-15T10.json
        {"hour": "2026-09-15T10", "bucket_sec": 10, "samples": [
            {"recorded_at": "2026-09-15T10:00:00", "mbps_in": 12.34,
             "mbps_out": 5.67, "bytes_in": 1542500, "bytes_out": 708750}, ...]}

Hourly sharding keeps every upload small (a full hour is ~360 buckets ≈ 35 KB)
and turns a long dashboard range into a handful of reads (6 h → 7 objects).
Only the shard of the bucket that just closed is rewritten, and only once per
``traffic_history_bucket_sec`` — not once per 2 s sample — so the object store
sees a few small writes per minute instead of thousands.

The in-memory buffer is authoritative for the running process: the dashboard is
served from it (no object read on the 2 s poll) and the stored shards are what
make the series survive a restart — ``load`` reads the recent ones back at
startup. Each point is the mean of the samples inside its bucket, summed over
this host's interfaces, i.e. the same figure the live "Last 60 Seconds" chart on
the Traffic page plots, so the two charts agree.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from datetime import datetime, timezone

from . import store
from .config import get_settings

settings = get_settings()

PREFIX = "bandwidth/"
_SHARD_SUFFIX = ".json"
_SHARD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}\.json$")

# A wide range is averaged down to at most this many points before it is sent,
# which keeps the JSON payload (~600 × 110 B ≈ 65 KB for 24 h) reasonable.
_MAX_POINTS = 600

# A failed shard read is retried on the next call, but not more often than this.
_RETRY_AFTER_SEC = 30.0


def _iso(epoch: float) -> str:
    """Naive UTC timestamp, matching every other timestamp the API returns."""
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _epoch(recorded_at: str) -> float:
    """Epoch seconds for a naive-UTC ``recorded_at`` value (0.0 when unusable)."""
    try:
        return datetime.fromisoformat(recorded_at).replace(tzinfo=timezone.utc).timestamp()
    except (AttributeError, TypeError, ValueError):
        return 0.0


def shard_key(epoch: float) -> str:
    """The ``YYYY-MM-DDTHH`` shard key an epoch second belongs to (UTC)."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H")


def shard_path(epoch: float) -> str:
    """Full Storage path of the shard an epoch second belongs to."""
    return f"{PREFIX}{shard_key(epoch)}{_SHARD_SUFFIX}"


def shard_keys(start: float, end: float) -> list[str]:
    """Every shard key between two epoch seconds, oldest first (inclusive)."""
    keys: list[str] = []
    cursor = int(start // 3600) * 3600
    last = int(end)
    while cursor <= last:
        keys.append(shard_key(cursor))
        cursor += 3600
    return keys


def stored_key(name: str) -> str | None:
    """Shard key of a listed object name, or ``None`` when it is not a shard.

    Guards the retention cleanup: only names this module itself writes are ever
    deleted, so ``state.json`` (devices/alerts) can never be touched.
    """
    candidate = name[len(PREFIX) :] if name.startswith(PREFIX) else name
    if not _SHARD_RE.match(candidate):
        return None
    return candidate[: -len(_SHARD_SUFFIX)]


class TrafficHistory:
    """Rolling traffic series: bucket the samples, persist the closed buckets.

    Thread-safe: ``record`` runs on the scheduler, while ``series``/``load``/
    ``flush``/``purge`` may run on API worker threads or the event loop.
    """

    def __init__(self, bucket_sec: int | None = None, retention_hours: int | None = None) -> None:
        self.bucket_sec = max(1, int(bucket_sec or settings.traffic_history_bucket_sec))
        self.retention_hours = max(1, int(retention_hours or settings.traffic_history_retention_hours))
        self._lock = threading.RLock()
        self._shards: dict[str, list[dict]] = {}  # shard key -> completed buckets
        self._open: dict | None = None  # bucket being filled right now
        self._dirty: set[str] = set()  # shards changed since the last successful write
        self._loaded: set[str] = set()  # shards already read from Storage
        self._retry_at = 0.0

    # ---------------- recording ----------------

    def record(self, snapshots: list[dict], now: float | None = None) -> bool:
        """Fold this instant's per-interface rates into the open bucket.

        Returns True when this call closed a bucket, i.e. when the shard holding
        it now needs to be persisted (``flush``).
        """
        if not settings.traffic_history_enabled or not snapshots:
            return False
        epoch = time.time() if now is None else now
        total_in = sum(float(s.get("mbps_in") or 0.0) for s in snapshots)
        total_out = sum(float(s.get("mbps_out") or 0.0) for s in snapshots)
        with self._lock:
            closed = self._roll(epoch)
            bucket = self._open
            bucket["sum_in"] += total_in
            bucket["sum_out"] += total_out
            bucket["n"] += 1
            self._trim(epoch - self.retention_hours * 3600)
        return closed

    def _roll(self, epoch: float) -> bool:
        """Start the bucket ``epoch`` belongs to; close and store the previous one."""
        start = int(epoch // self.bucket_sec) * self.bucket_sec
        if self._open is None:
            self._open = {"start": start, "sum_in": 0.0, "sum_out": 0.0, "n": 0}
            return False
        if self._open["start"] == start:
            return False
        self._close_open()
        self._open = {"start": start, "sum_in": 0.0, "sum_out": 0.0, "n": 0}
        return True

    def _close_open(self) -> None:
        bucket, self._open = self._open, None
        if not bucket or not bucket["n"]:
            return
        row = self._bucket_row(bucket)
        key = shard_key(bucket["start"])
        self._shards.setdefault(key, []).append(row)
        self._dirty.add(key)

    def _bucket_row(self, bucket: dict) -> dict:
        samples = max(1, bucket["n"])
        mbps_in = round(bucket["sum_in"] / samples, 2)
        mbps_out = round(bucket["sum_out"] / samples, 2)
        return {
            "t": float(bucket["start"]),
            "recorded_at": _iso(bucket["start"]),
            "mbps_in": mbps_in,
            "mbps_out": mbps_out,
            # Bytes-per-second equivalents, so a client that only ever consumed
            # `bytes_in`/`bytes_out` keeps working unchanged.
            "bytes_in": int(mbps_in * 1e6 / 8),
            "bytes_out": int(mbps_out * 1e6 / 8),
        }

    def _trim(self, cutoff: float | None = None) -> None:
        """Drop buckets past the retention window and any shard left empty."""
        if cutoff is None:
            cutoff = time.time() - self.retention_hours * 3600
        for key in [k for k, rows in self._shards.items() if rows and rows[-1]["t"] < cutoff]:
            self._shards.pop(key, None)
            self._dirty.discard(key)
            self._loaded.discard(key)

    # ---------------- querying ----------------

    def series(self, minutes: int, now: float | None = None, fetch_missing: bool = False) -> list[dict]:
        """Completed buckets of the last ``minutes`` minutes, oldest first.

        ``fetch_missing`` additionally reads shards that are not in memory yet
        (a range wider than what startup loaded). It performs blocking HTTP, so
        only the request path sets it — never the 2 s WebSocket push.
        """
        if not settings.traffic_history_enabled:
            return []
        epoch = time.time() if now is None else now
        window = max(1, min(int(minutes), self.retention_hours * 60))
        start = epoch - window * 60
        if fetch_missing:
            for key in shard_keys(start, epoch):
                self._read_shard(key)
        with self._lock:
            rows = [row for key in sorted(self._shards) for row in self._shards[key] if row["t"] >= start]
        return _downsample(rows, self.bucket_sec)

    def __len__(self) -> int:
        """Number of completed buckets currently held in memory."""
        with self._lock:
            return sum(len(rows) for rows in self._shards.values())

    # ---------------- Supabase Storage ----------------

    def flush(self) -> bool:
        """Upload every shard that changed since the last write.

        True when all of them are stored; False in memory-only mode or after a
        failed write (the shards stay dirty and are retried on the next bucket).
        """
        if not store.storage_configured():
            with self._lock:
                self._dirty.clear()  # nowhere to persist to: keep the history in memory
            return False
        with self._lock:
            pending = sorted(self._dirty)
        stored_all = True
        for key in pending:
            with self._lock:
                rows = list(self._shards.get(key, []))
            if not rows:
                with self._lock:
                    self._dirty.discard(key)
                continue
            payload = json.dumps(
                {
                    "hour": key,
                    "bucket_sec": self.bucket_sec,
                    "updated_at": _iso(time.time()),
                    "samples": [{k: v for k, v in row.items() if k != "t"} for row in rows],
                }
            )
            if store.write_json(f"{PREFIX}{key}{_SHARD_SUFFIX}", payload):
                with self._lock:
                    self._dirty.discard(key)
            else:
                stored_all = False
        return stored_all

    def load(self, hours: int | None = None) -> int:
        """Read the shards covering the last ``hours`` hours into memory.

        Objects that do not exist yet count as loaded (a cold bucket must not be
        re-read on every call); a *failed* read is not, so it is retried later.
        Returns the number of shards read.
        """
        if not store.storage_configured():
            return 0
        span = int(hours if hours is not None else settings.traffic_history_load_hours)
        now = time.time()
        return sum(1 for key in shard_keys(now - max(1, span) * 3600, now) if self._read_shard(key))

    def _read_shard(self, key: str) -> bool:
        """Pull one shard from Storage. False when already loaded or unreadable."""
        with self._lock:
            if key in self._loaded or time.monotonic() < self._retry_at:
                return False
        document = store.read_json(f"{PREFIX}{key}{_SHARD_SUFFIX}")
        if document is None:
            # Storage outage: retry later, but never in a tight loop.
            with self._lock:
                self._retry_at = time.monotonic() + _RETRY_AFTER_SEC
            return False
        rows = [self._from_stored(item) for item in document.get("samples", []) if isinstance(item, dict)]
        rows = sorted((row for row in rows if row["t"]), key=lambda row: row["t"])
        with self._lock:
            self._loaded.add(key)
            self._retry_at = 0.0
            known = {row["recorded_at"] for row in self._shards.get(key, [])}
            fresh = [row for row in rows if row["recorded_at"] not in known]
            if fresh:
                self._shards[key] = sorted(self._shards.get(key, []) + fresh, key=lambda row: row["t"])
            self._trim()
        return True

    @staticmethod
    def _from_stored(item: dict) -> dict:
        recorded_at = str(item.get("recorded_at", ""))
        try:
            mbps_in = float(item.get("mbps_in") or 0.0)
            mbps_out = float(item.get("mbps_out") or 0.0)
        except (TypeError, ValueError):
            mbps_in = mbps_out = 0.0
        return {
            "t": _epoch(recorded_at),
            "recorded_at": recorded_at,
            "mbps_in": round(mbps_in, 2),
            "mbps_out": round(mbps_out, 2),
            "bytes_in": int(mbps_in * 1e6 / 8),
            "bytes_out": int(mbps_out * 1e6 / 8),
        }

    def purge(self) -> int:
        """Delete stored shards older than the retention window. Returns how many."""
        if not store.storage_configured():
            return 0
        names = store.list_paths(PREFIX)
        if names is None:
            return 0
        cutoff = shard_key(time.time() - self.retention_hours * 3600)
        expired = [
            f"{PREFIX}{key}{_SHARD_SUFFIX}"
            for key in (stored_key(name) for name in names)
            if key and key < cutoff
        ]
        removed = len(expired) if expired and store.delete_paths(expired) else 0
        with self._lock:
            for key in [k for k in self._shards if k < cutoff]:
                self._shards.pop(key, None)
                self._dirty.discard(key)
                self._loaded.discard(key)
        return removed


def _downsample(rows: list[dict], bucket_sec: int, max_points: int = _MAX_POINTS) -> list[dict]:
    """Rows (oldest first) as API points, averaged down to at most ``max_points``.

    Each point is the mean of the buckets it covers, so a 6 h range still shows
    the shape of the traffic without sending thousands of samples.
    """
    ordered = sorted(rows, key=lambda row: row["t"])
    if not ordered:
        return []
    group = max(1, math.ceil(len(ordered) / max(1, max_points)))
    points: list[dict] = []
    for index in range(0, len(ordered), group):
        chunk = ordered[index : index + group]
        size = len(chunk)
        mbps_in = round(sum(row["mbps_in"] for row in chunk) / size, 2)
        mbps_out = round(sum(row["mbps_out"] for row in chunk) / size, 2)
        points.append(
            {
                # The newest bucket of the group, so the last point tracks "now".
                "recorded_at": chunk[-1]["recorded_at"],
                "bucket_sec": bucket_sec * size,
                "mbps_in": mbps_in,
                "mbps_out": mbps_out,
                "bytes_in": int(mbps_in * 1e6 / 8),
                "bytes_out": int(mbps_out * 1e6 / 8),
            }
        )
    return points


# Shared by the scheduler (records), the API (reads) and the cleanup job (purge).
traffic_history = TrafficHistory()
