"""Tests for poecraft.config — config loading and example validation."""

from __future__ import annotations

from pathlib import Path

from poecraft.config import Config, load_config

_EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.yaml"


def test_example_yaml_loads_into_config() -> None:
    """The shipped config.example.yaml must parse cleanly into Config."""
    config = load_config(_EXAMPLE)
    assert isinstance(config, Config)


def test_config_has_client_log_path_default_empty() -> None:
    assert Config().client_log_path == ""


def test_example_yaml_exposes_client_log_path_field() -> None:
    config = load_config(_EXAMPLE)
    # The example documents the field; default is empty (auto-discover).
    assert hasattr(config, "client_log_path")
    assert config.client_log_path == ""
