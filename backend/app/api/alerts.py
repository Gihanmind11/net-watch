from fastapi import APIRouter, Depends, HTTPException, status

from .. import services, store
from ..security import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts() -> dict:
    return services.alerts_payload()


@router.delete("/{alert_id}", dependencies=[Depends(get_current_user)])
def resolve_alert(alert_id: int) -> dict:
    alert = next((a for a in store.alerts() if a.id == alert_id), None)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    with store.transaction():
        alert.resolved = 1
    store.save()
    return {"status": "ok"}


@router.delete("", dependencies=[Depends(get_current_user)])
def clear_alerts() -> dict:
    with store.transaction():
        for alert in store.alerts():
            alert.resolved = 1
    store.save()
    return {"status": "ok"}
