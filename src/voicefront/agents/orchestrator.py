from __future__ import annotations

import logging
from typing import Any

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import (
    BUILD_RESULT,
    REVIEW_COMPLETE,
    TASK_ASSIGNED,
    TASKS_PARSED,
    EventBus,
)

logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    """Routes parsed tasks to Writer agents and tracks pipeline status."""

    STATUS_IDLE = "idle"
    STATUS_PROCESSING = "processing"
    STATUS_ERROR = "error"

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(name="orchestrator", event_bus=event_bus)
        self._status = self.STATUS_IDLE
        self._pending_tasks = 0
        self.subscribe(TASKS_PARSED)
        self.subscribe(REVIEW_COMPLETE)
        self.subscribe(BUILD_RESULT)

    def get_status(self) -> dict:
        return {
            "status": self._status,
            "pending_tasks": self._pending_tasks,
        }

    async def handle(self, payload: dict) -> None:
        if "tasks" in payload:
            await self._handle_tasks_parsed(payload)
        elif "approved" in payload:
            await self._handle_review_complete(payload)
        elif "passed" in payload:
            await self._handle_build_result(payload)

    async def _handle_tasks_parsed(self, payload: dict) -> None:
        tasks = payload.get("tasks", [])
        if not tasks:
            self.logger.info("No tasks to process")
            return

        self._status = self.STATUS_PROCESSING
        self._pending_tasks = len(tasks)

        for task in tasks:
            self.logger.info("Assigning task: %s", task.get("description", ""))
            await self.emit(TASK_ASSIGNED, {"task": task})

    async def _handle_review_complete(self, payload: dict) -> None:
        self._pending_tasks = max(0, self._pending_tasks - 1)

        if payload.get("approved"):
            self.logger.info("Review approved for %s", payload.get("path", ""))
        else:
            self.logger.warning("Review not approved: %s", payload.get("issues", []))

        if self._pending_tasks == 0:
            self._status = self.STATUS_IDLE
            self.logger.info("All tasks complete")

    async def _handle_build_result(self, payload: dict) -> None:
        if payload.get("passed"):
            self.logger.info("Build passed")
        else:
            self.logger.warning("Build failed: %s", payload.get("errors", []))
            self._status = self.STATUS_ERROR
