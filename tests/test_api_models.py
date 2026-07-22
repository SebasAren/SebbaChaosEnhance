"""Pydantic model parsing against the real PoE API response shapes.

The stash-tab metadata endpoint uses abbreviated keys (``n`` for name, ``i`` for
index); the models alias those onto friendlier names. These tests pin that
mapping so a regression (every tab showing "Tab 0") is caught immediately.
"""

from __future__ import annotations

from poecraft.api.models import StashItem, StashTabContents, StashTabMetadataResponse, StashTabProps
from poecraft.recipe.classifier import classify_item


def test_stash_tab_props_parses_abbreviated_api_keys() -> None:
    """The API sends `n`/`i`; the model must expose them as name/index."""
    raw = {
        "n": "Dump Tab",
        "i": 3,
        "id": "abc-123",
        "type": "QuadStash",
        "colour": {"r": 1, "g": 2, "b": 3},  # unrelated key, must be ignored
    }

    tab = StashTabProps(**raw)

    assert tab.name == "Dump Tab"
    assert tab.index == 3
    assert tab.id == "abc-123"
    assert tab.type == "QuadStash"


def test_stash_tab_props_parses_folder_children() -> None:
    """Nested tabs inside a Folder keep the same abbreviated key mapping."""
    raw = {
        "n": "Folder",
        "i": 0,
        "type": "Folder",
        "children": [
            {"n": "Quad One", "i": 1, "type": "QuadStash"},
            {"n": "Quad Two", "i": 2, "type": "QuadStash"},
        ],
    }

    tab = StashTabProps(**raw)

    assert tab.children is not None
    assert [c.name for c in tab.children] == ["Quad One", "Quad Two"]
    assert [c.index for c in tab.children] == [1, 2]


def test_stash_tab_props_still_accepts_field_names() -> None:
    """Construction via the friendly field names keeps working (tests/fixtures)."""
    tab = StashTabProps(name="Quad", index=5, type="NormalStash")

    assert tab.name == "Quad"
    assert tab.index == 5


def test_stash_tab_props_model_dump_uses_field_names() -> None:
    """The frontend reads name/index, so dump must emit field names, not aliases."""
    tab = StashTabProps(**{"n": "Quad", "i": 7, "type": "QuadStash"})

    dumped = tab.model_dump()

    assert dumped["name"] == "Quad"
    assert dumped["index"] == 7
    assert "n" not in dumped
    assert "i" not in dumped


def test_metadata_response_round_trips_real_shape() -> None:
    raw = {
        "numTabs": 2,
        "tabs": [
            {"n": "First", "i": 0, "type": "NormalStash"},
            {"n": "Second", "i": 1, "type": "QuadStash"},
        ],
    }

    resp = StashTabMetadataResponse(**raw)

    assert resp.numTabs == 2
    assert [t.name for t in resp.tabs] == ["First", "Second"]
    assert [t.index for t in resp.tabs] == [0, 1]


def test_tab_contents_parses_real_item_shape_and_classifies() -> None:
    """Items use full keys (name/typeLine/ilvl/...), not the tab n/i abbreviations.

    Guards the fetch path: a real ?tabIndex=N response must yield items whose
    fields survive parsing and whose derived item class is correct.
    """
    raw = {
        "numTabs": 4,
        "tabs": [{"n": "Dump", "i": 2, "type": "QuadStash"}],
        "items": [
            {
                "id": "a1",
                "name": "",
                "typeLine": "Gold Ring",
                "ilvl": 74,
                "frameType": 2,
                "identified": False,
                "icon": "",
                "category": {"ring": []},
                "x": 3,
                "y": 5,
                "w": 1,
                "h": 1,
                "influences": {},
                "socketedItems": [],
                "requirements": [],  # extra, unrelated key -> ignored
            },
            {
                "id": "a2",
                "name": "",
                "typeLine": "Siege Helmet",
                "ilvl": 68,
                "frameType": 2,
                "identified": False,
                "icon": "",
                "category": {"armour": ["helmet"]},
                "x": 10,
                "y": 2,
                "w": 2,
                "h": 2,
            },
        ],
    }

    contents = StashTabContents(**raw)

    assert contents.numTabs == 4
    assert len(contents.items) == 2

    ring, helmet = contents.items
    assert (ring.typeLine, ring.ilvl, ring.frameType) == ("Gold Ring", 74, 2)
    assert (ring.x, ring.y, ring.w, ring.h) == (3, 5, 1, 1)
    assert helmet.typeLine == "Siege Helmet"

    # the dumped dicts feed the classifier (icon empty -> category fallback)
    assert classify_item(ring.model_dump()).value == "Rings"
    assert classify_item(helmet.model_dump()).value == "Helmets"
