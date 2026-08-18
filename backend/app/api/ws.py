from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import services
from ..events import get_broker

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    broker = get_broker()
    if broker is None:
        await websocket.close()
        return
    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "payload": {
                    "devices": services.devices_payload(),
                    "alerts": services.alerts_payload(),
                    "bandwidth": services.bandwidth_payload(),
                    "stats": services.stats_payload(),
                },
            }
        )
        async for event in broker.subscribe():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
