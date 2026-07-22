"""Tests for poecraft.filter.generator — loot filter rule generation."""

from __future__ import annotations

import pytest

from poecraft.recipe.types import ItemClass, RecipeType

from poecraft.filter.generator import _parse_hex, generate_rule, generate_section
from poecraft.filter.reader import MARKER_END, MARKER_START


def test_parse_hex_full_orange() -> None:
    assert _parse_hex("#FF9600FF") == (255, 150, 0, 255)


def test_parse_hex_full_white() -> None:
    assert _parse_hex("#FFFFFFFF") == (255, 255, 255, 255)


def test_parse_hex_no_hash_prefix() -> None:
    assert _parse_hex("00FF0080") == (0, 255, 0, 128)


def test_generate_rule_rings_chaos_contains_all_required_lines() -> None:
    rule = generate_rule(ItemClass.RINGS, RecipeType.CHAOS)
    required = [
        "Show",
        'Class "Rings"',
        "Rarity Rare",
        "Identified False",
        "ItemLevel >= 60",
        "ItemLevel <= 74",
        "HasInfluence None",
        "Sockets < 6",
        "LinkedSockets < 5",
        "SetBackgroundColor 255 150 0 255",
        "SetFontSize 40",
        "MinimapIcon 0 Yellow Circle",
        "PlayEffect Yellow Temp",
    ]
    for line in required:
        assert line in rule, f"missing expected line: {line!r}"


def test_generate_rule_include_identified_omits_identified_line() -> None:
    rule = generate_rule(ItemClass.RINGS, RecipeType.REGAL, include_identified=True)
    assert "ItemLevel >= 75" in rule
    assert "Identified" not in rule


def test_generate_rule_chance_recipe_uses_chance_ilvl_range() -> None:
    rule = generate_rule(ItemClass.RINGS, RecipeType.CHANCE)
    assert "ItemLevel <= 59" in rule


@pytest.mark.parametrize(
    "item_class, expected_class_line",
    [
        (ItemClass.BODY_ARMOURS, 'Class "Body Armours"'),
        (ItemClass.ONE_HAND_WEAPONS, 'Class "One Hand Weapons"'),
        (ItemClass.TWO_HAND_WEAPONS, 'Class "Two Hand Weapons"'),
    ],
)
def test_generate_rule_multi_word_class_names_quoted(
    item_class: ItemClass, expected_class_line: str
) -> None:
    rule = generate_rule(item_class, RecipeType.CHAOS)
    assert expected_class_line in rule


def test_generate_section_highlight_only_missing_never_hide_wrapped_in_markers() -> None:
    section = generate_section({ItemClass.RINGS, ItemClass.BOOTS}, RecipeType.CHAOS)
    assert MARKER_START in section
    assert MARKER_END in section
    # exactly one Show rule for each missing class
    assert section.count('Class "Rings"') == 1
    assert section.count('Class "Boots"') == 1
    # never Hide
    assert "Hide" not in section
    # no rule for any non-missing class
    for non_missing in (ItemClass.HELMETS, ItemClass.AMULETS, ItemClass.BELTS):
        non_missing_name = {
            ItemClass.HELMETS: "Helmets",
            ItemClass.AMULETS: "Amulets",
            ItemClass.BELTS: "Belts",
        }[non_missing]
        assert f'Class "{non_missing_name}"' not in section
