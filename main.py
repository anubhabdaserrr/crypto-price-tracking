import asyncio
import json
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
import uvicorn

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Docs: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
BINANCE_WS = (
    "wss://stream.binance.com/stream"
    "?streams=btcusdt@ticker/ethusdt@ticker/bnbusdt@ticker"
)

connected_clients = set()
latest_prices = {}

price_queue = asyncio.Queue()

MAX_CONNECTIONS = 10

# Producer
async def listen_binance():

    async with websockets.connect(BINANCE_WS) as ws:
        print("Listening")
        while True:
            print(1)
            msg = json.loads(await ws.recv())
            print("Received from Binance:", msg)
            data = msg["data"]

            update = {
                "symbol": data["s"],
                "price": data["c"],
                "change_24h": data["P"],
                "timestamp": data["E"]
            }

            latest_prices[data["s"]] = update

            await price_queue.put(update)

# Consumer
async def broadcaster():

    while True:
        message = await price_queue.get()

        dead = []

        for client in connected_clients:
            try:
                await client.send_json(message)
            except:
                dead.append(client)

        for c in dead:
            connected_clients.remove(c)

# Websocket for clients
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    if len(connected_clients) >= MAX_CONNECTIONS:
        await websocket.accept()
        await websocket.send_json({"error": "connection limit reached"})
        await websocket.close()
        return

    await websocket.accept()
    connected_clients.add(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

# Handle startup functions
@app.on_event("startup")
async def startup():

    asyncio.create_task(listen_binance())
    asyncio.create_task(broadcaster())

@app.get("/")
async def welcome():
    return {"msg": "Welcome to Live Crypto Prices API V1"}

@app.get("/dashboard")
async def get_dashboard():
    return FileResponse("index.html")

@app.get("/price/all")
@limiter.limit("20/minute")
async def get_prices_all(request: Request):
    return latest_prices

@app.get("/price/{symbol}")
@limiter.limit("20/minute") # limits to max. x requests per minute per IP
async def get_price(request: Request, symbol: str):

    symbol = symbol.upper()

    if symbol not in latest_prices:
        return {"error": "symbol not found"}

    return latest_prices[symbol]


if __name__ == "__main__":
    uvicorn.run(app, port=8000)
