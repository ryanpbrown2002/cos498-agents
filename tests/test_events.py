import pytest

from voicefront.events.bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


async def test_subscribe_and_emit(bus):
    received = []

    async def callback(payload):
        received.append(payload)

    bus.subscribe("test_event", callback)
    await bus.emit("test_event", {"key": "value"})

    assert len(received) == 1
    assert received[0] == {"key": "value"}


async def test_multiple_subscribers(bus):
    results_a = []
    results_b = []

    async def callback_a(payload):
        results_a.append(payload)

    async def callback_b(payload):
        results_b.append(payload)

    bus.subscribe("test_event", callback_a)
    bus.subscribe("test_event", callback_b)
    await bus.emit("test_event", {"data": 1})

    assert len(results_a) == 1
    assert len(results_b) == 1


async def test_unsubscribe(bus):
    received = []

    async def callback(payload):
        received.append(payload)

    bus.subscribe("test_event", callback)
    bus.unsubscribe("test_event", callback)
    await bus.emit("test_event", {"data": 1})

    assert len(received) == 0


async def test_unsubscribe_nonexistent(bus):
    """Unsubscribing a callback that was never subscribed should not error."""

    async def callback(payload):
        pass

    bus.unsubscribe("test_event", callback)  # should not raise


async def test_emit_no_subscribers(bus):
    """Emitting with no subscribers should not error."""
    await bus.emit("no_one_listening", {"data": 1})


async def test_sync_callback(bus):
    received = []

    def callback(payload):
        received.append(payload)

    bus.subscribe("test_event", callback)
    await bus.emit("test_event", {"key": "sync"})

    assert len(received) == 1
    assert received[0] == {"key": "sync"}


async def test_async_callback_is_awaited(bus):
    """Verify that async callbacks are properly awaited."""
    order = []

    async def slow_callback(payload):
        order.append("start")
        # If this were not awaited, "end" would appear before "start"
        order.append("end")

    bus.subscribe("test_event", slow_callback)
    await bus.emit("test_event", {})

    assert order == ["start", "end"]
