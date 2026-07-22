"""Item classes, recipe types, and game constants for Path of Exile."""

from __future__ import annotations
from enum import Enum


class ItemClass(str, Enum):
    HELMETS = "Helmets"
    BODY_ARMOURS = "BodyArmours"
    GLOVES = "Gloves"
    BOOTS = "Boots"
    RINGS = "Rings"
    AMULETS = "Amulets"
    BELTS = "Belts"
    ONE_HAND_WEAPONS = "OneHandWeapons"
    TWO_HAND_WEAPONS = "TwoHandWeapons"


class RecipeType(str, Enum):
    CHAOS = "chaos"
    REGAL = "regal"
    CHANCE = "chance"
    EXALTED = "exalted"


RECIPE_ILVL_RANGES: dict[RecipeType, tuple[int, int]] = {
    RecipeType.CHAOS: (60, 74),
    RecipeType.REGAL: (75, 999),
    RecipeType.CHANCE: (1, 59),
    RecipeType.EXALTED: (60, 999),
}


class FrameType(int, Enum):
    NORMAL = 0
    MAGIC = 1
    RARE = 2
    UNIQUE = 3
    GEM = 4
    CURRENCY = 5
    DIVINATION_CARD = 6
    QUEST = 8
    PROPHECY = 10
    RELIC = 9


ICON_CLASS_MAP: dict[str, ItemClass] = {
    "Helmets": ItemClass.HELMETS,
    "Gloves": ItemClass.GLOVES,
    "Boots": ItemClass.BOOTS,
    "BodyArmours": ItemClass.BODY_ARMOURS,
    "Rings": ItemClass.RINGS,
    "Amulets": ItemClass.AMULETS,
    "Belts": ItemClass.BELTS,
    "OneHandWeapons": ItemClass.ONE_HAND_WEAPONS,
    "TwoHandWeapons": ItemClass.TWO_HAND_WEAPONS,
}

CATEGORY_CLASS_MAP: dict[str, ItemClass] = {
    "ring": ItemClass.RINGS,
    "amulet": ItemClass.AMULETS,
    "belt": ItemClass.BELTS,
    "helm": ItemClass.HELMETS,
    "helmet": ItemClass.HELMETS,
    "gloves": ItemClass.GLOVES,
    "boots": ItemClass.BOOTS,
    "chest": ItemClass.BODY_ARMOURS,
    "body": ItemClass.BODY_ARMOURS,
    "weapon": ItemClass.ONE_HAND_WEAPONS,
}

TWO_HAND_WEAPON_TYPES = {
    "TwoHandWeapons", "Two Hand Axes", "Two Hand Maces",
    "Two Hand Swords", "Staves", "Warstaves", "Bows",
}

ONE_HAND_WEAPON_TYPES = {
    "OneHandWeapons", "One Hand Axes", "One Hand Maces",
    "One Hand Swords", "Daggers", "Claws", "Wands",
    "Sceptres", "Shields",
}

CHAOS_RECIPE_SLOTS = {
    ItemClass.RINGS, ItemClass.AMULETS, ItemClass.BELTS,
    ItemClass.HELMETS, ItemClass.GLOVES, ItemClass.BOOTS,
    ItemClass.BODY_ARMOURS,
}

ALL_RECIPE_CLASSES = CHAOS_RECIPE_SLOTS | {
    ItemClass.ONE_HAND_WEAPONS, ItemClass.TWO_HAND_WEAPONS,
}

# Per-class item counts required for ONE full recipe set. The composition is
# identical across recipe types (chaos/regal/chance/exalted); only the ilvl
# ranges differ (see RECIPE_ILVL_RANGES).
RECIPE_SET_REQUIREMENTS: dict[ItemClass, int] = {
    ItemClass.RINGS: 2,
    ItemClass.AMULETS: 1,
    ItemClass.BELTS: 1,
    ItemClass.HELMETS: 1,
    ItemClass.GLOVES: 1,
    ItemClass.BOOTS: 1,
    ItemClass.BODY_ARMOURS: 1,
}

# The weapon slot is shared by one-hand and two-hand weapons and is satisfied
# by EITHER two one-hand weapons OR one two-hand weapon. A two-hand weapon
# contributes 2 units (fills the slot alone); a one-hand weapon contributes 1.
WEAPON_SLOT_REQUIRED_UNITS = 2
