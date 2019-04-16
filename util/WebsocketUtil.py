import json
import zlib
import time
import threading
import websockets
from util.Logger import logger


def inflate(data):
    decompress = zlib.decompressobj(
        -zlib.MAX_WBITS  # see above
    )
    inflated = decompress.decompress(data)
    inflated += decompress.flush()
    return inflated


async def ping(websocket, client):
    time.sleep(15)
    res = await websocket.send("ping")
    if res == "pong":
        logger.info(res)
        await ping(websocket, client)
    else:
        logger.warning("restart socket")
        websocket.close()
        conn(client)


async def recv(websocket, client):
    try:
        while True:
            price_info = client.priceInfo[client.SYMBOL_T]
            res = await websocket.recv()
            res = json.loads(inflate(res))
            if res and res.get("data") is not None:
                data = res.get("data")
                price_info["asks"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["asks"]))
                price_info["bids"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["bids"]))
    except Exception as e:
        logger.warning("socket closed!{}".format(e))


def conn(client):
    pair = client.SYMBOL_T.upper().replace("_", "-")
    websocket = websockets.connect('wss://real.okex.com:10442/ws/v3')
    sub_param = {"op": "subscribe", "args": ["spot/depth5:{}".format(pair)]}
    sub_str = json.dumps(sub_param)
    websocket.send(sub_str)
    threading.Thread(target=ping, args=(websocket, client,)).start()
    threading.Thread(target=recv, args=(websocket, client,)).start()
