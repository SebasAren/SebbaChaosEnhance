"""Loot-filter rule generation: Show rules highlighting missing recipe classes.

Highlight-only behavior: emit exactly one Show rule per missing item class
with a strong style (background/text/border color, MinimapIcon, PlayEffect).
Never emit Hide. Classes that aren't missing are left to the user's filter.
"""

from __future__ import annotations

from poecraft.recipe.types import ItemClass, RecipeType, RECIPE_ILVL_RANGES
from poecraft.filter.reader import MARKER_END, MARKER_START


# Definition order of ItemClass, used for deterministic rule ordering.
_CLASS_ORDER: dict[ItemClass, int] = {
    cls: i for i, cls in enumerate(ItemClass)
}


CLASS_COLORS: dict[ItemClass, dict[str, str]] = {
    ItemClass.RINGS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.AMULETS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.BELTS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.HELMETS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.GLOVES: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.BOOTS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.BODY_ARMOURS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.ONE_HAND_WEAPONS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
    ItemClass.TWO_HAND_WEAPONS: {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"},
}

CLASS_FILTER_NAMES: dict[ItemClass, str] = {
    ItemClass.RINGS: "Rings",
    ItemClass.AMULETS: "Amulets",
    ItemClass.BELTS: "Belts",
    ItemClass.HELMETS: "Helmets",
    ItemClass.GLOVES: "Gloves",
    ItemClass.BOOTS: "Boots",
    ItemClass.BODY_ARMOURS: "Body Armours",
    ItemClass.ONE_HAND_WEAPONS: "One Hand Weapons",
    ItemClass.TWO_HAND_WEAPONS: "Two Hand Weapons",
}

DEFAULT_STYLE: list[str] = [
    "HasInfluence None",
    "Sockets < 6",
    "LinkedSockets < 5",
]


def _parse_hex(hex_color: str) -> tuple[int, int, int, int]:
    """Parse an '#RRGGBBAA' hex color into an (r, g, b, a) int tuple.

    Accepts an optional leading '#'. Channels are two hex digits each.
    """
    value = hex_color.lstrip("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    a = int(value[6:8], 16)
    return (r, g, b, a)


def _fmt_color(hex_color: str) -> str:
    """Format an RGBA hex color as the space-separated PoE filter form."""
    r, g, b, a = _parse_hex(hex_color)
    return f"{r} {g} {b} {a}"


def generate_rule(
    item_class: ItemClass,
    recipe_type: RecipeType,
    include_identified: bool = False,
) -> str:
    """Generate a single highlight Show rule for one missing item class.

    The rule highlights (never hides) the given class with a strong style.
    ``include_identified=False`` emits an ``Identified False`` filter line so
    only unidentified rares match; setting it True omits that line entirely.
    """
    colors = CLASS_COLORS[item_class]
    low, high = RECIPE_ILVL_RANGES[recipe_type]
    name = CLASS_FILTER_NAMES[item_class]

    lines: list[str] = ["Show"]
    lines.append(f'Class "{name}"')
    lines.append("Rarity Rare")
    if not include_identified:
        lines.append("Identified False")
    lines.append(f"ItemLevel >= {low}")
    lines.append(f"ItemLevel <= {high}")
    lines.extend(DEFAULT_STYLE)
    lines.append(f"SetBackgroundColor {_fmt_color(colors['bg'])}")
    lines.append(f"SetTextColor {_fmt_color(colors['text'])}")
    lines.append(f"SetBorderColor {_fmt_color(colors['border'])}")
    lines.append("SetFontSize 40")
    lines.append("MinimapIcon 0 Yellow Circle")
    lines.append("PlayEffect Yellow Temp")
    return "\n".join(lines)


def generate_section(
    missing_classes: set[ItemClass],
    recipe_type: RecipeType,
    include_identified: bool = False,
) -> str:
    """Generate the marker-wrapped highlight section for missing classes.

    Emits exactly one Show rule per missing class (never Hide), wrapped in
    MARKER_START/MARKER_END. Rules are ordered by ItemClass enum definition
    for deterministic output. An empty ``missing_classes`` set still yields
    the marker wrapper with no rules in between.
    """
    body = "\n\n".join(
        generate_rule(cls, recipe_type, include_identified)
        for cls in sorted(missing_classes, key=_CLASS_ORDER.get)
    )
    if body:
        return f"{MARKER_START}\n{body}\n{MARKER_END}\n"
    return f"{MARKER_START}\n{MARKER_END}\n"
