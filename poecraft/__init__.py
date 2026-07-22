"""PoECraft — Native Linux Chaos Recipe Filter Tool for Path of Exile."""

from importlib import metadata

try:
    # Resolved from installed package metadata (pyproject.toml version).
    __version__ = metadata.version("poecraft")
except metadata.PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
