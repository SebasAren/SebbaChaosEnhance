"""Loot-filter writer: splice generated highlight sections into .filter files.

update_filter reads a .filter, splits it on the poecraft markers, generates a
fresh highlight section for the missing classes, and splices it back in —
injecting on a fresh filter or replacing an existing section idempotently.
remove_chaos_section strips the marker-wrapped section entirely.
"""

from __future__ import annotations

import os

from poecraft.recipe.types import ItemClass, RecipeType

from poecraft.filter.generator import generate_section
from poecraft.filter.reader import read_filter, split_filter


def write_filter(path: os.PathLike | str, content: str) -> None:
    """Write ``content`` to a .filter file (utf-8)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def update_filter(
    path: os.PathLike | str,
    missing_classes: set[ItemClass],
    recipe_type: RecipeType,
    include_identified: bool = False,
) -> bool:
    """Inject or replace the poecraft highlight section in a .filter file.

    Returns True if the file content changed (section differs from what was
    there), False if it was already up to date. The original before/after
    content is always preserved; only the marker-wrapped section is touched.
    """
    content = read_filter(path)
    before, _existing, after = split_filter(content)
    section = generate_section(missing_classes, recipe_type, include_identified)
    new_content = f"{before}{section}{after}"
    write_filter(path, new_content)
    return new_content != content


def remove_chaos_section(path: os.PathLike | str) -> bool:
    """Strip the poecraft highlight section from a .filter file.

    Returns True if a section was present and removed, False if there was
    nothing to remove (file left unchanged).
    """
    content = read_filter(path)
    before, section, after = split_filter(content)
    if not section:
        return False
    write_filter(path, f"{before}{after}")
    return True
