from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import FILE_CHANGED, REVIEW_COMPLETE, TASK_ASSIGNED, EventBus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a code reviewer for a voice-driven web frontend builder.
Review the provided code change for:
1. Syntax errors (unclosed tags, missing brackets, etc.)
2. Broken references (CSS classes used but not defined, JS referencing missing elements)
3. Obvious bugs or issues

Return a JSON object with:
- "approved": true if the code is acceptable, false if issues found
- "issues": array of strings describing each issue (empty array if approved)

Return ONLY the JSON object, no markdown fences, no explanation."""

MAX_RETRIES = 2


class CodeReviewerAgent(BaseAgent):
    """Reviews generated code for quality and correctness."""

    def __init__(self, event_bus: EventBus, claude_client: Any) -> None:
        super().__init__(name="reviewer", event_bus=event_bus, claude_client=claude_client)
        self._retry_counts: dict = defaultdict(int)
        self.subscribe(FILE_CHANGED)

    async def handle(self, payload: dict) -> None:
        file_path = payload.get("path", "")
        after = payload.get("after", "")

        review = await self._review_code(file_path, after)
        approved = review.get("approved", False)
        issues = review.get("issues", [])

        if not approved and self._retry_counts[file_path] < MAX_RETRIES:
            self._retry_counts[file_path] += 1
            self.logger.info("Review failed for %s (retry %d/%d): %s",
                             file_path, self._retry_counts[file_path], MAX_RETRIES, issues)
            await self.emit(TASK_ASSIGNED, {
                "task": {
                    "target": file_path,
                    "action": "fix",
                    "value": None,
                    "description": f"Fix the following issues: {'; '.join(issues)}",
                }
            })
        else:
            if approved:
                self._retry_counts.pop(file_path, None)
            else:
                self.logger.warning("Max retries reached for %s, proceeding despite issues", file_path)
                self._retry_counts.pop(file_path, None)

            await self.emit(REVIEW_COMPLETE, {
                "approved": approved,
                "issues": issues,
                "path": file_path,
            })

    async def _review_code(self, file_path: str, contents: str) -> dict:
        try:
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"File: {file_path}\n\nCode:\n{contents}"}],
            )
            raw = response.content[0].text
            return json.loads(raw)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            self.logger.error("Failed to parse review response: %s", e)
            return {"approved": True, "issues": []}
        except Exception as e:
            self.logger.error("Claude API error in reviewer: %s", e)
            return {"approved": True, "issues": []}
