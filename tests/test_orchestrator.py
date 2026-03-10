import pytest

from voicefront.agents.orchestrator import Orchestrator
from voicefront.events.bus import (
    BUILD_RESULT,
    EventBus,
    REVIEW_COMPLETE,
    TASK_ASSIGNED,
    TASKS_PARSED,
)


@pytest.fixture
def bus():
    return EventBus()


async def test_tasks_parsed_emits_task_assigned(bus):
    orch = Orchestrator(event_bus=bus)

    assigned = []
    bus.subscribe(TASK_ASSIGNED, lambda p: assigned.append(p))

    await bus.emit(TASKS_PARSED, {
        "tasks": [
            {"target": "header", "action": "create", "value": None, "description": "Add header"},
            {"target": "footer", "action": "create", "value": None, "description": "Add footer"},
        ]
    })

    assert len(assigned) == 2
    assert assigned[0]["task"]["target"] == "header"
    assert assigned[1]["task"]["target"] == "footer"


async def test_status_transitions(bus):
    orch = Orchestrator(event_bus=bus)
    assert orch.get_status()["status"] == "idle"

    await bus.emit(TASKS_PARSED, {
        "tasks": [{"target": "h1", "action": "create", "value": None, "description": "test"}]
    })
    assert orch.get_status()["status"] == "processing"

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "index.html"})
    assert orch.get_status()["status"] == "idle"


async def test_empty_tasks_stays_idle(bus):
    orch = Orchestrator(event_bus=bus)

    await bus.emit(TASKS_PARSED, {"tasks": []})
    assert orch.get_status()["status"] == "idle"


async def test_build_failure_sets_error(bus):
    orch = Orchestrator(event_bus=bus)

    await bus.emit(TASKS_PARSED, {
        "tasks": [{"target": "h1", "action": "create", "value": None, "description": "test"}]
    })
    await bus.emit(BUILD_RESULT, {"passed": False, "errors": ["HTML parse error"]})
    assert orch.get_status()["status"] == "error"
