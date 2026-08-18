from fastapi import APIRouter

from .. import services

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats() -> dict:
    return services.stats_payload()
