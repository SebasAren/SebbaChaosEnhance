"""Tests for poecraft.recipe.sets — recipe set generation core."""

from __future__ import annotations

import base64
import json

import pytest

from poecraft.recipe.types import (
    ALL_RECIPE_CLASSES,
    FrameType,
    ItemClass,
    RecipeType,
)
from poecraft.recipe.sets import (
    EnhancedItem,
    filter_stash_items,
    count_items,
    generate_sets,
)


def _icon(f_path: str) -> str:
    """Build a valid web.poecdn.com icon URL encoding the given item-path.

    f_path e.g. '2DItems/Rings/TopazSapphire' -> classifiable icon URL.
    """
    meta = [25, 14, {"f": f_path, "w": 1, "h": 1, "scale": 1}]
    encoded = base64.b64encode(json.dumps(meta).encode()).decode().rstrip("=")
    return f"https://web.poecdn.com/gen/image/{encoded}"


_ICON_PATHS: dict[ItemClass, str] = {
    ItemClass.HELMETS: "2DItems/Armours/Helmets/Iron",
    ItemClass.GLOVES: "2DItems/Armours/Gloves/Some",
    ItemClass.BOOTS: "2DItems/Armours/Boots/Some",
    ItemClass.BODY_ARMOURS: "2DItems/Armours/BodyArmours/Some",
    ItemClass.RINGS: "2DItems/Rings/TopazSapphire",
    ItemClass.AMULETS: "2DItems/Amulets/Some",
    ItemClass.BELTS: "2DItems/Belts/Some",
    ItemClass.ONE_HAND_WEAPONS: "2DItems/Weapons/OneHandWeapons/Some",
    ItemClass.TWO_HAND_WEAPONS: "2DItems/Weapons/TwoHandWeapons/Some",
}


def _raw_for(cls: ItemClass, item_id: str, **overrides) -> dict:
    """A chaos-eligible rare raw item of the given class."""
    return _raw_item(
        id=item_id,
        icon=_icon(_ICON_PATHS[cls]),
        **overrides,
    )


def _many(cls: ItemClass, count: int, prefix: str) -> list[dict]:
    """`count` distinct raw items of `cls` with ids `<prefix>-<i>`."""
    return [_raw_for(cls, f"{prefix}-{i}") for i in range(count)]


def _ei(**overrides) -> EnhancedItem:
    """Build an EnhancedItem with sensible defaults for unspecified fields."""
    defaults = dict(
        id="abc",
        name="",
        type_line="Some Base",
        item_level=70,
        frame_type=FrameType.RARE,
        identified=False,
        icon="",
        derived_item_class=None,
        stash_tab_index=0,
        x=0,
        y=0,
        w=1,
        h=1,
        influences={},
    )
    defaults.update(overrides)
    return EnhancedItem(**defaults)


class TestEnhancedItemRarity:
    def test_frame_type_2_is_rare(self):
        item = _ei(frame_type=FrameType.RARE)
        assert item.is_rare is True

    def test_non_rare_frame_is_not_rare(self):
        item = _ei(frame_type=FrameType.NORMAL)
        assert item.is_rare is False


class TestEnhancedItemIlvlEligibility:
    @pytest.mark.parametrize("ilvl", [60, 74])
    def test_chaos_eligible_within_range(self, ilvl):
        assert _ei(item_level=ilvl).is_chaos_eligible is True

    @pytest.mark.parametrize("ilvl", [59, 75])
    def test_chaos_not_eligible_outside_range(self, ilvl):
        assert _ei(item_level=ilvl).is_chaos_eligible is False

    def test_regal_eligible_at_75(self):
        assert _ei(item_level=75).is_regal_eligible is True

    @pytest.mark.parametrize("ilvl", [1, 59])
    def test_chance_eligible_low_range(self, ilvl):
        assert _ei(item_level=ilvl).is_chance_eligible is True

    def test_exalted_eligible_at_60(self):
        assert _ei(item_level=60).is_exalted_eligible is True


def _raw_item(**overrides) -> dict:
    """A raw API item dict mirroring StashItem (camelCase keys)."""
    defaults = dict(
        id="item-id",
        name="",
        typeLine="Some Base",
        ilvl=70,
        frameType=FrameType.RARE,
        identified=False,
        icon="",
        category={},
        influences={},
        x=0,
        y=0,
        w=1,
        h=1,
    )
    defaults.update(overrides)
    return defaults


class TestFilterStashItems:
    def test_only_chaos_eligible_rare_returned(self):
        ring = _raw_item(
            id="ring",
            typeLine="Topaz Ring",
            icon=_icon("2DItems/Rings/TopazSapphire"),
        )
        currency = _raw_item(
            id="currency",
            typeLine="Chaos Orb",
            frameType=FrameType.CURRENCY,
            icon=_icon("2DItems/Currency/ChaosOrb"),
        )
        low_ilvl_helmet = _raw_item(
            id="low-helmet",
            typeLine="Iron Helmet",
            ilvl=59,
            icon=_icon("2DItems/Armours/Helmets/Iron"),
        )
        identified_helmet = _raw_item(
            id="id-helmet",
            typeLine="Iron Helmet",
            ilvl=70,
            identified=True,
            icon=_icon("2DItems/Armours/Helmets/Iron"),
        )

        result = filter_stash_items(
            [ring, currency, low_ilvl_helmet, identified_helmet],
            RecipeType.CHAOS,
            include_identified=False,
        )

        assert [item.id for item in result] == ["ring"]
        assert result[0].derived_item_class is ItemClass.RINGS
        assert result[0].type_line == "Topaz Ring"
        assert result[0].item_level == 70
        assert result[0].is_rare is True

    def test_include_identified_returns_identified_items(self):
        identified_ring = _raw_item(
            id="id-ring",
            identified=True,
            icon=_icon("2DItems/Rings/TopazSapphire"),
        )
        result = filter_stash_items(
            [identified_ring], RecipeType.CHAOS, include_identified=True
        )
        assert [item.id for item in result] == ["id-ring"]

    def test_non_chaos_recipe_uses_own_ilvl_range(self):
        # regal range is 75-999: a 75 ring is eligible for regal but not chaos.
        regal_ring = _raw_item(
            id="regal-ring",
            ilvl=75,
            icon=_icon("2DItems/Rings/TopazSapphire"),
        )
        result = filter_stash_items([regal_ring], RecipeType.REGAL)
        assert [item.id for item in result] == ["regal-ring"]
        # same item excluded for chaos
        result_chaos = filter_stash_items([regal_ring], RecipeType.CHAOS)
        assert result_chaos == []


class TestCountItems:
    def test_tally_per_class(self):
        items = [
            _ei(derived_item_class=ItemClass.RINGS),
            _ei(derived_item_class=ItemClass.RINGS),
            _ei(derived_item_class=ItemClass.HELMETS),
            _ei(derived_item_class=None),  # unclassified should be ignored
        ]
        counts = count_items(items)
        assert counts == {
            ItemClass.RINGS: 2,
            ItemClass.HELMETS: 1,
        }

    def test_empty_input(self):
        assert count_items([]) == {}


class TestGenerateSetsEmpty:
    def test_empty_items_creates_threshold_empty_sets(self):
        status = generate_sets([], RecipeType.CHAOS, set_threshold=2)

        assert status.completed_sets == 0
        assert len(status.in_progress) == 2
        assert status.unassigned_items == []
        assert status.item_counts == {}
        # each set is missing every required class: the 7 jewellery/armour
        # classes plus the shared weapon slot (one-hand & two-hand).
        for recipe_set in status.in_progress:
            assert recipe_set.missing == ALL_RECIPE_CLASSES
            assert recipe_set.items == {}
            assert recipe_set.is_complete is False
        assert status.missing_classes == ALL_RECIPE_CLASSES

    def test_empty_items_zero_threshold(self):
        status = generate_sets([], RecipeType.CHAOS, set_threshold=0)
        assert status.in_progress == []
        assert status.completed_sets == 0
        assert status.missing_classes == set()
        assert status.unassigned_items == []


class TestGenerateSetsFill:
    def test_two_complete_chaos_sets(self):
        # 2 complete chaos sets worth of items: 2 rings + 1 each of the six
        # singletons + 2 one-hand weapons, per set.
        items = [
            *_many(ItemClass.RINGS, 4, "ring"),
            *_many(ItemClass.AMULETS, 2, "amu"),
            *_many(ItemClass.BELTS, 2, "belt"),
            *_many(ItemClass.HELMETS, 2, "helm"),
            *_many(ItemClass.GLOVES, 2, "glove"),
            *_many(ItemClass.BOOTS, 2, "boot"),
            *_many(ItemClass.BODY_ARMOURS, 2, "body"),
            *_many(ItemClass.ONE_HAND_WEAPONS, 4, "1h"),
        ]

        status = generate_sets(items, RecipeType.CHAOS, set_threshold=2)

        assert status.completed_sets == 2
        assert len(status.in_progress) == 2
        assert status.unassigned_items == []
        assert status.missing_classes == set()

        for recipe_set in status.in_progress:
            assert recipe_set.is_complete is True
            # every required class is present
            assert set(recipe_set.items.keys()) == {
                ItemClass.RINGS,
                ItemClass.AMULETS,
                ItemClass.BELTS,
                ItemClass.HELMETS,
                ItemClass.GLOVES,
                ItemClass.BOOTS,
                ItemClass.BODY_ARMOURS,
                ItemClass.ONE_HAND_WEAPONS,
            }
            # per-item -> set assignment with correct counts
            assert len(recipe_set.items[ItemClass.RINGS]) == 2
            assert len(recipe_set.items[ItemClass.ONE_HAND_WEAPONS]) == 2
            for cls in (
                ItemClass.AMULETS,
                ItemClass.BELTS,
                ItemClass.HELMETS,
                ItemClass.GLOVES,
                ItemClass.BOOTS,
                ItemClass.BODY_ARMOURS,
            ):
                assert len(recipe_set.items[cls]) == 1

        # item_counts reflects totals across both sets
        assert status.item_counts[ItemClass.RINGS] == 4
        assert status.item_counts[ItemClass.ONE_HAND_WEAPONS] == 4

    def test_two_hand_weapon_fills_slot_and_surplus_tracked(self):
        # 2 complete sets: one weapon slot filled by a 2H, the other by 2x 1H.
        # 4 helmets total (2 needed) -> 2 surplus.
        items = [
            *_many(ItemClass.RINGS, 4, "ring"),
            *_many(ItemClass.AMULETS, 2, "amu"),
            *_many(ItemClass.BELTS, 2, "belt"),
            *_many(ItemClass.HELMETS, 4, "helm"),
            *_many(ItemClass.GLOVES, 2, "glove"),
            *_many(ItemClass.BOOTS, 2, "boot"),
            *_many(ItemClass.BODY_ARMOURS, 2, "body"),
            *_many(ItemClass.ONE_HAND_WEAPONS, 2, "1h"),
            *_many(ItemClass.TWO_HAND_WEAPONS, 1, "2h"),
        ]

        status = generate_sets(items, RecipeType.CHAOS, set_threshold=2)

        assert status.completed_sets == 2
        for recipe_set in status.in_progress:
            assert recipe_set.is_complete is True

        # one set's weapon slot is the 2H, the other's is the pair of 1H
        two_hand_sets = [
            s for s in status.in_progress
            if ItemClass.TWO_HAND_WEAPONS in s.items
        ]
        one_hand_sets = [
            s for s in status.in_progress
            if ItemClass.ONE_HAND_WEAPONS in s.items
        ]
        assert len(two_hand_sets) == 1
        assert len(two_hand_sets[0].items[ItemClass.TWO_HAND_WEAPONS]) == 1
        assert len(one_hand_sets) == 1
        assert len(one_hand_sets[0].items[ItemClass.ONE_HAND_WEAPONS]) == 2

        # 2 surplus helmets routed to unassigned_items
        assert len(status.unassigned_items) == 2
        assert {
            item.derived_item_class for item in status.unassigned_items
        } == {ItemClass.HELMETS}
        assert {item.id for item in status.unassigned_items} == {
            "helm-2",
            "helm-3",
        }
        # item_counts reflects all eligible items, including surplus
        assert status.item_counts[ItemClass.HELMETS] == 4
        assert status.item_counts[ItemClass.TWO_HAND_WEAPONS] == 1

    def test_two_hand_sorted_before_one_hand(self):
        # 1x 2H + 1x 1H, threshold 1: the 2H must claim the empty weapon
        # slot; the lone 1H cannot complete a set on its own -> surplus.
        # This discriminates the two-hand-first sort.
        items = [
            *_many(ItemClass.RINGS, 2, "ring"),
            *_many(ItemClass.AMULETS, 1, "amu"),
            *_many(ItemClass.BELTS, 1, "belt"),
            *_many(ItemClass.HELMETS, 1, "helm"),
            *_many(ItemClass.GLOVES, 1, "glove"),
            *_many(ItemClass.BOOTS, 1, "boot"),
            *_many(ItemClass.BODY_ARMOURS, 1, "body"),
            *_many(ItemClass.ONE_HAND_WEAPONS, 1, "1h"),
            *_many(ItemClass.TWO_HAND_WEAPONS, 1, "2h"),
        ]

        status = generate_sets(items, RecipeType.CHAOS, set_threshold=1)

        assert status.completed_sets == 1
        only_set = status.in_progress[0]
        assert only_set.is_complete is True
        assert ItemClass.TWO_HAND_WEAPONS in only_set.items
        assert ItemClass.ONE_HAND_WEAPONS not in only_set.items
        assert [item.id for item in status.unassigned_items] == ["1h-0"]
