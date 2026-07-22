"""Client.txt zone-change watcher.

Tails the PoE Client.txt log and fires a callback on zone-change lines.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence

# Matches: [INFO Client <pid>] : You have entered <Area Name>.
_ZONE_CHANGE_RE = re.compile(
    r"\[INFO Client \d+\] : You have entered (?P<area>.+)\.$"
)

# Relative location of the PoE Client.txt inside a Steam install.
_CLIENT_LOG_REL = Path("steamapps") / "common" / "Path of Exile" / "logs" / "Client.txt"

# Common Steam install roots (Linux). Injectable for tests.
_DEFAULT_STEAM_ROOTS = (
    Path.home() / ".local" / "share" / "Steam",
    Path.home() / ".steam" / "steam",
)


class _LogConfig(Protocol):
    """Structural type for the config resolve_log_path reads."""

    client_log_path: str


def parse_zone_change(line: str) -> str | None:
    """Return the area name if ``line`` is a zone-change line, else ``None``."""
    match = _ZONE_CHANGE_RE.search(line)
    if match is None:
        return None
    return match.group("area")


def default_log_path(roots: Sequence[Path] | None = None) -> Path | None:
    """Return the Client.txt path under the first matching Steam root, else None.

    ``roots`` defaults to common Steam install locations; injectable for tests.
    Only paths that exist on disk are returned.
    """
    candidates = roots if roots is not None else _DEFAULT_STEAM_ROOTS
    for root in candidates:
        path = Path(root) / _CLIENT_LOG_REL
        if path.exists():
            return path
    return None


def resolve_log_path(config: _LogConfig, roots: Sequence[Path] | None = None) -> Path | None:
    """Resolve the Client.txt path to watch.

    An explicit, existing ``config.client_log_path`` wins; otherwise fall back to
    :func:`default_log_path` auto-discovery. Returns None if nothing resolves.
    """
    explicit = (config.client_log_path or "").strip()
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.exists():
            return explicit_path
        return None
    return default_log_path(roots)


# Async callback invoked once per detected zone change with the area name.
ZoneChangeCallback = Callable[[str], Awaitable[None]]


class ClientLogWatcher:
    """Tails Client.txt and fires ``on_zone_change`` on each zone-change line."""

    def __init__(
        self,
        path: Path,
        on_zone_change: ZoneChangeCallback,
        poll_interval: float = 0.5,
    ) -> None:
        self.path = Path(path)
        self.on_zone_change = on_zone_change
        self.poll_interval = poll_interval
        self.last_size: int = 0
        self._running: bool = False

    def _process_new(self, text: str) -> list[str]:
        """Return area names for every zone-change line in ``text`` (pure)."""
        changes: list[str] = []
        for line in text.splitlines():
            area = parse_zone_change(line)
            if area is not None:
                changes.append(area)
        return changes

    async def _poll(self) -> None:
        """Read bytes appended since ``last_size`` and dispatch per zone change.

        If the file shrank (truncation/rotation), reset the offset to the start
        of the file so we resume cleanly without crashing.
        """
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return
        if size < self.last_size:
            self.last_size = 0  # truncated/rotated: resume from start
        if size == self.last_size:
            return  # nothing new
        with open(self.path, "rb") as f:
            f.seek(self.last_size)
            data = f.read(size - self.last_size)
        self.last_size = size
        text = data.decode("utf-8", errors="replace")
        for area in self._process_new(text):
            await self.on_zone_change(area)

    async def start(self) -> None:
        """Poll the log in a loop until :meth:`stop` is called or cancelled."""
        self._running = True
        try:
            while self._running:
                await self._poll()
                await asyncio.sleep(self.poll_interval)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Signal the polling loop started by :meth:`start` to exit."""
        self._running = False
