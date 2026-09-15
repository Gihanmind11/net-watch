from fastapi import APIRouter, Query

from .. import services

router = APIRouter(prefix="/api/bandwidth", tags=["bandwidth"])

# The Traffic page's range buttons map straight onto this window.
_MIN_HISTORY_MINUTES = 1
_MAX_HISTORY_MINUTES = 1440


@router.get("")
def bandwidth(
    minutes: int = Query(
        services.DEFAULT_HISTORY_MINUTES,
        ge=_MIN_HISTORY_MINUTES,
        le=_MAX_HISTORY_MINUTES,
        description="Historical window in minutes (defaults to the last 5).",
    ),
) -> dict:
    """Current rates, interface statistics and the historical traffic series."""
    return services.bandwidth_payload(minutes=minutes, fetch_history=True)


@router.get("/interfaces")
def interfaces() -> dict:
    return services.interfaces_payload()


@router.get("/top-talkers")
def top_talkers() -> dict:
    return services.top_talkers_payload()
