from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Union

logger = logging.getLogger(__name__)

# Event type constants
TRANSCRIPT_READY = "transcript_ready"
TASKS_PARSED = "tasks_parsed"
TASK_ASSIGNED = "task_assigned"
FILE_CHANGED = "file_changed"
REVIEW_COMPLETE = "review_complete"
BUILD_RESULT = "build_result"

Callback = Union[Callable[[dict], None], Callable[[dict], Coroutine]]


class EventBus:
    """Lightweight in-process pub/sub event system for agent communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callback) -> None:
        self._subscribers[event_type].append(callback)
        logger.debug("Subscribed %s to '%s'", callback, event_type)

    def unsubscribe(self, event_type: str, callback: Callback) -> None:
        try:
            self._subscribers[event_type].remove(callback)
            logger.debug("Unsubscribed %s from '%s'", callback, event_type)
        except ValueError:
            pass

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.debug("Emitting '%s' with payload keys: %s", event_type, list(payload.keys()))
        for callback in self._subscribers[event_type]:
            result = callback(payload)
            if asyncio.iscoroutine(result):
                await result
