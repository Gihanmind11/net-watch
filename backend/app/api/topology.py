from fastapi import APIRouter

from .. import services

router = APIRouter(prefix="/api/topology", tags=["topology"])


@router.get("")
def topology() -> dict:
    return services.topology_payload()
