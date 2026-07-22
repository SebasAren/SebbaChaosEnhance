"""Loot-filter reader: marker-based splitting.

A PoE loot filter managed by poecraft has an injected highlight section
wrapped by MARKER_START and MARKER_END comment lines. split_filter separates
a raw filter string into the text before, the marker-wrapped section, and
the text after.
"""

from __future__ import annotations

import os

MARKER_START = "# poecraft:chaos-recipe start"
MARKER_END = "# poecraft:chaos-recipe end"


def read_filter(path: os.PathLike | str) -> str:
    """Read a .filter file's full contents as a string."""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def split_filter(content: str) -> tuple[str, str, str]:
    """Split filter content into (before, section, after) on poecraft markers.

    The returned ``section`` includes the MARKER_START and MARKER_END lines
    plus everything between them. If no markers are present, returns
    ``("", "", content)`` — i.e. the whole filter is treated as the
    "after" part so an empty section can be injected between an empty
    "before" and the existing content.
    """
    start_idx = content.find(MARKER_START)
    if start_idx == -1:
        return "", "", content

    end_idx = content.find(MARKER_END, start_idx)
    if end_idx == -1:
        # Unterminated marker: treat the remainder as the section.
        return content[:start_idx], content[start_idx:], ""

    end_with_newline = end_idx + len(MARKER_END)
    # Include the trailing newline after the end marker, if present.
    if content[end_with_newline : end_with_newline + 1] == "\n":
        end_with_newline += 1

    before = content[:start_idx]
    section = content[start_idx:end_with_newline]
    after = content[end_with_newline:]
    return before, section, after
