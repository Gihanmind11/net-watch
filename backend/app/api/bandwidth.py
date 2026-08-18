from fastapi import APIRouter

from .. import services

router = APIRouter(prefix="/api/bandwidth", tags=["bandwidth"])


@router.get("")
def bandwidth() -> dict:
    return services.bandwidth_payload()


@router.get("/interfaces")
def interfaces() -> dict:
    return services.interfaces_payload()


@router.get("/top-talkers")
def top_talkers() -> dict:
    return services.top_talkers_payload()
