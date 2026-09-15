"""Regression tests for the historical traffic series (Traffic page chart).

Covers the bug where the "Historical Traffic" chart was permanently empty: the
refactor from the SQLAlchemy ``bandwidth_logs`` table to Supabase Storage
dropped the history writer, so ``/api/bandwidth`` always answered
``"history": []``. These tests pin the replacement — bucket averaging, the
requested range, hourly shard persistence and the retention cleanup — without
ever touching the network (the Storage helpers are stubbed).
"""

import json
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store, traffic_history


def iso_utc(epoch: float) -> str:
    """Naive UTC ISO string, as the API emits it."""
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def snapshot(mbps_in: float, mbps_out: float) -> list[dict]:
    """Two interfaces, as ``BandwidthSampler.snapshot()`` returns them."""
    return [
        {"interface": "Ethernet", "mbps_in": mbps_in, "mbps_out": mbps_out},
        {"interface": "Wi-Fi", "mbps_in": mbps_in, "mbps_out": mbps_out},
    ]


class TrafficHistoryTests(unittest.TestCase):
    def setUp(self):
        # Memory-only by default, and the Storage helpers are stubbed so that no
        # test can reach the network; tearDown puts the originals back.
        self._store = {
            name: getattr(store, name)
            for name in ("storage_configured", "read_json", "write_json", "list_paths", "delete_paths")
        }
        store.storage_configured = lambda: False
        self.history = traffic_history.TrafficHistory(bucket_sec=10, retention_hours=2)

    def tearDown(self):
        for name, original in self._store.items():
            setattr(store, name, original)

    # ---------------- bucketing ----------------

    def test_bucket_closes_once_per_bucket_interval(self):
        self.assertFalse(self.history.record(snapshot(1.0, 2.0), now=1000))
        self.assertFalse(self.history.record(snapshot(1.0, 2.0), now=1005))
        # Crossing the 10 s boundary closes the bucket and opens the next one.
        self.assertTrue(self.history.record(snapshot(1.0, 2.0), now=1010))
        self.assertEqual(len(self.history.series(5, now=1010)), 1)
        self.assertEqual(len(self.history), 1)

    def test_point_is_the_mean_of_its_bucket_summed_over_interfaces(self):
        self.history.record(snapshot(1.0, 2.0), now=1000)  # 2.0 in / 4.0 out total
        self.history.record(snapshot(3.0, 0.0), now=1005)  # 6.0 in / 0.0 out total
        self.history.record(snapshot(0.0, 0.0), now=1010)  # closes the bucket

        point = self.history.series(5, now=1010)[0]
        self.assertEqual(point["recorded_at"], iso_utc(1000))
        self.assertEqual(point["mbps_in"], 4.0)  # mean of 2.0 and 6.0
        self.assertEqual(point["mbps_out"], 2.0)  # mean of 4.0 and 0.0
        # Byte counts stay in step with the rate (bytes per second).
        self.assertEqual(point["bytes_in"], int(4.0 * 1e6 / 8))
        self.assertEqual(point["bytes_out"], int(2.0 * 1e6 / 8))

    def test_open_bucket_is_not_served_before_it_closes(self):
        self.history.record(snapshot(5.0, 5.0), now=1000)
        self.assertEqual(self.history.series(5, now=1000), [])

    # ---------------- range + downsampling ----------------

    def test_series_only_returns_the_requested_window(self):
        for step in range(61):  # 60 closed 10 s buckets = 10 minutes
            self.history.record(snapshot(1.0, 1.0), now=1000 + step * 10)
        now = 1000 + 60 * 10  # the bucket that is still open starts here

        five = self.history.series(5, now=now)
        ten = self.history.series(10, now=now)
        self.assertEqual(len(five), 30)  # last 5 of the 10 minutes
        self.assertEqual(len(ten), 60)
        # Oldest first, spanning exactly the requested window.
        self.assertEqual(five[0]["recorded_at"], iso_utc(now - 5 * 60))
        self.assertEqual(five[-1]["recorded_at"], iso_utc(now - 10))
        self.assertEqual([row["recorded_at"] for row in five], sorted(row["recorded_at"] for row in five))
        self.assertEqual(ten[0]["recorded_at"], iso_utc(now - 10 * 60))

    def test_long_range_is_downsampled_to_a_bounded_point_count(self):
        history = traffic_history.TrafficHistory(bucket_sec=1, retention_hours=2)
        for step in range(1201):  # 1200 closed 1 s buckets
            history.record(snapshot(2.0, 1.0), now=1_000_000 + step)

        points = history.series(20, now=1_000_000 + 1200)
        self.assertEqual(len(points), traffic_history._MAX_POINTS)
        self.assertEqual(points[0]["bucket_sec"], 2)  # each point covers 2 buckets
        # Averaging keeps the level (4.0/2.0 Mbps is the two-interface total).
        self.assertEqual(points[-1]["mbps_in"], 4.0)
        self.assertEqual(points[-1]["mbps_out"], 2.0)

    # ---------------- Supabase Storage ----------------

    def test_shard_paths_are_hourly_utc_documents(self):
        self.assertEqual(traffic_history.shard_key(0), "1970-01-01T00")
        self.assertEqual(traffic_history.shard_path(0), "bandwidth/1970-01-01T00.json")
        self.assertEqual(traffic_history.shard_path(3599), "bandwidth/1970-01-01T00.json")
        self.assertEqual(traffic_history.shard_path(3600), "bandwidth/1970-01-01T01.json")
        self.assertEqual(traffic_history.shard_keys(0, 7200), ["1970-01-01T00", "1970-01-01T01", "1970-01-01T02"])

    def test_stored_key_only_accepts_shard_names(self):
        self.assertEqual(traffic_history.stored_key("bandwidth/2026-09-15T10.json"), "2026-09-15T10")
        self.assertEqual(traffic_history.stored_key("2026-09-15T10.json"), "2026-09-15T10")
        for name in ("state.json", "bandwidth/state.json", "bandwidth/sub/file.json", "bandwidth/"):
            with self.subTest(name=name):
                self.assertIsNone(traffic_history.stored_key(name))

    def test_closed_bucket_is_uploaded_as_one_hour_shard(self):
        store.storage_configured = lambda: True
        written: dict[str, str] = {}
        store.write_json = lambda path, payload: written.setdefault(path, payload) is not None

        self.history.record(snapshot(1.5, 0.5), now=1000)
        self.assertTrue(self.history.record(snapshot(1.5, 0.5), now=1010))
        self.assertTrue(self.history.flush())

        path = next(iter(written))
        self.assertEqual(path, traffic_history.shard_path(1000))
        document = json.loads(written[path])
        self.assertEqual(document["hour"], traffic_history.shard_key(1000))
        self.assertEqual(document["bucket_sec"], 10)
        sample = document["samples"][0]
        self.assertEqual(sample["recorded_at"], iso_utc(1000))
        self.assertEqual(sample["mbps_in"], 3.0)  # two interfaces × 1.5 Mbps
        self.assertEqual(sample["mbps_out"], 1.0)
        self.assertNotIn("t", sample)  # internal epoch is not persisted

    def test_flush_is_a_noop_in_memory_only_mode(self):
        self.history.record(snapshot(1.0, 1.0), now=1000)
        self.assertTrue(self.history.record(snapshot(1.0, 1.0), now=1010))
        self.assertFalse(self.history.flush())
        self.assertEqual(len(self.history.series(5, now=1010)), 1)  # still served

    def test_load_restores_persisted_buckets_into_the_series(self):
        store.storage_configured = lambda: True
        bucket = int(time.time() // 10) * 10
        document = {
            "hour": traffic_history.shard_key(bucket),
            "bucket_sec": 10,
            "samples": [{"recorded_at": iso_utc(bucket), "mbps_in": 7.25, "mbps_out": 3.5}],
        }
        requested: list[str] = []

        def fake_read(path: str) -> dict:
            requested.append(path)
            return document if path == traffic_history.shard_path(bucket) else {}

        store.read_json = fake_read

        # Every shard covering the last hour is read (the fake one holds data,
        # the others do not exist yet, which still counts as a completed read).
        self.assertGreaterEqual(self.history.load(hours=1), 1)
        series = self.history.series(5, now=time.time())
        self.assertEqual([row["mbps_in"] for row in series], [7.25])
        self.assertEqual(series[0]["mbps_out"], 3.5)
        self.assertIn(traffic_history.shard_path(bucket), requested)
        # A shard already read is not fetched a second time.
        self.assertEqual(self.history.load(hours=1), 0)

    def test_purge_deletes_only_expired_traffic_shards(self):
        store.storage_configured = lambda: True
        expired = traffic_history.shard_key(time.time() - 3 * 3600)  # retention is 2 h
        recent = traffic_history.shard_key(time.time())
        store.list_paths = lambda prefix: [f"{expired}.json", f"{recent}.json", "state.json"]
        deleted: list[list[str]] = []
        store.delete_paths = lambda paths: deleted.append(paths) or True

        self.assertEqual(self.history.purge(), 1)
        self.assertEqual(deleted, [[f"bandwidth/{expired}.json"]])

    # ---------------- configuration ----------------

    def test_disabled_history_records_and_serves_nothing(self):
        settings = traffic_history.settings
        settings.traffic_history_enabled = False
        try:
            self.assertFalse(self.history.record(snapshot(1.0, 1.0), now=1000))
            self.history.record(snapshot(1.0, 1.0), now=1010)
            self.assertEqual(self.history.series(5, now=1010), [])
        finally:
            settings.traffic_history_enabled = True


if __name__ == "__main__":
    unittest.main(verbosity=2)