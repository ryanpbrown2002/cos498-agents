from __future__ import annotations

import asyncio
import json
import logging
import os
from http.server import SimpleHTTPRequestHandler
from functools import partial
from typing import Any, Set

import websockets

from voicefront.events.bus import BUILD_RESULT, EventBus

logger = logging.getLogger(__name__)


class ReloadServer:
    """WebSocket server that pushes reload/error signals to browser clients.
    Also serves the generated/ directory and client.html over HTTP."""

    def __init__(
        self,
        event_bus: EventBus,
        generated_dir: str,
        ws_port: int = 8765,
        http_port: int = 8080,
    ) -> None:
        self.event_bus = event_bus
        self.generated_dir = generated_dir
        self.ws_port = ws_port
        self.http_port = http_port
        self._clients: Set[Any] = set()
        self._on_transcript = None  # callback for transcript messages from browser

        self.event_bus.subscribe(BUILD_RESULT, self._on_build_result)

    def set_transcript_callback(self, callback) -> None:
        """Set the callback for when the browser sends a transcript."""
        self._on_transcript = callback

    async def _on_build_result(self, payload: dict) -> None:
        if payload.get("passed"):
            message = json.dumps({"type": "reload"})
        else:
            message = json.dumps({"type": "error", "errors": payload.get("errors", [])})

        await self._broadcast(message)

    async def _broadcast(self, message: str) -> None:
        if not self._clients:
            return
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        self._clients -= disconnected

    async def _handle_ws(self, websocket) -> None:
        self._clients.add(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._clients))
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "transcript" and self._on_transcript:
                        await self._on_transcript(data.get("text", ""))
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from WebSocket client: %s", message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("WebSocket client disconnected (%d remaining)", len(self._clients))

    async def start_ws(self) -> None:
        """Start the WebSocket server."""
        self._ws_server = await websockets.serve(self._handle_ws, "localhost", self.ws_port)
        logger.info("WebSocket server started on ws://localhost:%d", self.ws_port)

    async def start_http(self) -> None:
        """Start a simple HTTP server for the generated files and client."""
        server_dir = os.path.dirname(os.path.abspath(__file__))
        generated_dir = self.generated_dir

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=generated_dir, **kwargs)

            def do_GET(self):
                if self.path == "/" or self.path == "/client" or self.path == "/client.html":
                    client_path = os.path.join(server_dir, "client.html")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    with open(client_path, "rb") as f:
                        self.wfile.write(f.read())
                elif self.path == "/preview" or self.path == "/preview/":
                    self.path = "/index.html"
                    super().do_GET()
                else:
                    super().do_GET()

            def log_message(self, format, *args):
                logger.debug("HTTP: %s", format % args)

        loop = asyncio.get_event_loop()
        self._http_server = await loop.run_in_executor(None, lambda: None)

        # Use asyncio-compatible server
        import socketserver
        handler = Handler
        self._httpd = socketserver.TCPServer(("", self.http_port), handler)
        self._httpd.allow_reuse_address = True

        logger.info("HTTP server started on http://localhost:%d", self.http_port)
        loop.run_in_executor(None, self._httpd.serve_forever)

    async def stop(self) -> None:
        if hasattr(self, "_ws_server"):
            self._ws_server.close()
            await self._ws_server.wait_closed()
        if hasattr(self, "_httpd"):
            self._httpd.shutdown()
