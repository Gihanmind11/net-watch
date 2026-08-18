import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import services
from .api import alerts, auth, bandwidth, devices, scan, stats, topology, ws
from .config import get_settings
from .database import init_db
from .events import init_broker
from .scheduler import MonitorScheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    services.seed_demo_if_empty()
    broker = init_broker()
    services.protocol_monitor.start()
    app.state.scan_lock = asyncio.Lock()
    app.state.broker = broker
    scheduler = MonitorScheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.stop()
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
):
    app.include_router(router)
