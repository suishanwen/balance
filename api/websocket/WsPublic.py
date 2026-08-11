import asyncio
import json
import logging
import threading
import websockets
from collections.abc import Callable
from api.websocket.WebSocketFactory import WebSocketFactory

logger = logging.getLogger(__name__)


class WsPublic:
    def __init__(self, url: str):
        self.url = url
        self.websocket = None
        self.callback = None
        self.factory = WebSocketFactory(url)

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.connected_event = threading.Event()
        self.stop_event = threading.Event()
        self.subscriptions: list[list] = []
        self.reconnect_interval = 1  # 更快重连：1秒

        self.thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _connect(self):
        try:
            self.websocket = await self.factory.connect()
            self.connected_event.set()
            logger.info(f"WebSocket connected to {self.url}")
        except Exception as e:
            logger.error(f"Initial connection failed: {e}, url={self.url}")
            raise

    async def _resubscribe(self):
        for params in self.subscriptions:
            payload = json.dumps({"op": "subscribe", "args": params})
            await self.websocket.send(payload)
            logger.info(f"Resubscribed with payload: {payload}")

    def connect(self):
        future = self._run_async(self._connect())
        future.result()

    def start(self):
        if not self.thread.is_alive():
            raise RuntimeError("WebSocket thread not running")
        logger.info("Starting WebSocket...")
        self.connect()
        self._run_async(self._consume())
        self._run_async(self._heartbeat())

    async def _consume(self):
        while not self.stop_event.is_set():
            try:
                async for message in self.websocket:
                    logger.debug("Received message: %s", message)
                    if self.callback:
                        try:
                            self.callback(message)
                        except Exception as cb_err:
                            logger.error(f"Callback error: {cb_err}")
                    else:
                        logger.warning("Callback is not set, skipping message")

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Connection closed: code={e.code}, reason={e.reason}, url={self.url}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}, url={self.url}")

            # 清除状态并立即重连
            self.connected_event.clear()
            self.websocket = None

            if self.stop_event.is_set():
                break

            logger.info(f"Reconnecting in {self.reconnect_interval} seconds... url={self.url}")
            await asyncio.sleep(self.reconnect_interval)

            try:
                await self._connect()
                await self._resubscribe()
            except Exception as re:
                logger.error(f"Reconnection failed: {re}, url={self.url}")

    async def _heartbeat(self):
        while not self.stop_event.is_set():
            try:
                if self.websocket:
                    pong = await self.websocket.ping()
                    await asyncio.wait_for(pong, timeout=10)
                    logger.debug("Heartbeat pong received")
                await asyncio.sleep(20)
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}, url={self.url}")
                self.connected_event.clear()
                self.websocket = None
                await asyncio.sleep(self.reconnect_interval)

    def subscribe(self, params: list, callback: Callable[[str], None]):
        self.connected_event.wait()
        self.callback = callback
        if params not in self.subscriptions:
            self.subscriptions.append(params)

        async def _subscribe():
            payload = json.dumps({"op": "subscribe", "args": params})
            await self.websocket.send(payload)
            logger.info(f"Subscribed with payload: {payload}")

        future = self._run_async(_subscribe())
        return future.result()

    def unsubscribe(self, params: list, callback: Callable[[str], None] = None):
        self.connected_event.wait()
        if callback:
            self.callback = callback
        if params in self.subscriptions:
            self.subscriptions.remove(params)

        async def _unsubscribe():
            payload = json.dumps({"op": "unsubscribe", "args": params})
            await self.websocket.send(payload)
            logger.info(f"Unsubscribed with payload: {payload}")

        future = self._run_async(_unsubscribe())
        return future.result()

    def stop(self):
        self.stop_event.set()

        async def _stop():
            try:
                if self.websocket:
                    await self.websocket.close()
                    logger.info("WebSocket closed properly")
            finally:
                await self.factory.close()

        self._run_async(_stop()).result()
        self.connected_event.clear()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        logger.info("WebSocket client stopped")