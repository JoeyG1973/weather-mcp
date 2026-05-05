# weather-mcp

MCP server wrapping Open-Meteo for an LLM voice assistant.

![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## Overview

`weather-mcp` exposes weather lookup as a pair of MCP tools backed by the public
[Open-Meteo](https://open-meteo.com/) API. The intended consumer is an LLM-driven
voice assistant: tool output is fed to the model as context, not always read aloud
verbatim. Because of that, responses are short TTS-friendly prose and each weather
response opens with the local time at the queried location, so the model can
reason about freshness ("rain this afternoon" makes no sense at 11 PM).

## Tools

| Tool | Parameters | Returns |
| --- | --- | --- |
| `get_current_weather` | `location: str` | One TTS-friendly sentence: current temperature, feels-like, sky conditions, wind. |
| `get_forecast` | `location: str`, `days: int` (1–14) | TTS-friendly paragraph, one sentence per day. |

**Disambiguation.** A bare city like `Paris` returns a spoken list of options.
Adding a qualifier — `Paris, France` or `Paris, TX` — picks one.

**Day clamping.** `days` values outside 1–14 are clamped, and the response opens
with a brief acknowledgment of the clamp.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) for environment and dependency management
- Internet access (Open-Meteo public API; no API key required)

## Install

```sh
uv sync
```

## Run

```sh
uv run weather-mcp
```

By default the server binds `0.0.0.0:8001` and speaks the SSE transport.
Override the bind with `--host` and `--port`, or with the environment
variables `WEATHER_MCP_HOST` and `WEATHER_MCP_PORT`. CLI flags take
precedence over environment variables.

## Connecting a client

Any MCP client that supports the SSE transport can connect by pointing at
`http://<host>:8001/sse`. Schemas vary by client; the snippet below shows where
the URL goes:

```json
{
  "mcpServers": {
    "weather": {
      "url": "http://<host>:8001/sse"
    }
  }
}
```

## Development

```sh
uv run pytest
```

Tests use `respx` to stub Open-Meteo HTTP calls; no network is required.

## Deployment (systemd)

Save as `/etc/systemd/system/weather-mcp.service`:

```ini
[Unit]
Description=Weather MCP server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/weather-mcp
ExecStart=/opt/weather-mcp/.venv/bin/weather-mcp
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:

```sh
systemctl daemon-reload
systemctl enable --now weather-mcp
journalctl -u weather-mcp -f
```

To bind a different address or port, set `Environment=WEATHER_MCP_HOST=...`
and/or `Environment=WEATHER_MCP_PORT=...` in the unit's `[Service]` section.

## Project layout

- `main.py` — FastMCP server, tool functions, lifespan, SSE entrypoint.
- `open_meteo.py` — HTTP I/O for Open-Meteo geocoding and forecast endpoints.
- `formatting.py` — TTS-friendly prose builders.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Licensed under the Apache License 2.0; full text in [`LICENSE`](LICENSE).
