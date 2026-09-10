from fastapi import APIRouter

from ..wifi import wifi_payload

router = APIRouter(prefix="/api/wifi", tags=["wifi"])


@router.get("")
def wifi() -> dict:
    return wifi_payload()
