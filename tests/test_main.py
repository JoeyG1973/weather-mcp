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
