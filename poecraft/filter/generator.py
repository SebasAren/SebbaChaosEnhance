"""Loot-filter rule generation: Show rules highlighting missing recipe classes.

Highlight-only behavior: emit exactly one Show rule per missing item class
with a strong style (background/text/border color, MinimapIcon, PlayEffect).
Never emit Hide. Classes that aren't missing are left to the user's filter.
"""

from __future__ import annotations

from poecraft.filter.reader import MARKER_END, MARKER_START
from poecraft.recipe.types import RECIPE_ILVL_RANGES, ItemClass, RecipeType

# Definition order of ItemClass, used for deterministic rule ordering.
_CLASS_ORDER: dict[ItemClass, int] = {cls: i for i, cls in enumerate(ItemClass)}


# Per-slot highlight palette. Each entry maps to a {bg, text, border} style.
# Jewelry (rings/amulets/belts) all share red: they are the rarest recipe
# pieces and the most important to spot on the ground, so one strong color
# makes them pop. Every other slot gets a distinct color so a quick glance
# tells you which armor/weapon piece a set is still missing.
_RED = {"bg": "#D0021BFF", "text": "#FFFFFFFF", "border": "#D0021BFF"}
_BLUE = {"bg": "#2D7FF9FF", "text": "#FFFFFFFF", "border": "#2D7FF9FF"}
_GREEN = {"bg": "#34A853FF", "text": "#FFFFFFFF", "border": "#34A853FF"}
_MAGENTA = {"bg": "#C3409FFF", "text": "#FFFFFFFF", "border": "#C3409FFF"}
_PURPLE = {"bg": "#7B1FA2FF", "text": "#FFFFFFFF", "border": "#7B1FA2FF"}
_ORANGE = {"bg": "#FF9600FF", "text": "#FFFFFFFF", "border": "#FF9600FF"}
_TEAL = {"bg": "#0097A7FF", "text": "#FFFFFFFF", "border": "#0097A7FF"}

CLASS_COLORS: dict[ItemClass, dict[str, str]] = {
    ItemClass.RINGS: _RED,
    ItemClass.AMULETS: _RED,
    ItemClass.BELTS: _RED,
    ItemClass.HELMETS: _BLUE,
    ItemClass.GLOVES: _GREEN,
    ItemClass.BOOTS: _MAGENTA,
    ItemClass.BODY_ARMOURS: _PURPLE,
    ItemClass.ONE_HAND_WEAPONS: _ORANGE,
    ItemClass.TWO_HAND_WEAPONS: _TEAL,
}

# The full argument emitted after `Class ` for each item class. Every class
# is quoted (PoE requires quotes for multi-word names like "Body Armours").
# Weapons are enumerated explicitly: PoE has no "One Hand Weapons" or
# "Two Hand Weapons" item class, so a substring like "One Hand" would miss
# Daggers/Wands/Sceptres/Bows/Staves. Mirrors ChaosRecipeEnhancer's managers.
CLASS_FILTER_NAMES: dict[ItemClass, str] = {
    ItemClass.RINGS: '"Rings"',
    ItemClass.AMULETS: '"Amulets"',
    ItemClass.BELTS: '"Belts"',
    ItemClass.HELMETS: '"Helmets"',
    ItemClass.GLOVES: '"Gloves"',
    ItemClass.BOOTS: '"Boots"',
    ItemClass.BODY_ARMOURS: '"Body Armours"',
    ItemClass.ONE_HAND_WEAPONS: (
        '"Daggers" "One Hand Axes" "One Hand Maces" "One Hand Swords" '
        '"Rune Daggers" "Sceptres" "Thrusting One Hand Swords" "Wands" '
        '"Claws" "Shields"'
    ),
    ItemClass.TWO_HAND_WEAPONS: (
        '"Two Hand Swords" "Two Hand Axes" "Two Hand Maces" "Staves" "Warstaves" "Bows"'
    ),
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
    needs_lower_level: bool = True,
) -> str:
    """Generate a single highlight Show rule for one missing item class.

    The rule highlights (never hides) the given class with a strong style.
    ``include_identified=False`` emits an ``Identified False`` filter line so
    only unidentified rares match; setting it True omits that line entirely.

    ``needs_lower_level`` gates the chaos recipe's ``ItemLevel`` upper bound:
    when False (the stash has enough items), the upper bound is dropped so the
    filter broadens to ilvl 60+ and catches higher drops — e.g. ilvl 75
    boss/rare-monster drops in an ilvl 73 map. Mirrors CRE's NeedsLowerLevel.
    Other recipe types are unaffected.
    """
    colors = CLASS_COLORS[item_class]
    low, high = RECIPE_ILVL_RANGES[recipe_type]
    class_arg = CLASS_FILTER_NAMES[item_class]

    lines: list[str] = ["Show"]
    lines.append(f"Class {class_arg}")
    lines.append("Rarity Rare")
    if not include_identified:
        lines.append("Identified False")
    lines.append(f"ItemLevel >= {low}")
    # Chaos recipe: cap the upper bound only when we specifically need more
    # chaos-range (ilvl 60-74) items. With enough items, broaden to ilvl 60+.
    if recipe_type != RecipeType.CHAOS or needs_lower_level:
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
    needs_lower_level: bool = True,
) -> str:
    """Generate the marker-wrapped highlight section for missing classes.

    Emits exactly one Show rule per missing class (never Hide), wrapped in
    MARKER_START/MARKER_END. Rules are ordered by ItemClass enum definition
    for deterministic output. An empty ``missing_classes`` set still yields
    the marker wrapper with no rules in between. ``needs_lower_level`` is
    forwarded to each rule (see :func:`generate_rule`).
    """
    body = "\n\n".join(
        generate_rule(cls, recipe_type, include_identified, needs_lower_level)
        for cls in sorted(missing_classes, key=lambda c: _CLASS_ORDER[c])
    )
    if body:
        return f"{MARKER_START}\n{body}\n{MARKER_END}\n"
    return f"{MARKER_START}\n{MARKER_END}\n"
