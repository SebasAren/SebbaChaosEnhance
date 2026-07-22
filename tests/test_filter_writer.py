"""Tests for poecraft.filter.writer — injecting/replacing/removing sections."""

from __future__ import annotations

from poecraft.filter.reader import MARKER_END, MARKER_START
from poecraft.filter.writer import remove_chaos_section, update_filter, write_filter
from poecraft.recipe.types import ItemClass, RecipeType


def test_write_filter_writes_content(tmp_path) -> None:
    p = tmp_path / "out.filter"
    write_filter(p, 'Show\n    Class "Currency"\n')
    assert p.read_text() == 'Show\n    Class "Currency"\n'


def test_update_filter_injects_section_into_fresh_filter(tmp_path) -> None:
    original = 'Show\n    Class "Currency"\n'
    p = tmp_path / "fresh.filter"
    p.write_text(original)

    changed = update_filter(p, {ItemClass.RINGS}, RecipeType.CHAOS)
    assert changed is True

    result = p.read_text()
    # markers present
    assert MARKER_START in result
    assert MARKER_END in result
    # Rings Show rule present
    assert 'Class "Rings"' in result
    assert "Hide" not in result
    # original content intact
    assert original in result
    # markers appear exactly once
    assert result.count(MARKER_START) == 1
    assert result.count(MARKER_END) == 1


def test_update_filter_idempotent_replace(tmp_path) -> None:
    original = 'Show\n    Class "Currency"\n# trailing\n'
    p = tmp_path / "idempotent.filter"
    p.write_text(original)

    update_filter(p, {ItemClass.RINGS}, RecipeType.CHAOS)
    once = p.read_text()
    update_filter(p, {ItemClass.RINGS}, RecipeType.CHAOS)
    twice = p.read_text()

    # the Rings Show rule appears exactly once after the second call
    assert twice.count('Class "Rings"') == 1
    # content is stable (second call produced the same result as the first)
    assert once == twice
    # original before/after content intact
    assert original in twice


def test_update_filter_threads_needs_lower_level(tmp_path) -> None:
    """needs_lower_level=False broadens the chaos range to ilvl 60+."""
    p = tmp_path / "broad.filter"
    p.write_text('Show\n    Class "Currency"\n')

    update_filter(p, {ItemClass.BOOTS}, RecipeType.CHAOS, needs_lower_level=False)

    result = p.read_text()
    assert "ItemLevel >= 60" in result
    assert "ItemLevel <= 74" not in result


def test_update_filter_default_keeps_upper_bound(tmp_path) -> None:
    """Default (needs_lower_level=True) keeps the strict 60-74 chaos range."""
    p = tmp_path / "strict.filter"
    p.write_text('Show\n    Class "Currency"\n')

    update_filter(p, {ItemClass.BOOTS}, RecipeType.CHAOS)

    result = p.read_text()
    assert "ItemLevel <= 74" in result


def test_remove_chaos_section_strips_markers_and_section(tmp_path) -> None:
    original = 'Show\n    Class "Currency"\n# trailing\n'
    p = tmp_path / "removable.filter"
    p.write_text(original)
    update_filter(p, {ItemClass.RINGS, ItemClass.BOOTS}, RecipeType.CHAOS)

    removed = remove_chaos_section(p)
    assert removed is True

    result = p.read_text()
    # no markers, no section, no recipe rules
    assert MARKER_START not in result
    assert MARKER_END not in result
    assert 'Class "Rings"' not in result
    assert 'Class "Boots"' not in result
    # original content intact
    assert original in result


def test_remove_chaos_section_on_clean_filter_returns_false(tmp_path) -> None:
    original = 'Show\n    Class "Currency"\n'
    p = tmp_path / "clean.filter"
    p.write_text(original)

    removed = remove_chaos_section(p)
    assert removed is False
    assert p.read_text() == original
