import pytest

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import EventBus


class MockAgent(BaseAgent):
    def __init__(self, name, event_bus):
        super().__init__(name=name, event_bus=event_bus)
        self.received_payloads = []

    async def handle(self, payload):
        self.received_payloads.append(payload)


@pytest.fixture
def bus():
    return EventBus()


async def test_base_agent_is_abstract():
    """BaseAgent cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseAgent(name="test", event_bus=EventBus())


async def test_subclass_instantiation(bus):
    agent = MockAgent("test_agent", bus)
    assert agent.name == "test_agent"
    assert agent.event_bus is bus
    assert agent.claude_client is None


async def test_subscribe_registers_on_bus(bus):
    agent = MockAgent("test_agent", bus)
    agent.subscribe("test_event")

    await bus.emit("test_event", {"data": 42})
    assert len(agent.received_payloads) == 1
    assert agent.received_payloads[0]["data"] == 42


async def test_emit_publishes_to_bus(bus):
    received = []

    async def listener(payload):
        received.append(payload)

    bus.subscribe("output_event", listener)

    agent = MockAgent("test_agent", bus)
    await agent.emit("output_event", {"result": "ok"})

    assert len(received) == 1
    assert received[0]["result"] == "ok"


async def test_multiple_events(bus):
    agent = MockAgent("test_agent", bus)
    agent.subscribe("event_a")
    agent.subscribe("event_b")

    await bus.emit("event_a", {"type": "a"})
    await bus.emit("event_b", {"type": "b"})

    assert len(agent.received_payloads) == 2
