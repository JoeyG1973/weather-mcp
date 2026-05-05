# README, LICENSE, and CHANGELOG — Design Spec

**Date:** 2026-05-05
**Status:** Approved

## Goal

The repo currently has an empty `README.md` and no `LICENSE` or `CHANGELOG`. Add the standard top-level documentation files so the project is presentable to all readers: future-self, other developers running their own copy, and voice-assistant operators wiring it into their config.

## Scope

Three new files at the repo root:
1. `README.md` (currently empty — overwrite)
2. `LICENSE` — Apache 2.0
3. `CHANGELOG.md` — Keep-a-Changelog format, with a 0.1.0 release entry dated 2026-05-05

No changes to source code, tests, or `pyproject.toml`. No CI, no contribution guide, no badges beyond two static informational ones.

## README.md

### Tone and length

Matter-of-fact, single-page, no marketing language. Code blocks for commands and config; prose for context. The reader should be able to install, run, and connect a client without leaving the file.

### Section outline

1. **Title + tagline + badges**
   - H1: `weather-mcp`
   - One-line tagline: "MCP server wrapping Open-Meteo for an LLM voice assistant."
   - Two static shields.io badges immediately under the H1, as Markdown image links:
     - `https://img.shields.io/badge/python-3.13+-blue.svg` — alt text "Python 3.13+"
     - `https://img.shields.io/badge/license-Apache%202.0-blue.svg` — alt text "License: Apache 2.0", linked to `LICENSE`

2. **Overview** (2–3 sentences)
   - What it does: exposes weather lookup as MCP tools backed by Open-Meteo.
   - Who consumes it: an LLM-driven voice assistant — the LLM uses tool output as context, not always verbatim narration.
   - Design consequence: responses are TTS-friendly prose with a local-time context prefix so the assistant can reason about freshness.

3. **Tools**
   - Small table with columns: tool, parameters, returns.
     - `get_current_weather` — `location: str` — TTS-friendly sentence with current temp, feels-like, sky, wind.
     - `get_forecast` — `location: str`, `days: int (1–14)` — TTS-friendly paragraph, one sentence per day.
   - Brief notes after the table:
     - **Disambiguation:** "Paris" alone returns a spoken list of options; "Paris, France" or "Paris, TX" picks one.
     - **Day clamping:** values outside 1–14 are clamped, and the response opens with a brief acknowledgment of the clamp.

4. **Requirements**
   - Python 3.13+
   - [`uv`](https://docs.astral.sh/uv/) (link to install instructions)
   - Internet access (Open-Meteo public API; no API key required)

5. **Install**
   ```sh
   uv sync
   ```

6. **Run**
   ```sh
   uv run weather-mcp
   ```
   - Binds `0.0.0.0:8001`, SSE transport.

7. **Connecting a client**
   - One short prose paragraph: any MCP client that supports SSE can connect by pointing at `http://<host>:8001/sse`.
   - Generic JSON snippet (illustrative — schemas vary by client):
     ```json
     {
       "mcpServers": {
         "weather": {
           "url": "http://<host>:8001/sse"
         }
       }
     }
     ```

8. **Development**
   ```sh
   uv run pytest
   ```
   - One-line note: tests use `respx` to stub Open-Meteo HTTP calls; no network is required.

9. **Deployment (systemd)**
   - Sample unit file as a fenced `ini` block:
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
   - One-line note: save as `/etc/systemd/system/weather-mcp.service`.
   - Three commands after: `systemctl daemon-reload`, `systemctl enable --now weather-mcp`, `journalctl -u weather-mcp -f`.

10. **Project layout**
    - Three bullets:
      - `main.py` — FastMCP server, tool functions, lifespan, SSE entrypoint.
      - `open_meteo.py` — HTTP I/O for geocoding and weather forecast endpoints.
      - `formatting.py` — TTS-friendly prose builders.

11. **Changelog**
    - Single line: `See [CHANGELOG.md](CHANGELOG.md).`

12. **License**
    - Single sentence: Licensed under Apache License 2.0; full text in [`LICENSE`](LICENSE).

### Out of scope (do not add)
- CI status badges (no CI configured).
- Coverage badge.
- Contribution guide.
- Architecture diagrams.
- Roadmap.

## LICENSE

- Standard Apache License 2.0 text, verbatim from <https://www.apache.org/licenses/LICENSE-2.0.txt>.
- Copyright line: `Copyright 2026 Joseph J Garcia`.
- Place at repo root as `LICENSE` (no extension).

## CHANGELOG.md

- Keep-a-Changelog 1.1.0 format.
- Header explaining the format and that the project adheres to Semantic Versioning.
- One release entry:

  ```markdown
  ## [0.1.0] - 2026-05-05
  ### Added
  - Initial release.
  - Tools: `get_current_weather`, `get_forecast` (1–14 days).
  - Open-Meteo backend with geocoding and disambiguation.
  - TTS-friendly prose output for LLM voice-assistant consumers.
  - Local-time prefix on every weather response.
  ```

- No "Unreleased" section yet (will be added on the next change).

## Acceptance criteria

- `README.md` renders cleanly on GitHub (the two badges display; all internal links — `LICENSE`, `CHANGELOG.md` — resolve).
- `LICENSE` contains the unmodified Apache 2.0 text plus the correct copyright line.
- `CHANGELOG.md` has the single 0.1.0 entry exactly as specified.
- No source-code or build-config changes.
- All three files committed in a single commit.

## Risks / open questions

None outstanding. Copyright holder confirmed as "Joseph J Garcia". Apache 2.0 license confirmed. Section structure and content confirmed with user.
