import os
from unittest.mock import MagicMock

import pytest

from voicefront.agents.writer import WriterAgent
from voicefront.events.bus import EventBus, FILE_CHANGED, TASK_ASSIGNED


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def gen_dir(tmp_path):
    d = tmp_path / "generated"
    d.mkdir()
    (d / "index.html").write_text("<html><body><h1>Hello</h1></body></html>")
    (d / "style.css").write_text("body { margin: 0; }")
    (d / "script.js").write_text("// empty")
    return str(d)


def make_mock_client(response_text):
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    client.messages.create.return_value = MagicMock(content=[content_block])
    return client


async def test_writes_file_from_claude_response(bus, gen_dir):
    new_html = "<html><body><h1>Updated</h1></body></html>"
    client = make_mock_client(new_html)
    agent = WriterAgent(event_bus=bus, claude_client=client, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(FILE_CHANGED, lambda p: emitted.append(p))

    await bus.emit(TASK_ASSIGNED, {
        "task": {"target": "header", "action": "change_text", "value": "Updated", "description": "Change header text"}
    })

    assert len(emitted) == 1
    # File should be written
    written = open(emitted[0]["path"]).read()
    assert written == new_html


async def test_emits_file_changed_with_diff(bus, gen_dir):
    client = make_mock_client("body { margin: 10px; }")
    agent = WriterAgent(event_bus=bus, claude_client=client, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(FILE_CHANGED, lambda p: emitted.append(p))

    await bus.emit(TASK_ASSIGNED, {
        "task": {"target": "style", "action": "change", "value": None, "description": "Change margin"}
    })

    assert emitted[0]["before"] == "body { margin: 0; }"
    assert emitted[0]["after"] == "body { margin: 10px; }"


async def test_reads_current_file_before_sending(bus, gen_dir):
    client = make_mock_client("<html></html>")
    agent = WriterAgent(event_bus=bus, claude_client=client, generated_dir=gen_dir)

    await bus.emit(TASK_ASSIGNED, {
        "task": {"target": "header", "action": "create", "value": None, "description": "Add header"}
    })

    call_kwargs = client.messages.create.call_args
    prompt = call_kwargs.kwargs["messages"][0]["content"]
    assert "<h1>Hello</h1>" in prompt


async def test_handles_missing_file(bus, gen_dir):
    # Remove index.html
    os.remove(os.path.join(gen_dir, "index.html"))
    client = make_mock_client("<html><body>New</body></html>")
    agent = WriterAgent(event_bus=bus, claude_client=client, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(FILE_CHANGED, lambda p: emitted.append(p))

    await bus.emit(TASK_ASSIGNED, {
        "task": {"target": "page", "action": "create", "value": None, "description": "Create page"}
    })

    assert len(emitted) == 1
    assert emitted[0]["before"] == ""
    assert os.path.exists(emitted[0]["path"])
