from __future__ import annotations

import html.parser
import logging
import os
import re
import subprocess
import shutil
from typing import Any, List

from voicefront.agents.base import BaseAgent
from voicefront.events.bus import BUILD_RESULT, REVIEW_COMPLETE, EventBus

logger = logging.getLogger(__name__)


class _HTMLValidator(html.parser.HTMLParser):
    """Simple HTML validator that tracks unclosed tags."""

    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.errors: List[str] = []
        self._stack: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in self.VOID_ELEMENTS:
            self._stack.append(tag.lower())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.VOID_ELEMENTS:
            return
        if not self._stack:
            self.errors.append(f"Unexpected closing tag </{tag}> with no matching open tag")
        elif self._stack[-1] != tag:
            self.errors.append(f"Mismatched tag: expected </{self._stack[-1]}>, got </{tag}>")
            # Try to recover by popping
            if tag in self._stack:
                while self._stack and self._stack[-1] != tag:
                    self._stack.pop()
                if self._stack:
                    self._stack.pop()
        else:
            self._stack.pop()

    def finish(self):
        for tag in self._stack:
            self.errors.append(f"Unclosed tag <{tag}>")


class BuildValidator(BaseAgent):
    """Validates that generated code is parseable and free of syntax errors."""

    def __init__(self, event_bus: EventBus, generated_dir: str) -> None:
        super().__init__(name="validator", event_bus=event_bus)
        self.generated_dir = generated_dir
        self.subscribe(REVIEW_COMPLETE)

    async def handle(self, payload: dict) -> None:
        if not payload.get("approved", False):
            return

        errors = []
        errors.extend(self._validate_html())
        errors.extend(self._validate_css())
        errors.extend(self._validate_js())

        passed = len(errors) == 0
        await self.emit(BUILD_RESULT, {"passed": passed, "errors": errors})

    def _validate_html(self) -> List[str]:
        path = os.path.join(self.generated_dir, "index.html")
        if not os.path.exists(path):
            return ["index.html not found"]

        try:
            with open(path, "r") as f:
                contents = f.read()
            validator = _HTMLValidator()
            validator.feed(contents)
            validator.finish()
            return [f"HTML: {e}" for e in validator.errors]
        except Exception as e:
            return [f"HTML validation error: {e}"]

    def _validate_css(self) -> List[str]:
        path = os.path.join(self.generated_dir, "style.css")
        if not os.path.exists(path):
            return ["style.css not found"]

        try:
            with open(path, "r") as f:
                contents = f.read()
            errors = []
            # Check for balanced braces
            open_count = contents.count("{")
            close_count = contents.count("}")
            if open_count != close_count:
                errors.append(f"CSS: Unmatched braces ({open_count} open, {close_count} close)")
            return errors
        except Exception as e:
            return [f"CSS validation error: {e}"]

    def _validate_js(self) -> List[str]:
        path = os.path.join(self.generated_dir, "script.js")
        if not os.path.exists(path):
            return ["script.js not found"]

        # Try node --check if available
        if shutil.which("node"):
            try:
                result = subprocess.run(
                    ["node", "--check", path],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode != 0:
                    return [f"JS: {result.stderr.strip()}"]
                return []
            except subprocess.TimeoutExpired:
                return ["JS: validation timed out"]
            except Exception as e:
                return [f"JS validation error: {e}"]

        # Fallback: basic brace matching
        try:
            with open(path, "r") as f:
                contents = f.read()
            open_count = contents.count("{")
            close_count = contents.count("}")
            if open_count != close_count:
                return [f"JS: Unmatched braces ({open_count} open, {close_count} close)"]
            return []
        except Exception as e:
            return [f"JS validation error: {e}"]
