from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update

from .. import services
from ..database import SessionLocal
from ..models import Alert
from ..security import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def list_alerts() -> dict:
    return services.alerts_payload()


@router.delete("/{alert_id}", dependencies=[Depends(get_current_user)])
def resolve_alert(alert_id: int) -> dict:
    with SessionLocal() as db:
        alert = db.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
        alert.resolved = 1
        db.commit()
    return {"status": "ok"}


@router.delete("", dependencies=[Depends(get_current_user)])
def clear_alerts() -> dict:
    with SessionLocal() as db:
        db.execute(update(Alert).values(resolved=1))
        db.commit()
    return {"status": "ok"}
