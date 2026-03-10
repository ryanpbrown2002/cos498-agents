import json
from unittest.mock import MagicMock

import pytest

from voicefront.agents.intent_parser import IntentParserAgent, Task
from voicefront.events.bus import EventBus, TASKS_PARSED, TRANSCRIPT_READY


@pytest.fixture
def bus():
    return EventBus()


def make_mock_client(response_text):
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    client.messages.create.return_value = MagicMock(content=[content_block])
    return client


async def test_subscribes_to_transcript_ready(bus):
    client = make_mock_client("[]")
    agent = IntentParserAgent(event_bus=bus, claude_client=client)
    assert agent._on_event in bus._subscribers[TRANSCRIPT_READY]


async def test_valid_json_emits_tasks(bus):
    response = json.dumps([
        {"target": "header", "action": "change_color", "value": "blue", "description": "Make header blue"},
        {"target": "sidebar", "action": "create", "value": None, "description": "Add sidebar"},
    ])
    client = make_mock_client(response)
    agent = IntentParserAgent(event_bus=bus, claude_client=client)

    emitted = []
    bus.subscribe(TASKS_PARSED, lambda p: emitted.append(p))

    await bus.emit(TRANSCRIPT_READY, {"text": "make the header blue and add a sidebar"})

    assert len(emitted) == 1
    tasks = emitted[0]["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["target"] == "header"
    assert tasks[0]["action"] == "change_color"
    assert tasks[1]["target"] == "sidebar"


async def test_invalid_json_emits_empty_tasks(bus):
    client = make_mock_client("this is not json at all")
    agent = IntentParserAgent(event_bus=bus, claude_client=client)

    emitted = []
    bus.subscribe(TASKS_PARSED, lambda p: emitted.append(p))

    await bus.emit(TRANSCRIPT_READY, {"text": "do something"})

    assert len(emitted) == 1
    assert emitted[0]["tasks"] == []


async def test_empty_transcript_emits_empty_tasks(bus):
    client = make_mock_client("[]")
    agent = IntentParserAgent(event_bus=bus, claude_client=client)

    emitted = []
    bus.subscribe(TASKS_PARSED, lambda p: emitted.append(p))

    await bus.emit(TRANSCRIPT_READY, {"text": ""})

    assert len(emitted) == 1
    assert emitted[0]["tasks"] == []
    # Should not call Claude for empty text
    client.messages.create.assert_not_called()


async def test_system_prompt_content(bus):
    client = make_mock_client("[]")
    agent = IntentParserAgent(event_bus=bus, claude_client=client)

    await bus.emit(TRANSCRIPT_READY, {"text": "add a button"})

    call_kwargs = client.messages.create.call_args
    assert "JSON array" in call_kwargs.kwargs["system"]
    assert "target" in call_kwargs.kwargs["system"]
    assert "action" in call_kwargs.kwargs["system"]
