from fastapi import APIRouter, Depends, HTTPException, status

from .. import services, store
from ..security import get_current_user

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def list_devices() -> dict:
    return services.devices_payload()


@router.get("/{ip}")
def get_device(ip: str) -> dict:
    device = next((d for d in store.devices() if d.ip_address == ip), None)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return services.device_payload(device)


@router.delete("", dependencies=[Depends(get_current_user)])
def clear_devices() -> dict:
    """Reset the inventory."""
    with store.transaction():
        store.devices().clear()
        store.alerts().clear()
    store.save()
    return {"status": "ok"}
