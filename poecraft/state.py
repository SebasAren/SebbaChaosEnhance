"""In-memory recipe state + refresh orchestration.

Holds the current :class:`RecipeStatus` and drives a refresh cycle:
fetch selected stash tabs -> generate recipe sets -> update the loot
filter -> store the result. The client and filter writer are injected so
the cycle is unit-testable without network or filesystem.
"""

from __future__ import annotations

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

        filter_writer.update_filter(
            path=config.loot_filter_path,
            missing_classes=status.missing_classes,
            recipe_type=recipe_type,
            include_identified=config.include_identified,
        )

        self.current = status
        self.last_refresh = datetime.now()
        return status


_state: RecipeState | None = None


def get_state() -> RecipeState:
    """Return the module-level RecipeState singleton."""
    global _state
    if _state is None:
        _state = RecipeState()
    return _state
