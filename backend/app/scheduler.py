"""Background monitoring jobs driven by APScheduler (async)."""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import services
from .config import get_settings


class MonitorScheduler:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        s = self._scheduler
        cfg = {"max_instances": 1, "coalesce": True}
        s.add_job(services.run_scan, "interval", seconds=self._settings.scan_interval_sec, id="scan", **cfg)
        s.add_job(services.run_ping_cycle, "interval", seconds=self._settings.ping_interval_sec, id="ping", **cfg)
        s.add_job(services.run_bandwidth_cycle, "interval", seconds=self._settings.bandwidth_interval_sec, id="bandwidth", **cfg)
        s.add_job(services.cleanup_old_logs, "cron", hour=3, id="cleanup", max_instances=1, coalesce=True)
        s.add_job(
            services.run_scan,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=1),
            id="initial_scan",
            **cfg,
        )
        s.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
