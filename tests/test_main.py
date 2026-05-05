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
