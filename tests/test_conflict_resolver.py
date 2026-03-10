import json
import os
from unittest.mock import MagicMock

import pytest

from voicefront.agents.conflict_resolver import ConflictResolverAgent
from voicefront.events.bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


def make_mock_client(response_text):
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    client.messages.create.return_value = MagicMock(content=[content_block])
    return client


async def test_single_change_passes_through(bus):
    resolver = ConflictResolverAgent(event_bus=bus)

    await resolver.collect({
        "path": "/tmp/test.html",
        "before": "<html></html>",
        "after": "<html><body>A</body></html>",
    })

    results = await resolver.resolve_all()
    assert len(results) == 1
    assert results[0]["after"] == "<html><body>A</body></html>"


async def test_non_overlapping_changes_use_latest(bus):
    """Sequential changes (different before states) just use the last one."""
    resolver = ConflictResolverAgent(event_bus=bus)

    await resolver.collect({
        "path": "/tmp/test.html",
        "before": "v1",
        "after": "v2",
    })
    await resolver.collect({
        "path": "/tmp/test.html",
        "before": "v2",
        "after": "v3",
    })

    results = await resolver.resolve_all()
    assert len(results) == 1
    assert results[0]["after"] == "v3"


async def test_overlapping_changes_call_claude(bus, tmp_path):
    """Parallel changes (same before state) should be merged via Claude."""
    merged_html = "<html><body><h1>Blue Header</h1><nav>Links</nav></body></html>"
    client = make_mock_client(merged_html)
    out_path = str(tmp_path / "test.html")

    resolver = ConflictResolverAgent(event_bus=bus, claude_client=client, generated_dir=str(tmp_path))

    await resolver.collect({
        "path": out_path,
        "before": "<html><body></body></html>",
        "after": "<html><body><h1>Blue Header</h1></body></html>",
    })
    await resolver.collect({
        "path": out_path,
        "before": "<html><body></body></html>",
        "after": "<html><body><nav>Links</nav></body></html>",
    })

    results = await resolver.resolve_all()
    assert len(results) == 1
    assert results[0]["after"] == merged_html
    client.messages.create.assert_called_once()


async def test_merged_output_is_written_to_file(bus, tmp_path):
    merged = "<html>merged</html>"
    client = make_mock_client(merged)
    out_path = str(tmp_path / "test.html")

    resolver = ConflictResolverAgent(event_bus=bus, claude_client=client)

    await resolver.collect({"path": out_path, "before": "orig", "after": "v1"})
    await resolver.collect({"path": out_path, "before": "orig", "after": "v2"})

    await resolver.resolve_all()
    assert open(out_path).read() == merged


async def test_no_claude_client_uses_last(bus):
    """Without a Claude client, fall back to the last change."""
    resolver = ConflictResolverAgent(event_bus=bus, claude_client=None)

    await resolver.collect({"path": "/tmp/x.html", "before": "orig", "after": "v1"})
    await resolver.collect({"path": "/tmp/x.html", "before": "orig", "after": "v2"})

    results = await resolver.resolve_all()
    assert results[0]["after"] == "v2"


async def test_multiple_files_resolved_independently(bus):
    resolver = ConflictResolverAgent(event_bus=bus)

    await resolver.collect({"path": "a.html", "before": "a", "after": "a1"})
    await resolver.collect({"path": "b.css", "before": "b", "after": "b1"})

    results = await resolver.resolve_all()
    assert len(results) == 2
    paths = [r["path"] for r in results]
    assert "a.html" in paths
    assert "b.css" in paths
