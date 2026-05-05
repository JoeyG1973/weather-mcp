# Configurable Host and Port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `0.0.0.0:8001` bind in `main.py` with values resolvable from CLI flags (`--host`, `--port`), environment variables (`WEATHER_MCP_HOST`, `WEATHER_MCP_PORT`), or the existing default — in that precedence order.

**Architecture:** A new private `_parse_args(argv)` returns an `argparse.Namespace` whose defaults are pulled from the environment. A new private `_apply_bind_settings(mcp, args)` mutates `mcp.settings.host` and `mcp.settings.port` before the server runs. The module-level `FastMCP` instance stays where it is so the existing `@mcp.tool(...)` decorators register at import time; `main()` calls the two helpers, then `mcp.run("sse")`.

**Tech Stack:** Python 3.13, stdlib `argparse` and `os`, existing `mcp.server.fastmcp.FastMCP`, `pytest` with `monkeypatch`.

**Spec:** [`docs/superpowers/specs/2026-05-05-configurable-bind-design.md`](../specs/2026-05-05-configurable-bind-design.md)

---

## File map

- **Modify** `main.py`
  - Add `import argparse` and `import os` to the stdlib imports block.
  - Add `_parse_args` and `_apply_bind_settings` private helpers near the bottom (above `main`).
  - Update `main()` to call both before `mcp.run("sse")`.
  - Update the module docstring (line 4) to drop the "port 8001" claim — it's no longer fixed.
- **Create** `tests/test_main.py` covering the two helpers.
- **Modify** `README.md` — short notes in the **Run** and **Deployment (systemd)** sections.
- **Modify** `CHANGELOG.md` — add an `## [Unreleased]` section above the 0.1.0 entry.

---

## Task 1: Add `_parse_args` with full precedence behavior

**Files:**
- Create: `tests/test_main.py`
- Modify: `main.py:8-15` (stdlib imports), append helpers above `def main()` at line 281

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py` with this exact content:

```python
"""Tests for argument parsing and bind-setting helpers in main.py."""
from __future__ import annotations

import pytest

from main import _parse_args


def test_defaults_when_no_env_no_argv(monkeypatch):
    monkeypatch.delenv("WEATHER_MCP_HOST", raising=False)
    monkeypatch.delenv("WEATHER_MCP_PORT", raising=False)
    args = _parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 8001


def test_env_host_overrides_default(monkeypatch):
    monkeypatch.setenv("WEATHER_MCP_HOST", "127.0.0.1")
    monkeypatch.delenv("WEATHER_MCP_PORT", raising=False)
    args = _parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8001


def test_env_port_overrides_default(monkeypatch):
    monkeypatch.delenv("WEATHER_MCP_HOST", raising=False)
    monkeypatch.setenv("WEATHER_MCP_PORT", "9000")
    args = _parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_cli_overrides_default(monkeypatch):
    monkeypatch.delenv("WEATHER_MCP_HOST", raising=False)
    monkeypatch.delenv("WEATHER_MCP_PORT", raising=False)
    args = _parse_args(["--host", "10.0.0.1", "--port", "9000"])
    assert args.host == "10.0.0.1"
    assert args.port == 9000


def test_cli_overrides_env(monkeypatch):
    monkeypatch.setenv("WEATHER_MCP_HOST", "192.168.1.1")
    monkeypatch.setenv("WEATHER_MCP_PORT", "7000")
    args = _parse_args(["--host", "10.0.0.1", "--port", "9000"])
    assert args.host == "10.0.0.1"
    assert args.port == 9000


def test_invalid_env_port_fails_loudly(monkeypatch):
    monkeypatch.setenv("WEATHER_MCP_PORT", "banana")
    with pytest.raises(ValueError):
        _parse_args([])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/weather-mcp && uv run pytest tests/test_main.py -v`

Expected: All six tests fail at collection or import with `ImportError: cannot import name '_parse_args' from 'main'` (or similar). This confirms the helper does not exist yet.

- [ ] **Step 3: Add imports to `main.py`**

Edit the stdlib imports block at `main.py:8-15`. Add `import argparse` and `import os` so the block becomes:

```python
# ---------------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------------
import argparse
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone as _utc
from typing import AsyncIterator, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
```

- [ ] **Step 4: Implement `_parse_args` in `main.py`**

Insert this block immediately above `def main() -> None:` (around line 281). Keep one blank line between this block and the existing entrypoint.

```python
# ---------------------------------------------------------------------------
# CLI / environment configuration
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; env vars supply defaults; hardcoded fallback last.

    Precedence: CLI flag > environment variable > hardcoded default.
    A non-integer WEATHER_MCP_PORT raises ValueError at startup — fail fast,
    no silent fallback.
    """
    parser = argparse.ArgumentParser(prog="weather-mcp")
    parser.add_argument(
        "--host",
        default=os.environ.get("WEATHER_MCP_HOST", "0.0.0.0"),
        help="Bind address (env: WEATHER_MCP_HOST). Default: 0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WEATHER_MCP_PORT", "8001")),
        help="Bind port (env: WEATHER_MCP_PORT). Default: 8001",
    )
    return parser.parse_args(argv)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /opt/weather-mcp && uv run pytest tests/test_main.py -v`

Expected: All six tests PASS.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `cd /opt/weather-mcp && uv run pytest -v`

Expected: All previously-passing tests still pass; the six new ones pass too.

- [ ] **Step 7: Commit**

```bash
git -C /opt/weather-mcp add main.py tests/test_main.py
git -C /opt/weather-mcp commit -m "$(cat <<'EOF'
feat: parse host and port from argv and environment

CLI flags --host/--port override WEATHER_MCP_HOST/WEATHER_MCP_PORT,
which override the existing 0.0.0.0:8001 default. Invalid env-var
ports fail loudly at startup with ValueError.
EOF
)"
```

---

## Task 2: Apply parsed bind settings to the FastMCP instance

**Files:**
- Modify: `tests/test_main.py` (add tests at end)
- Modify: `main.py` — add `_apply_bind_settings`, update `main()` to call it

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`:

```python
from mcp.server.fastmcp import FastMCP

from main import _apply_bind_settings


def test_apply_bind_settings_sets_host_and_port():
    mcp = FastMCP("test-server", host="0.0.0.0", port=8001)
    args = _parse_args(["--host", "10.0.0.1", "--port", "9000"])
    _apply_bind_settings(mcp, args)
    assert mcp.settings.host == "10.0.0.1"
    assert mcp.settings.port == 9000


def test_apply_bind_settings_with_defaults_keeps_module_defaults(monkeypatch):
    monkeypatch.delenv("WEATHER_MCP_HOST", raising=False)
    monkeypatch.delenv("WEATHER_MCP_PORT", raising=False)
    mcp = FastMCP("test-server", host="9.9.9.9", port=1234)
    args = _parse_args([])
    _apply_bind_settings(mcp, args)
    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 8001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/weather-mcp && uv run pytest tests/test_main.py -v`

Expected: The two new tests fail with `ImportError: cannot import name '_apply_bind_settings' from 'main'`. The six earlier tests still pass.

- [ ] **Step 3: Implement `_apply_bind_settings` in `main.py`**

Add this function immediately below `_parse_args` (before `def main()`):

```python
def _apply_bind_settings(mcp: FastMCP, args: argparse.Namespace) -> None:
    """Override the FastMCP instance's bind host and port from parsed args.

    FastMCP reads `settings.host` and `settings.port` at run-time inside
    `run_sse_async`, so mutating them after construction is safe. The library
    itself uses this pattern (see `settings.mount_path`).
    """
    mcp.settings.host = args.host
    mcp.settings.port = args.port
```

- [ ] **Step 4: Update `main()` to wire the helpers**

Replace the existing `main()` body at `main.py:281-282`:

```python
def main() -> None:
    args = _parse_args()
    _apply_bind_settings(mcp, args)
    mcp.run("sse")
```

- [ ] **Step 5: Update the stale module docstring**

Edit `main.py:1-5`. Replace the docstring with:

```python
"""Weather MCP server: tool functions, lifespan, and SSE entrypoint.

This module wires the MCP tools to the Open-Meteo I/O layer and the prose
formatting layer, then exposes them via a FastMCP SSE server. Bind host
and port are configurable; see _parse_args.
"""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /opt/weather-mcp && uv run pytest tests/test_main.py -v`

Expected: All eight tests in `test_main.py` pass.

- [ ] **Step 7: Run the full test suite**

Run: `cd /opt/weather-mcp && uv run pytest -v`

Expected: Everything passes.

- [ ] **Step 8: Smoke-test the binary with a non-default port**

Run: `cd /opt/weather-mcp && WEATHER_MCP_PORT=9099 uv run weather-mcp &`

Expected: Server logs say it is listening on `0.0.0.0:9099` (or equivalent uvicorn output). Confirm with:

```bash
sleep 1 && curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9099/sse --max-time 1 || true
```

Expected: A non-zero HTTP status (200 or otherwise) — anything other than `Connection refused` proves the bind worked.

Stop the background server: `kill %1` (or `pkill -f weather-mcp`).

- [ ] **Step 9: Commit**

```bash
git -C /opt/weather-mcp add main.py tests/test_main.py
git -C /opt/weather-mcp commit -m "$(cat <<'EOF'
feat: apply parsed host and port to the FastMCP instance at startup

main() now reads CLI flags and env vars via _parse_args, then mutates
mcp.settings before mcp.run("sse"). The module-level FastMCP instance
remains so @mcp.tool decorators still register at import.
EOF
)"
```

---

## Task 3: Document the new options in README

**Files:**
- Modify: `README.md` (Run section and Deployment section)

- [ ] **Step 1: Update the Run section**

Find the Run section (begins with `## Run`) in `README.md`. After the existing `uv run weather-mcp` fenced block and the line `The server binds 0.0.0.0:8001 and speaks the SSE transport.`, append:

```markdown

By default the server binds `0.0.0.0:8001`. Override with `--host` and
`--port`, or with the environment variables `WEATHER_MCP_HOST` and
`WEATHER_MCP_PORT`. CLI flags take precedence over environment variables.
```

- [ ] **Step 2: Update the Deployment (systemd) section**

In the Deployment (systemd) section, after the `journalctl -u weather-mcp -f` block, append:

```markdown

To bind a different address or port, set `Environment=WEATHER_MCP_HOST=...`
and/or `Environment=WEATHER_MCP_PORT=...` in the unit's `[Service]` section.
```

- [ ] **Step 3: Verify the file still looks right**

Run: `grep -nE 'WEATHER_MCP_(HOST|PORT)' /opt/weather-mcp/README.md`

Expected: At least three matches — one in the Run paragraph, two in the systemd note.

- [ ] **Step 4: Commit**

```bash
git -C /opt/weather-mcp add README.md
git -C /opt/weather-mcp commit -m "$(cat <<'EOF'
docs: README notes on configurable bind via flags and env vars
EOF
)"
```

---

## Task 4: Add an Unreleased CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Insert the Unreleased section**

In `CHANGELOG.md`, insert this block immediately above the `## [0.1.0] - 2026-05-05` heading. Leave one blank line between this block and the 0.1.0 heading.

```markdown
## [Unreleased]

### Added

- Configurable host and port via `--host`/`--port` CLI flags and
  `WEATHER_MCP_HOST`/`WEATHER_MCP_PORT` environment variables.
```

- [ ] **Step 2: Verify the file**

Run: `head -20 /opt/weather-mcp/CHANGELOG.md`

Expected: The header, then the new `## [Unreleased]` block, then the existing `## [0.1.0]` block.

- [ ] **Step 3: Commit**

```bash
git -C /opt/weather-mcp add CHANGELOG.md
git -C /opt/weather-mcp commit -m "$(cat <<'EOF'
docs: changelog entry for configurable host and port
EOF
)"
```

---

## Final verification

- [ ] **Step 1: Full test suite from a clean state**

Run: `cd /opt/weather-mcp && uv run pytest -v`

Expected: All tests pass, including the eight in `tests/test_main.py`.

- [ ] **Step 2: Default-bind smoke test**

Run: `cd /opt/weather-mcp && uv run weather-mcp &` then `sleep 1 && curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/sse --max-time 1 || true`

Expected: A non-zero HTTP status (proves default 8001 still works). Stop with `kill %1`.

- [ ] **Step 3: CLI-override smoke test**

Run: `cd /opt/weather-mcp && uv run weather-mcp --port 9099 &` then `sleep 1 && curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9099/sse --max-time 1 || true`

Expected: Non-zero HTTP status. Stop with `kill %1`.

- [ ] **Step 4: Loud-failure smoke test**

Run: `cd /opt/weather-mcp && WEATHER_MCP_PORT=banana uv run weather-mcp; echo "exit=$?"`

Expected: Process exits non-zero with a `ValueError` traceback mentioning `'banana'`.

- [ ] **Step 5: Confirm git history**

Run: `git -C /opt/weather-mcp log --oneline -6`

Expected (top to bottom):
- `docs: changelog entry for configurable host and port`
- `docs: README notes on configurable bind via flags and env vars`
- `feat: apply parsed host and port to the FastMCP instance at startup`
- `feat: parse host and port from argv and environment`
- `docs: design spec for configurable host and port`
- (older commits)
