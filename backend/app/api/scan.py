import asyncio

from fastapi import APIRouter, Depends, Request

from .. import services
from ..security import get_current_user

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("", dependencies=[Depends(get_current_user)])
async def trigger_scan(request: Request) -> dict:
    """Manual on-demand discovery scan (mutex with the scheduled scan)."""
    lock: asyncio.Lock = request.app.state.scan_lock
    async with lock:
        return await services.run_scan()
