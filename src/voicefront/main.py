from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import anthropic
from dotenv import load_dotenv

from voicefront.agents.intent_parser import IntentParserAgent
from voicefront.agents.orchestrator import Orchestrator
from voicefront.agents.reviewer import CodeReviewerAgent
from voicefront.agents.validator import BuildValidator
from voicefront.agents.writer import WriterAgent
from voicefront.events.bus import TRANSCRIPT_READY, EventBus
from voicefront.server.reload import ReloadServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voicefront")


def get_generated_dir() -> str:
    """Resolve the generated/ directory path."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")


async def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    generated_dir = get_generated_dir()
    logger.info("Generated files directory: %s", generated_dir)

    # Core components
    event_bus = EventBus()
    client = anthropic.Anthropic(api_key=api_key)

    # Agents
    intent_parser = IntentParserAgent(event_bus=event_bus, claude_client=client)
    orchestrator = Orchestrator(event_bus=event_bus)
    writer = WriterAgent(event_bus=event_bus, claude_client=client, generated_dir=generated_dir)
    reviewer = CodeReviewerAgent(event_bus=event_bus, claude_client=client)
    validator = BuildValidator(event_bus=event_bus, generated_dir=generated_dir)

    # Server
    server = ReloadServer(
        event_bus=event_bus,
        generated_dir=generated_dir,
        ws_port=8765,
        http_port=8080,
    )

    # Wire transcript messages from browser -> event bus
    async def on_transcript(text: str) -> None:
        logger.info("Received transcript: %s", text)
        await event_bus.emit(TRANSCRIPT_READY, {"text": text})

    server.set_transcript_callback(on_transcript)

    # Start servers
    await server.start_ws()
    await server.start_http()

    logger.info("=" * 50)
    logger.info("VoiceFront is running!")
    logger.info("Open http://localhost:8080 in Chrome")
    logger.info("Speak to build your frontend")
    logger.info("=" * 50)

    # Wait for shutdown
    stop = asyncio.Event()

    def handle_signal():
        logger.info("Shutting down...")
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await stop.wait()
    await server.stop()
    logger.info("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
