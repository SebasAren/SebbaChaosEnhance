"""Recipe set generation core.

Turns raw PoE API stash items into recipe-eligible EnhancedItems and
generates in-progress chaos/regal/chance/exalted sets with per-item → set
assignment and surplus tracking. Pure Python — no network or filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from poecraft.recipe import classifier
from poecraft.recipe.types import (
    FrameType,
    ItemClass,
    RecipeType,
    RECIPE_ILVL_RANGES,
    RECIPE_SET_REQUIREMENTS,
    WEAPON_SLOT_REQUIRED_UNITS,
)


@dataclass
class EnhancedItem:
    """A stash item enriched with derived recipe metadata."""

    id: str
    name: str
    type_line: str
    item_level: int
    frame_type: FrameType
    identified: bool
    icon: str
    derived_item_class: Optional[ItemClass]
    stash_tab_index: int
    x: int
    y: int
    w: int
    h: int
    influences: dict

    @property
    def is_rare(self) -> bool:
        return self.frame_type == FrameType.RARE

    def _in_range(self, recipe_type: RecipeType) -> bool:
        low, high = RECIPE_ILVL_RANGES[recipe_type]
        return low <= self.item_level <= high

    @property
    def is_chaos_eligible(self) -> bool:
        return self._in_range(RecipeType.CHAOS)

    @property
    def is_regal_eligible(self) -> bool:
        return self._in_range(RecipeType.REGAL)

    @property
    def is_chance_eligible(self) -> bool:
        return self._in_range(RecipeType.CHANCE)

    @property
    def is_exalted_eligible(self) -> bool:
        return self._in_range(RecipeType.EXALTED)


def _in_recipe_ilvl_range(item_level: int, recipe_type: RecipeType) -> bool:
    low, high = RECIPE_ILVL_RANGES[recipe_type]
    return low <= item_level <= high


def is_eligible(
    item_data: dict, recipe_type: RecipeType, include_identified: bool
) -> bool:
    """Whether a raw API item dict qualifies for the given recipe."""
    if item_data.get("frameType") != FrameType.RARE:
        return False
    if item_data.get("identified") and not include_identified:
        return False
    if not _in_recipe_ilvl_range(item_data.get("ilvl", 0), recipe_type):
        return False
    if classifier.classify_item(item_data) is None:
        return False
    return True


def filter_stash_items(
    raw_items: list[dict],
    recipe_type: RecipeType,
    include_identified: bool = False,
) -> list[EnhancedItem]:
    """Map raw API item dicts to recipe-eligible EnhancedItems."""
    eligible: list[EnhancedItem] = []
    for raw in raw_items:
        if not is_eligible(raw, recipe_type, include_identified):
            continue
        eligible.append(
            EnhancedItem(
                id=raw.get("id", ""),
                name=raw.get("name", ""),
                type_line=raw.get("typeLine", ""),
                item_level=raw.get("ilvl", 0),
                frame_type=raw.get("frameType"),
                identified=raw.get("identified", False),
                icon=raw.get("icon", ""),
                derived_item_class=classifier.classify_item(raw),
                stash_tab_index=raw.get("stashTabindex", 0),
                x=raw.get("x", 0),
                y=raw.get("y", 0),
                w=raw.get("w", 0),
                h=raw.get("h", 0),
                influences=raw.get("influences", {}) or {},
            )
        )
    return eligible


def count_items(items: list[EnhancedItem]) -> dict[ItemClass, int]:
    """Tally EnhancedItems per derived_item_class, skipping unclassified."""
    counts: dict[ItemClass, int] = {}
    for item in items:
        if item.derived_item_class is None:
            continue
        counts[item.derived_item_class] = counts.get(item.derived_item_class, 0) + 1
    return counts


@dataclass
class RecipeSet:
    """One recipe set being assembled: items assigned per item class.

    Non-weapon classes hold up to RECIPE_SET_REQUIREMENTS[cls] items. The
    weapon slot holds EITHER one two-hand weapon OR up to two one-hand
    weapons (a two-hand weapon counts as 2 units, a one-hand as 1).
    """

    items: dict[ItemClass, list[EnhancedItem]] = field(default_factory=dict)

    def _count(self, cls: ItemClass) -> int:
        return len(self.items.get(cls, []))

    def _weapon_units(self) -> int:
        return self._count(ItemClass.ONE_HAND_WEAPONS) + 2 * self._count(
            ItemClass.TWO_HAND_WEAPONS
        )

    def can_accept(self, item: EnhancedItem) -> bool:
        """Whether this set still has room for the item's class."""
        cls = item.derived_item_class
        if cls is None:
            return False
        if cls in RECIPE_SET_REQUIREMENTS:
            return self._count(cls) < RECIPE_SET_REQUIREMENTS[cls]
        if cls is ItemClass.TWO_HAND_WEAPONS:
            # a two-hand weapon fills the slot; it only fits an empty one
            return self._weapon_units() == 0
        if cls is ItemClass.ONE_HAND_WEAPONS:
            return self._weapon_units() < WEAPON_SLOT_REQUIRED_UNITS
        return False

    def add(self, item: EnhancedItem) -> None:
        cls = item.derived_item_class
        if cls is None:
            return
        self.items.setdefault(cls, []).append(item)

    @property
    def missing(self) -> set[ItemClass]:
        """Classes still needed to complete this set."""
        missing: set[ItemClass] = {
            cls
            for cls, required in RECIPE_SET_REQUIREMENTS.items()
            if self._count(cls) < required
        }
        if self._weapon_units() < WEAPON_SLOT_REQUIRED_UNITS:
            missing.add(ItemClass.ONE_HAND_WEAPONS)
            if self._count(ItemClass.ONE_HAND_WEAPONS) == 0:
                # no weapons yet: a two-hand weapon could fill the slot alone
                missing.add(ItemClass.TWO_HAND_WEAPONS)
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.missing


@dataclass
class RecipeStatus:
    """Aggregate state of recipe-set generation."""

    completed_sets: int
    in_progress: list[RecipeSet]
    missing_classes: set[ItemClass]
    item_counts: dict[ItemClass, int]
    unassigned_items: list[EnhancedItem]

    def to_grid(self) -> dict:
        """Flatten to a grid-friendly dict: items with per-item set_index.

        Items in ``in_progress`` sets carry their set index (0-based); items in
        ``unassigned_items`` carry ``None``. Each item exposes id, geometry
        (x/y/w/h), set_index, and its derived class string.
        """
        items: list[dict] = []
        for set_index, recipe_set in enumerate(self.in_progress):
            for cls, assigned in recipe_set.items.items():
                for item in assigned:
                    items.append(self._grid_item(item, set_index))
        for item in self.unassigned_items:
            items.append(self._grid_item(item, None))
        return {"items": items}

    @staticmethod
    def _grid_item(item: EnhancedItem, set_index: int | None) -> dict:
        return {
            "id": item.id,
            "x": item.x,
            "y": item.y,
            "w": item.w,
            "h": item.h,
            "set_index": set_index,
            "class": item.derived_item_class.value
            if item.derived_item_class is not None
            else None,
        }


def _sort_key_for_fill(item: EnhancedItem):
    """Two-hand weapons first, then by item class."""
    cls = item.derived_item_class
    is_two_hand = cls is ItemClass.TWO_HAND_WEAPONS
    return (0 if is_two_hand else 1, cls.value if cls else "")


def generate_sets(
    items: list[dict],
    recipe_type: RecipeType,
    set_threshold: int,
    include_identified: bool = False,
) -> RecipeStatus:
    """Greedily assign eligible items to set_threshold recipe sets.

    Items are sorted two-hand weapons first, then by class. Each item is
    placed into the first set that still has room for its class; items that
    no set can accept become surplus (unassigned_items). in_progress holds
    all generated sets (complete and partial); completed_sets counts those
    that are complete.
    """
    eligible = filter_stash_items(items, recipe_type, include_identified)
    item_counts = count_items(eligible)

    recipe_sets = [RecipeSet() for _ in range(set_threshold)]

    unassigned: list[EnhancedItem] = []
    for item in sorted(eligible, key=_sort_key_for_fill):
        for recipe_set in recipe_sets:
            if recipe_set.can_accept(item):
                recipe_set.add(item)
                break
        else:
            unassigned.append(item)

    completed_sets = sum(1 for s in recipe_sets if s.is_complete)
    missing_classes: set[ItemClass] = set()
    for recipe_set in recipe_sets:
        missing_classes |= recipe_set.missing

    return RecipeStatus(
        completed_sets=completed_sets,
        in_progress=recipe_sets,
        missing_classes=missing_classes,
        item_counts=item_counts,
        unassigned_items=unassigned,
    )
