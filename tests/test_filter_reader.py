"""Tests for poecraft.filter.reader — marker-based filter splitting."""

from __future__ import annotations

from poecraft.filter.reader import (
    MARKER_END,
    MARKER_START,
    read_filter,
    split_filter,
)


def test_split_filter_with_markers_returns_before_section_after() -> None:
    before = "# my filter\nShow\n    Class \"Currency\"\n"
    section = "Show\n    Class \"Rings\"\n"
    after = "# end of filter\n"
    content = f"{before}{MARKER_START}\n{section}{MARKER_END}\n{after}"

    got_before, got_section, got_after = split_filter(content)
    assert got_before == before
    assert got_section == f"{MARKER_START}\n{section}{MARKER_END}\n"
    assert got_after == after


def test_split_filter_no_markers_returns_empty_before_empty_section_whole_after() -> None:
    whole = "# plain filter\nShow\n    Class \"Currency\"\n"
    got_before, got_section, got_after = split_filter(whole)
    assert got_before == ""
    assert got_section == ""
    assert got_after == whole


def test_read_filter_returns_file_contents(tmp_path) -> None:
    p = tmp_path / "test.filter"
    p.write_text("Show\n    Class \"Rings\"\n")
    assert read_filter(p) == "Show\n    Class \"Rings\"\n"
