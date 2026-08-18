from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select

from .. import services
from ..database import SessionLocal
from ..models import Alert, BandwidthLog, Device, PingHistory
from ..security import get_current_user

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def list_devices() -> dict:
    return services.devices_payload()


@router.get("/{ip}")
def get_device(ip: str) -> dict:
    with SessionLocal() as db:
        device = db.scalar(select(Device).where(Device.ip_address == ip))
        if device is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
        return services.device_payload(device)


@router.delete("", dependencies=[Depends(get_current_user)])
def clear_devices() -> dict:
    """Reset the inventory (demo convenience)."""
    with SessionLocal() as db:
        db.execute(delete(PingHistory))
        db.execute(delete(BandwidthLog))
        db.execute(delete(Alert))
        db.execute(delete(Device))
        db.commit()
    return {"status": "ok"}
