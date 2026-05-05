"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture by filename (without extension allowed)."""
    fname = name if name.endswith(".json") else f"{name}.json"
    return json.loads((FIXTURES_DIR / fname).read_text())


@pytest.fixture
def fixture():
    """Return the load_fixture helper as a fixture."""
    return load_fixture


@pytest.fixture
async def http_client():
    """A real httpx.AsyncClient for tests that mock at the transport layer with respx."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client
