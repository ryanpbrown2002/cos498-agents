from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from voicefront.events.bus import EventBus

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all VoiceFront agents."""

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        claude_client: anthropic.Anthropic | None = None,
    ) -> None:
        self.name = name
        self.event_bus = event_bus
        self.claude_client = claude_client
        self.logger = logging.getLogger(f"voicefront.agent.{name}")

    def subscribe(self, event_type: str) -> None:
        self.event_bus.subscribe(event_type, self._on_event)
        self.logger.info("Agent '%s' subscribed to '%s'", self.name, event_type)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.logger.info("Agent '%s' emitting '%s'", self.name, event_type)
        await self.event_bus.emit(event_type, payload)

    async def _on_event(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("_event_type", "unknown")
        self.logger.info("Agent '%s' received event '%s'", self.name, event_type)
        await self.handle(payload)

    @abstractmethod
    async def handle(self, payload: dict[str, Any]) -> None:
        ...
