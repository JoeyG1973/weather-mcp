# Contributing

Thanks for your interest in contributing to `weather-mcp`.

## Development setup

```sh
git clone https://github.com/JoeyG1973/weather-mcp.git
cd weather-mcp
uv sync
uv run pytest
```

Tests stub Open-Meteo HTTP calls with `respx`; no network access is required.

## Pull requests

- Keep changes focused: one feature or fix per PR.
- Add or update tests when behavior changes.
- Run `uv run pytest` before submitting.
- Note user-visible changes in `CHANGELOG.md` under the `[Unreleased]` section.

## Reporting bugs and requesting features

Use the issue templates linked from the repository's **Issues** tab.

## Security

Do not file public issues for security vulnerabilities. See
[`SECURITY.md`](SECURITY.md) for the private reporting process.
