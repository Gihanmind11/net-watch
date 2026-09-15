import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import services, store
from .api import alerts, auth, bandwidth, devices, scan, stats, topology, wifi, ws
from .config import get_settings
from .database import init_db
from .events import init_broker
from .scheduler import MonitorScheduler
from .traffic_history import traffic_history

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    store.load()
    # Read the persisted traffic history back before the scheduler records new
    # buckets, so the Traffic page has the series immediately after a restart
    # (blocking object reads → worker thread).
    loaded = await asyncio.to_thread(traffic_history.load)
    if loaded:
        logger.info("Restored %d traffic-history shard(s) (%d buckets) from Storage", loaded, len(traffic_history))
    broker = init_broker()
    services.protocol_monitor.start()
    app.state.scan_lock = asyncio.Lock()
    app.state.broker = broker
    scheduler = MonitorScheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.stop()
    # Persist the buckets recorded since the last hourly shard write.
    await asyncio.to_thread(traffic_history.flush)
    services.protocol_monitor.stop()
    await broker.close()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    devices.router,
    alerts.router,
    bandwidth.router,
    topology.router,
    stats.router,
    scan.router,
    ws.router,
    wifi.router,
):
    app.include_router(router)
