import websockets
import asyncio

async def test():
    uri = "ws://localhost:8000/ws"

    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            print(msg)

asyncio.run(test())