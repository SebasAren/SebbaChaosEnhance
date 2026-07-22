"""Integration: recipe-core missing_classes drives the loot filter.

Builds a stash via recipe-core's generate_sets, derives the missing classes
from the resulting RecipeStatus, and drives update_filter on a tmp .filter
file — asserting the written filter Shows exactly the missing classes and
Hides nothing.
"""

from __future__ import annotations

import base64
import json

from poecraft.recipe.types import ItemClass, RecipeType
from poecraft.recipe.sets import generate_sets
from poecraft.filter.reader import MARKER_END, MARKER_START
from poecraft.filter.writer import update_filter


def _icon(f_path: str) -> str:
    meta = [25, 14, {"f": f_path, "w": 1, "h": 1, "scale": 1}]
    encoded = base64.b64encode(json.dumps(meta).encode()).decode().rstrip("=")
    return f"https://web.poecdn.com/gen/image/{encoded}"


_ICON_PATHS = {
    ItemClass.HELMETS: "2DItems/Armours/Helmets/Iron",
    ItemClass.GLOVES: "2DItems/Armours/Gloves/Some",
    ItemClass.BOOTS: "2DItems/Armours/Boots/Some",
    ItemClass.BODY_ARMOURS: "2DItems/Armours/BodyArmours/Some",
    ItemClass.RINGS: "2DItems/Rings/TopazSapphire",
    ItemClass.AMULETS: "2DItems/Amulets/Some",
    ItemClass.BELTS: "2DItems/Belts/Some",
    ItemClass.ONE_HAND_WEAPONS: "2DItems/Weapons/OneHandWeapons/Some",
}


def _raw_for(cls: ItemClass, item_id: str) -> dict:
    return {
        "id": item_id,
        "name": "",
        "typeLine": "Some Base",
        "ilvl": 70,
        "frameType": 2,
        "identified": False,
        "icon": _icon(_ICON_PATHS[cls]),
        "stashTabindex": 0,
        "x": 0,
        "y": 0,
        "w": 1,
        "h": 1,
        "influences": {},
    }


def test_recipe_core_missing_classes_drive_filter(tmp_path) -> None:
    # A complete chaos set EXCEPT rings and boots are missing.
    stash = [
        _raw_for(ItemClass.HELMETS, "h1"),
        _raw_for(ItemClass.GLOVES, "g1"),
        _raw_for(ItemClass.BODY_ARMOURS, "b1"),
        _raw_for(ItemClass.AMULETS, "a1"),
        _raw_for(ItemClass.BELTS, "be1"),
        _raw_for(ItemClass.ONE_HAND_WEAPONS, "oh1"),
        _raw_for(ItemClass.ONE_HAND_WEAPONS, "oh2"),
    ]
    status = generate_sets(stash, RecipeType.CHAOS, set_threshold=1)
    assert ItemClass.RINGS in status.missing_classes
    assert ItemClass.BOOTS in status.missing_classes

    p = tmp_path / "integration.filter"
    p.write_text("# user filter\nShow\n    Class \"Currency\"\n")

    changed = update_filter(p, status.missing_classes, RecipeType.CHAOS)
    assert changed is True

    result = p.read_text()
    # markers present
    assert MARKER_START in result
    assert MARKER_END in result
    # Shows the missing classes
    assert 'Class "Rings"' in result
    assert 'Class "Boots"' in result
    # Hides nothing — highlight-only
    assert "Hide" not in result
    # does NOT add rules for classes the user already has covered
    assert 'Class "Helmets"' not in result
    assert 'Class "Gloves"' not in result
    # original user content preserved
    assert "# user filter" in result
    assert 'Class "Currency"' in result
