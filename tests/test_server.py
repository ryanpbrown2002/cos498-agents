import asyncio
import json

import pytest
import websockets

from voicefront.events.bus import BUILD_RESULT, EventBus
from voicefront.server.reload import ReloadServer


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
async def server(bus, tmp_path):
    gen_dir = tmp_path / "generated"
    gen_dir.mkdir()
    (gen_dir / "index.html").write_text("<html><body>test</body></html>")

    srv = ReloadServer(event_bus=bus, generated_dir=str(gen_dir), ws_port=0, http_port=0)
    await srv.start_ws()

    # Get the actual port assigned
    srv.ws_port = srv._ws_server.sockets[0].getsockname()[1]

    yield srv
    await srv.stop()


async def test_ws_client_receives_reload(bus, server):
    async with websockets.connect(f"ws://localhost:{server.ws_port}") as ws:
        await asyncio.sleep(0.05)
        await bus.emit(BUILD_RESULT, {"passed": True, "errors": []})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "reload"


async def test_ws_client_receives_error(bus, server):
    async with websockets.connect(f"ws://localhost:{server.ws_port}") as ws:
        await asyncio.sleep(0.05)
        await bus.emit(BUILD_RESULT, {"passed": False, "errors": ["bad html"]})
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "error"
        assert "bad html" in msg["errors"]


async def test_multiple_ws_clients(bus, server):
    async with websockets.connect(f"ws://localhost:{server.ws_port}") as ws1:
        async with websockets.connect(f"ws://localhost:{server.ws_port}") as ws2:
            await asyncio.sleep(0.05)
            await bus.emit(BUILD_RESULT, {"passed": True, "errors": []})
            msg1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=2))
            msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=2))
            assert msg1["type"] == "reload"
            assert msg2["type"] == "reload"


async def test_transcript_callback(bus, server):
    received = []

    async def on_transcript(text):
        received.append(text)

    server.set_transcript_callback(on_transcript)

    async with websockets.connect(f"ws://localhost:{server.ws_port}") as ws:
        await ws.send(json.dumps({"type": "transcript", "text": "add a header"}))
        await asyncio.sleep(0.1)

    assert received == ["add a header"]
