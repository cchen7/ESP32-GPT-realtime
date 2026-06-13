"""Device-facing WebSocket server.

Spins up a :class:`bridge.session.DeviceSession` per inbound connection.
"""
import asyncio

import websockets

from bridge import config
from bridge.session import DeviceSession


async def _on_connection(ws):
    peer = ws.remote_address
    print(f"[ws] new connection from {peer}")
    session = DeviceSession(ws)
    try:
        await session.run()
    finally:
        print(f"[ws] connection from {peer} closed")


async def serve() -> None:
    print(f"[ws] listening on ws://{config.WS_HOST}:{config.WS_PORT}")
    async with websockets.serve(
        _on_connection,
        config.WS_HOST,
        config.WS_PORT,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()  # run forever
