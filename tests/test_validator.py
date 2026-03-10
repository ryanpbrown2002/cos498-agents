import os

import pytest

from voicefront.agents.validator import BuildValidator
from voicefront.events.bus import BUILD_RESULT, EventBus, REVIEW_COMPLETE


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def gen_dir(tmp_path):
    d = tmp_path / "generated"
    d.mkdir()
    (d / "index.html").write_text("<!DOCTYPE html><html><head></head><body><h1>Hi</h1></body></html>")
    (d / "style.css").write_text("body { margin: 0; }")
    (d / "script.js").write_text("// valid js\n")
    return str(d)


async def test_valid_files_pass(bus, gen_dir):
    validator = BuildValidator(event_bus=bus, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "index.html"})

    assert len(emitted) == 1
    assert emitted[0]["passed"] is True
    assert emitted[0]["errors"] == []


async def test_unclosed_html_tag_fails(bus, gen_dir):
    (open(os.path.join(gen_dir, "index.html"), "w")).write("<html><body><div></body></html>")
    validator = BuildValidator(event_bus=bus, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "index.html"})

    assert emitted[0]["passed"] is False
    assert any("HTML" in e for e in emitted[0]["errors"])


async def test_unmatched_css_braces_fails(bus, gen_dir):
    with open(os.path.join(gen_dir, "style.css"), "w") as f:
        f.write("body { margin: 0; ")  # missing closing brace
    validator = BuildValidator(event_bus=bus, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "style.css"})

    assert emitted[0]["passed"] is False
    assert any("CSS" in e for e in emitted[0]["errors"])


async def test_js_syntax_error_fails(bus, gen_dir):
    with open(os.path.join(gen_dir, "script.js"), "w") as f:
        f.write("function { broken")
    validator = BuildValidator(event_bus=bus, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "script.js"})

    assert emitted[0]["passed"] is False
    assert any("JS" in e for e in emitted[0]["errors"])


async def test_missing_files_reported(bus, tmp_path):
    empty_dir = str(tmp_path / "empty")
    os.makedirs(empty_dir)
    validator = BuildValidator(event_bus=bus, generated_dir=empty_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": True, "issues": [], "path": "index.html"})

    assert emitted[0]["passed"] is False
    assert len(emitted[0]["errors"]) == 3  # all 3 files missing


async def test_unapproved_review_skipped(bus, gen_dir):
    validator = BuildValidator(event_bus=bus, generated_dir=gen_dir)

    emitted = []
    bus.subscribe(BUILD_RESULT, lambda p: emitted.append(p))

    await bus.emit(REVIEW_COMPLETE, {"approved": False, "issues": ["bad"], "path": "index.html"})

    assert len(emitted) == 0  # should not validate unapproved code
