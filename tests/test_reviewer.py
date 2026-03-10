import json
from unittest.mock import MagicMock

import pytest

from voicefront.agents.reviewer import CodeReviewerAgent
from voicefront.events.bus import EventBus, FILE_CHANGED, REVIEW_COMPLETE, TASK_ASSIGNED


@pytest.fixture
def bus():
    return EventBus()


def make_mock_client(response_text):
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    client.messages.create.return_value = MagicMock(content=[content_block])
    return client


async def test_approved_review_emits_review_complete(bus):
    client = make_mock_client(json.dumps({"approved": True, "issues": []}))
    agent = CodeReviewerAgent(event_bus=bus, claude_client=client)

    emitted = []
    bus.subscribe(REVIEW_COMPLETE, lambda p: emitted.append(p))

    await bus.emit(FILE_CHANGED, {"path": "index.html", "before": "", "after": "<html></html>"})

    assert len(emitted) == 1
    assert emitted[0]["approved"] is True
    assert emitted[0]["issues"] == []


async def test_rejected_review_retries(bus):
    client = make_mock_client(json.dumps({"approved": False, "issues": ["Missing doctype"]}))
    agent = CodeReviewerAgent(event_bus=bus, claude_client=client)

    retried = []
    bus.subscribe(TASK_ASSIGNED, lambda p: retried.append(p))

    review_emitted = []
    bus.subscribe(REVIEW_COMPLETE, lambda p: review_emitted.append(p))

    await bus.emit(FILE_CHANGED, {"path": "test.html", "before": "", "after": "<html></html>"})

    assert len(retried) == 1
    assert "Missing doctype" in retried[0]["task"]["description"]
    assert len(review_emitted) == 0  # Should not emit review_complete on retry


async def test_max_retries_emits_not_approved(bus):
    client = make_mock_client(json.dumps({"approved": False, "issues": ["bad code"]}))
    agent = CodeReviewerAgent(event_bus=bus, claude_client=client)

    review_emitted = []
    bus.subscribe(REVIEW_COMPLETE, lambda p: review_emitted.append(p))

    # Exhaust retries (2) then one more
    await bus.emit(FILE_CHANGED, {"path": "test.html", "before": "", "after": "bad"})
    await bus.emit(FILE_CHANGED, {"path": "test.html", "before": "", "after": "bad"})
    await bus.emit(FILE_CHANGED, {"path": "test.html", "before": "", "after": "bad"})

    assert len(review_emitted) == 1
    assert review_emitted[0]["approved"] is False


async def test_malformed_response_approves(bus):
    client = make_mock_client("not json at all")
    agent = CodeReviewerAgent(event_bus=bus, claude_client=client)

    emitted = []
    bus.subscribe(REVIEW_COMPLETE, lambda p: emitted.append(p))

    await bus.emit(FILE_CHANGED, {"path": "test.html", "before": "", "after": "<html></html>"})

    assert len(emitted) == 1
    assert emitted[0]["approved"] is True
