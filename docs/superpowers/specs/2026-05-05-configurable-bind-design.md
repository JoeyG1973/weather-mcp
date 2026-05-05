# Configurable host and port — Design Spec

**Date:** 2026-05-05
**Status:** Approved

## Goal

The server currently hardcodes `host="0.0.0.0"` and `port=8001` in `main.py`.
Allow operators to override either at startup, via CLI flags or environment
variables, without changing the code. Default behavior (`0.0.0.0:8001`) is
preserved.

## Scope

- `main.py` — argument parsing and applying overrides to the FastMCP settings.
- `tests/test_main.py` — new file covering the parser and precedence rules.
- `README.md` — short note in the **Run** and **Deployment (systemd)** sections.

No changes to the Open-Meteo client, the formatting layer, or the tool
functions.

## User-facing surface

Two equivalent configuration paths, with this precedence:

```
CLI flag  >  environment variable  >  hardcoded default
```

| Setting | CLI flag | Environment variable | Default     |
| ------- | -------- | -------------------- | ----------- |
| Host    | `--host` | `WEATHER_MCP_HOST`   | `0.0.0.0`   |
| Port    | `--port` | `WEATHER_MCP_PORT`   | `8001`      |

`--help` is a free side benefit of using `argparse`.

### Examples

```sh
weather-mcp                          # 0.0.0.0:8001
weather-mcp --port 9000              # 0.0.0.0:9000
WEATHER_MCP_PORT=9000 weather-mcp    # 0.0.0.0:9000
WEATHER_MCP_HOST=127.0.0.1 weather-mcp --port 9000   # 127.0.0.1:9000
```

## Implementation

### Argument parser

A new private function in `main.py`:

```python
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; env vars supply defaults; hardcoded fallback last."""
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

Notes:
- `argv=None` lets `argparse` read `sys.argv[1:]` in production, while tests
  pass an explicit list.
- The `int(os.environ.get(...))` evaluates lazily (only when `_parse_args` is
  called) — env-var reads happen at startup, not at module import.
- A non-integer `WEATHER_MCP_PORT` raises `ValueError` at startup. Fail fast,
  no silent fallback. Misconfiguration should be loud.

### Applying the settings

The module-level `mcp = FastMCP(...)` must remain at import time, because the
`@mcp.tool(...)` decorators register against it during module load. Override
the settings inside `main()` before `mcp.run("sse")`:

```python
def main() -> None:
    args = _parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run("sse")
```

Why this is safe: FastMCP reads `self.settings.host` and `self.settings.port`
at run-time inside `run_sse_async` (`server.py:770-771, 785-786`); the library
itself mutates `settings.mount_path` the same way (`server.py:825`). The
existing `host=`/`port=` arguments to the `FastMCP(...)` constructor become
defaults that `main()` immediately overrides.

### Imports

Add `import argparse` and `import os` to the standard-library imports block in
`main.py`.

## Tests

New file `tests/test_main.py`. Each test invokes `_parse_args` directly with an
explicit `argv` list; env vars are managed via the pytest `monkeypatch`
fixture. The tests exercise the parser, not a live server — no FastMCP
spin-up.

| Test | Setup | Assert |
| --- | --- | --- |
| `test_defaults` | no env, no argv | `host == "0.0.0.0"`, `port == 8001` |
| `test_env_overrides_default_host` | `WEATHER_MCP_HOST=127.0.0.1`, no argv | `host == "127.0.0.1"` |
| `test_env_overrides_default_port` | `WEATHER_MCP_PORT=9000`, no argv | `port == 9000` |
| `test_cli_overrides_default` | no env, `--host 10.0.0.1 --port 9000` | both come from argv |
| `test_cli_overrides_env` | both env and argv set, different values | argv wins |
| `test_invalid_env_port_fails_loudly` | `WEATHER_MCP_PORT=banana`, no argv | `pytest.raises(ValueError)` |

## Documentation updates

### README — `## Run`

After the existing `uv run weather-mcp` block, add a short paragraph:

> By default the server binds `0.0.0.0:8001`. Override with `--host` and
> `--port`, or with the environment variables `WEATHER_MCP_HOST` and
> `WEATHER_MCP_PORT`. CLI flags take precedence over env vars.

### README — `## Deployment (systemd)`

Append a one-line note under the unit file:

> To change the bind address, set `Environment=WEATHER_MCP_HOST=...` and/or
> `Environment=WEATHER_MCP_PORT=...` in the unit's `[Service]` section.

### CHANGELOG.md

Add an `## [Unreleased]` section above the 0.1.0 entry:

```markdown
## [Unreleased]

### Added
- Configurable host and port via `--host`/`--port` CLI flags and
  `WEATHER_MCP_HOST`/`WEATHER_MCP_PORT` environment variables.
```

## Acceptance criteria

- `weather-mcp` with no flags or env vars still binds `0.0.0.0:8001`.
- `--port 9000` binds port 9000 regardless of env.
- `WEATHER_MCP_HOST=127.0.0.1 weather-mcp` binds 127.0.0.1.
- A non-integer `WEATHER_MCP_PORT` causes startup to fail with `ValueError`.
- All new tests pass.
- All pre-existing tests still pass.
- README and CHANGELOG updated as described.

## Out of scope

- TLS / HTTPS termination.
- Authentication.
- Multiple simultaneous binds.
- Dotenv files or any config-file format.
- Validating that the host string is a parseable IP/hostname (we let the OS
  socket layer reject bad values).
- Validating port range (the OS will reject 0 or values > 65535).
