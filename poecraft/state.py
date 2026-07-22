"""In-memory recipe state + refresh orchestration.

Holds the current :class:`RecipeStatus` and drives a refresh cycle:
fetch selected stash tabs -> generate recipe sets -> update the loot
filter -> store the result. The client and filter writer are injected so
the cycle is unit-testable without network or filesystem.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from poecraft.config import Config
from poecraft.recipe.sets import RecipeStatus, generate_sets
from poecraft.recipe.types import RecipeType


class RecipeState:
    """Current recipe status and last refresh timestamp."""

    def __init__(self) -> None:
        self.current: RecipeStatus | None = None
        self.last_refresh: datetime | None = None
        # SSE subscribers: each connected /api/events client owns one queue,
        # which we push the latest payload onto whenever the state changes.
        self._subscribers: list[asyncio.Queue[dict]] = []

    async def refresh(self, client: Any, config: Config, filter_writer: Any) -> RecipeStatus:
        """Run one refresh cycle and store the resulting status.

        ``client`` must expose ``async get_all_selected_tabs(indices)``; the
        ``filter_writer`` must expose ``update_filter(path, missing_classes,
        recipe_type, include_identified)``.
        """
        tabs = await client.get_all_selected_tabs(config.stash_tabs)

        raw_items: list[dict] = []
        for items in tabs.values():
            for item in items:
                raw_items.append(
                    item.model_dump() if hasattr(item, "model_dump") else dict(item)
                )

        recipe_type = RecipeType(config.recipe_type)
        status = generate_sets(
            raw_items,
            recipe_type=recipe_type,
            set_threshold=config.set_threshold,
            include_identified=config.include_identified,
        )

        # An empty loot_filter_path means no filter is configured — skip the
        # update rather than crash on open("").
        if config.loot_filter_path:
            filter_writer.update_filter(
                path=config.loot_filter_path,
                missing_classes=status.missing_classes,
                recipe_type=recipe_type,
                include_identified=config.include_identified,
            )

        self.current = status
        self.last_refresh = datetime.now()
        self._notify()
        return status

    def to_payload(self) -> dict:
        """JSON-serializable status payload (the /api/status contract).

        Centralized here so both the REST endpoints and the SSE stream render
        an identical shape.
        """
        status = self.current
        if status is None:
            return {
                "completed_sets": 0,
                "item_counts": {},
                "missing_classes": [],
                "grid": {"items": []},
                "last_refresh": None,
            }
        return {
            "completed_sets": status.completed_sets,
            "item_counts": {cls.value: n for cls, n in status.item_counts.items()},
            "missing_classes": sorted(cls.value for cls in status.missing_classes),
            "grid": status.to_grid(),
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
        }

    def subscribe(self) -> asyncio.Queue[dict]:
        """Register a queue that receives the payload on every refresh."""
        q: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        """Remove a subscriber queue (no-op if already removed)."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def _notify(self) -> None:
        """Push the current payload to every subscriber (non-blocking)."""
        if not self._subscribers:
            return
        payload = self.to_payload()
        for q in self._subscribers:
            q.put_nowait(payload)


_state: RecipeState | None = None


def get_state() -> RecipeState:
    """Return the module-level RecipeState singleton."""
    global _state
    if _state is None:
        _state = RecipeState()
    return _state
