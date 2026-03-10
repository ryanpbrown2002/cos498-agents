from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import FILE_CHANGED, EventBus

logger = logging.getLogger(__name__)

MERGE_SYSTEM_PROMPT = """You are a code merge tool. You receive two versions of the same file
that were modified independently by different agents. Merge them into a single coherent version
that preserves the intent of both changes.

Rules:
- Return ONLY the merged file contents
- No markdown fences, no explanation
- Preserve all changes from both versions where possible
- If changes truly conflict (modify the same element differently), prefer the version
  that seems more complete or correct"""


class ConflictResolverAgent(BaseAgent):
    """Detects and resolves conflicts when parallel writers modify related files.

    Collects FILE_CHANGED events within a batch window. If multiple changes
    target the same file, merges them — automatically for non-overlapping changes,
    via Claude for true conflicts.
    """

    def __init__(self, event_bus: EventBus, claude_client: Any = None, generated_dir: str = "") -> None:
        super().__init__(name="conflict_resolver", event_bus=event_bus, claude_client=claude_client)
        self.generated_dir = generated_dir
        self._pending_changes: Dict[str, List[dict]] = {}

    async def collect(self, payload: dict) -> None:
        """Collect a file change for potential conflict resolution."""
        path = payload.get("path", "")
        if path not in self._pending_changes:
            self._pending_changes[path] = []
        self._pending_changes[path].append(payload)

    async def resolve_all(self) -> List[dict]:
        """Resolve all pending changes and return the final file_changed events."""
        results = []
        for path, changes in self._pending_changes.items():
            if len(changes) <= 1:
                # No conflict, pass through
                results.extend(changes)
            else:
                merged = await self._merge_changes(path, changes)
                results.append(merged)
        self._pending_changes.clear()
        return results

    async def _merge_changes(self, path: str, changes: List[dict]) -> dict:
        """Merge multiple changes to the same file."""
        # Check if changes are non-overlapping (different before states mean sequential,
        # same before state means parallel divergence)
        before_states = set(c.get("before", "") for c in changes)

        if len(before_states) > 1:
            # Changes were sequential (each saw a different before state)
            # The last change already incorporates prior ones — just use it
            self.logger.info("Non-overlapping sequential changes to %s, using latest", path)
            return changes[-1]

        # True parallel conflict — same starting point, different results
        self.logger.info("Parallel conflict detected on %s, merging via Claude", path)
        return await self._claude_merge(path, changes)

    async def _claude_merge(self, path: str, changes: List[dict]) -> dict:
        """Use Claude to merge conflicting file versions."""
        if not self.claude_client:
            self.logger.warning("No Claude client for merge, using last change")
            return changes[-1]

        versions = "\n\n---\n\n".join(
            f"Version {i+1}:\n{c.get('after', '')}"
            for i, c in enumerate(changes)
        )
        original = changes[0].get("before", "")

        prompt = f"Original file:\n{original}\n\nModified versions to merge:\n{versions}"

        try:
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=MERGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            merged_content = response.content[0].text

            # Write merged result
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(merged_content)

            return {
                "path": path,
                "before": original,
                "after": merged_content,
            }
        except Exception as e:
            self.logger.error("Claude merge failed: %s", e)
            return changes[-1]

    async def handle(self, payload: dict) -> None:
        """Not used directly — this agent is driven by collect/resolve_all."""
        pass
