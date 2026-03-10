from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, List

from voicefront.agents.base import BaseAgent
from voicefront.agents.writer import WriterAgent
from voicefront.events.bus import (
    BUILD_RESULT,
    FILE_CHANGED,
    REVIEW_COMPLETE,
    TASK_ASSIGNED,
    TASKS_PARSED,
    EventBus,
)

logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    """Routes parsed tasks to Writer agents and tracks pipeline status.

    Phase 1: sequential execution with a single writer.
    Phase 2: parallel execution — tasks targeting different files run concurrently,
    tasks targeting the same file run sequentially.
    """

    STATUS_IDLE = "idle"
    STATUS_PROCESSING = "processing"
    STATUS_ERROR = "error"

    def __init__(
        self,
        event_bus: EventBus,
        writer_pool: List[WriterAgent] = None,
        parallel: bool = False,
    ) -> None:
        super().__init__(name="orchestrator", event_bus=event_bus)
        self._status = self.STATUS_IDLE
        self._pending_tasks = 0
        self._parallel = parallel
        self._writer_pool = writer_pool or []
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

        if self._parallel and len(self._writer_pool) > 1:
            await self._dispatch_parallel(tasks)
        else:
            await self._dispatch_sequential(tasks)

    async def _dispatch_sequential(self, tasks: list) -> None:
        for task in tasks:
            self.logger.info("Assigning task: %s", task.get("description", ""))
            await self.emit(TASK_ASSIGNED, {"task": task})

    async def _dispatch_parallel(self, tasks: list) -> None:
        """Group tasks by target file and run groups in parallel."""
        # Group tasks by the file they'll target
        file_groups = defaultdict(list)
        for task in tasks:
            target = task.get("target", "").lower()
            # Same heuristic as WriterAgent._resolve_file
            if any(w in target for w in ["style", "color", "font", "margin", "padding", "background"]):
                key = "style.css"
            elif any(w in target for w in ["script", "function", "event", "click", "animation"]):
                key = "script.js"
            else:
                key = "index.html"
            file_groups[key].append(task)

        self.logger.info(
            "Parallel dispatch: %d tasks across %d files",
            len(tasks), len(file_groups),
        )

        async def run_group(file_key: str, group_tasks: list) -> None:
            """Run tasks targeting the same file sequentially."""
            for task in group_tasks:
                self.logger.info("Assigning task to %s group: %s", file_key, task.get("description", ""))
                await self.emit(TASK_ASSIGNED, {"task": task})

        # Run file groups in parallel
        await asyncio.gather(
            *(run_group(k, v) for k, v in file_groups.items())
        )

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
