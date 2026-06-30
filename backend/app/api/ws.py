"""WebSocket endpoint streaming live council activity for a chat."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from quorum_core.core.events import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws/chats/{chat_id}")
async def chat_ws(websocket: WebSocket, chat_id: str) -> None:
    await websocket.accept()
    queue = event_bus.subscribe(chat_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # send after close
        pass
    finally:
        event_bus.unsubscribe(chat_id, queue)
