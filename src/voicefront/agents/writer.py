from __future__ import annotations

import logging
import os
from typing import Any

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import FILE_CHANGED, TASK_ASSIGNED, EventBus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a frontend code writer for a voice-driven web builder.
You will receive a task description and the current contents of a file.
Your job is to modify the file to accomplish the task.

Rules:
- Return ONLY the complete updated file contents
- No markdown fences, no explanation, no commentary
- If the file is empty or doesn't exist, create appropriate content from scratch
- Write valid HTML, CSS, or JS depending on the file type
- Keep changes minimal and focused on the task"""


class WriterAgent(BaseAgent):
    """Generates and modifies frontend code based on tasks."""

    def __init__(self, event_bus: EventBus, claude_client: Any, generated_dir: str) -> None:
        super().__init__(name="writer", event_bus=event_bus, claude_client=claude_client)
        self.generated_dir = generated_dir
        self.subscribe(TASK_ASSIGNED)

    async def handle(self, payload: dict) -> None:
        task = payload.get("task", {})
        target = task.get("target", "")
        description = task.get("description", "")

        file_path = self._resolve_file(target)
        current_contents = self._read_file(file_path)
        new_contents = await self._generate_code(description, current_contents, file_path)

        self._write_file(file_path, new_contents)

        await self.emit(FILE_CHANGED, {
            "path": file_path,
            "before": current_contents,
            "after": new_contents,
        })

    def _resolve_file(self, target: str) -> str:
        """Determine which file to edit based on the task target."""
        # Simple heuristic: CSS-related tasks go to style.css, JS to script.js, else index.html
        target_lower = target.lower()
        if any(word in target_lower for word in ["style", "color", "font", "margin", "padding", "background"]):
            filename = "style.css"
        elif any(word in target_lower for word in ["script", "function", "event", "click", "animation"]):
            filename = "script.js"
        else:
            filename = "index.html"
        return os.path.join(self.generated_dir, filename)

    def _read_file(self, file_path: str) -> str:
        try:
            with open(file_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def _write_file(self, file_path: str, contents: str) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(contents)

    async def _generate_code(self, description: str, current_contents: str, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1]
        file_type = {".html": "HTML", ".css": "CSS", ".js": "JavaScript"}.get(ext, "text")

        prompt = f"Task: {description}\n\nCurrent {file_type} file contents:\n```\n{current_contents}\n```"

        try:
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            self.logger.error("Claude API error in writer: %s", e)
            return current_contents
