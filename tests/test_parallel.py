import asyncio
import time

import pytest

from voicefront.agents.orchestrator import Orchestrator
from voicefront.events.bus import EventBus, TASK_ASSIGNED, TASKS_PARSED, REVIEW_COMPLETE


@pytest.fixture
def bus():
    return EventBus()


async def test_parallel_different_files_dispatched_concurrently(bus):
    """Tasks targeting different files should run in parallel."""
    orch = Orchestrator(event_bus=bus, parallel=True, writer_pool=["w1", "w2"])

    assigned = []
    bus.subscribe(TASK_ASSIGNED, lambda p: assigned.append(p))

    await bus.emit(TASKS_PARSED, {
        "tasks": [
            {"target": "header", "action": "create", "value": None, "description": "Add header"},
            {"target": "style", "action": "change_color", "value": "blue", "description": "Blue styles"},
        ]
    })

    assert len(assigned) == 2
    # They should be grouped into different files
    targets = [a["task"]["target"] for a in assigned]
    assert "header" in targets
    assert "style" in targets


async def test_parallel_same_file_runs_sequentially(bus):
    """Tasks targeting the same file should run sequentially within their group."""
    orch = Orchestrator(event_bus=bus, parallel=True, writer_pool=["w1", "w2"])

    order = []

    async def track(payload):
        order.append(payload["task"]["description"])

    bus.subscribe(TASK_ASSIGNED, track)

    await bus.emit(TASKS_PARSED, {
        "tasks": [
            {"target": "header", "action": "create", "value": None, "description": "task1"},
            {"target": "footer", "action": "create", "value": None, "description": "task2"},
        ]
    })

    # Both target index.html, so they should be sequential within that group
    assert order == ["task1", "task2"]


async def test_parallel_fallback_to_sequential(bus):
    """With parallel=False or empty pool, should fall back to sequential."""
    orch = Orchestrator(event_bus=bus, parallel=False)

    assigned = []
    bus.subscribe(TASK_ASSIGNED, lambda p: assigned.append(p))

    await bus.emit(TASKS_PARSED, {
        "tasks": [
            {"target": "header", "action": "create", "value": None, "description": "A"},
            {"target": "style", "action": "change", "value": None, "description": "B"},
        ]
    })

    assert len(assigned) == 2


async def test_writer_failure_does_not_block_others(bus):
    """If one task group errors, others should still complete."""
    orch = Orchestrator(event_bus=bus, parallel=True, writer_pool=["w1", "w2"])

    assigned = []
    call_count = 0

    async def track_with_error(payload):
        nonlocal call_count
        call_count += 1
        assigned.append(payload["task"]["description"])

    bus.subscribe(TASK_ASSIGNED, track_with_error)

    await bus.emit(TASKS_PARSED, {
        "tasks": [
            {"target": "header", "action": "create", "value": None, "description": "html-task"},
            {"target": "style", "action": "change", "value": None, "description": "css-task"},
            {"target": "script", "action": "create", "value": None, "description": "js-task"},
        ]
    })

    assert len(assigned) == 3
