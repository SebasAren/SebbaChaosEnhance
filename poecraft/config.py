"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class Config(BaseModel):
    """PoECraft configuration."""

    # PoE Account
    account_name: str = ""
    league: str = "Standard"
    session_id: str = ""

    # Stash tabs to scan (0-based indices)
    stash_tabs: list[int] = Field(default_factory=list)

    # Recipe settings
    recipe_type: Literal["chaos", "regal", "chance", "exalted"] = "chaos"
    set_threshold: int = 5
    include_identified: bool = False

    # Loot filter
    loot_filter_path: str = ""

    # Path to PoE Client.txt log (empty => auto-discover Steam install)
    client_log_path: str = ""

    # Server
    host: str = "127.0.0.1"
    port: int = 8420

    # Auto-refresh interval in seconds (0 = manual only)
    refresh_interval: int = 30


_config: Config | None = None


def get_config_path() -> Path:
    """Get config file path from env or default location."""
    env_path = os.environ.get("POECRAFT_CONFIG")
    if env_path:
        return Path(env_path)
    return Path.home() / ".config" / "poecraft" / "config.yaml"


def load_config(path: Path | str | None = None) -> Config:
    """Load config from YAML file. Returns defaults if file doesn't exist."""
    global _config

    if path is None:
        path = get_config_path()
    else:
        path = Path(path)

    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        _config = Config(**raw)
    else:
        _config = Config()

    return _config


def get_config() -> Config:
    """Get the loaded config singleton. Loads from default path if not yet loaded."""
    global _config
    if _config is None:
        return load_config()
    return _config


def save_config(config: Config, path: Path | str | None = None) -> None:
    """Save config to YAML file."""
    global _config
    _config = config

    if path is None:
        path = get_config_path()
    else:
        path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)
