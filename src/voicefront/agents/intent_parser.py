from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import TASKS_PARSED, TRANSCRIPT_READY, EventBus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intent parser for a voice-driven frontend builder.
Given a user's spoken transcript, extract structured tasks for modifying a web frontend.

Return a JSON array of task objects. Each task has:
- "target": the UI element to modify or create (e.g., "header", "sidebar", "button", "body")
- "action": what to do (e.g., "create", "change_color", "change_text", "change_size", "remove", "move")
- "value": the value for the action if applicable (e.g., "blue", "24px", "Hello World"), or null
- "description": a brief human-readable description of the task

Return ONLY the JSON array, no markdown fences, no explanation.

Example input: "make the header blue and add a sidebar with navigation links"
Example output: [{"target": "header", "action": "change_color", "value": "blue", "description": "Change header color to blue"}, {"target": "sidebar", "action": "create", "value": "navigation links", "description": "Create a sidebar with navigation links"}]"""


@dataclass
class Task:
    target: str
    action: str
    value: Optional[str]
    description: str


class IntentParserAgent(BaseAgent):
    """Parses raw voice transcript into structured frontend tasks."""

    def __init__(self, event_bus: EventBus, claude_client: Any) -> None:
        super().__init__(name="intent_parser", event_bus=event_bus, claude_client=claude_client)
        self.subscribe(TRANSCRIPT_READY)

    async def handle(self, payload: dict) -> None:
        text = payload.get("text", "")
        if not text.strip():
            await self.emit(TASKS_PARSED, {"tasks": []})
            return

        tasks = await self._parse_transcript(text)
        await self.emit(TASKS_PARSED, {"tasks": [t.__dict__ for t in tasks]})

    async def _parse_transcript(self, text: str) -> List[Task]:
        try:
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = response.content[0].text
            parsed = json.loads(raw)
            return [
                Task(
                    target=t["target"],
                    action=t["action"],
                    value=t.get("value"),
                    description=t.get("description", ""),
                )
                for t in parsed
            ]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            self.logger.error("Failed to parse Claude response: %s", e)
            return []
        except Exception as e:
            self.logger.error("Claude API error: %s", e)
            return []
