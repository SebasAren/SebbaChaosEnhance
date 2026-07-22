"""Item classifier - derives item class from PoE CDN icon URLs.

The PoE API does not directly return item classes (Helmet, Ring, etc.).
Each item has an icon URL containing base64-encoded metadata that we
decode to determine the item class.

Icon URL format (5th path segment is base64-encoded JSON):
    [25,14,{"f":"2DItems/Rings/TopazSapphire","w":1,"h":1,"scale":1}]

The "f" field path split by "/" gives:
    index 1: "Rings", "Amulets", "Belts", "Weapons", "Armours"
    index 2: sub-type for Weapons/Armours (e.g. "Boots", "Helmets")
"""

from __future__ import annotations

import base64
import json
import logging

from poecraft.recipe.types import (
    CATEGORY_CLASS_MAP,
    ICON_CLASS_MAP,
    ONE_HAND_WEAPON_TYPES,
    TWO_HAND_WEAPON_TYPES,
    ItemClass,
)

logger = logging.getLogger(__name__)


def classify_from_icon(icon_url: str) -> ItemClass | None:
    """Derive item class from a PoE CDN icon URL."""
    if not icon_url:
        return None

    try:
        parts = [p for p in icon_url.split("/") if p]

        if len(parts) < 5:
            return None

        encoded = parts[4]
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding

        decoded_bytes = base64.b64decode(encoded)
        decoded_str = decoded_bytes.decode("utf-8")
        metadata = json.loads(decoded_str)

        if isinstance(metadata, list) and len(metadata) >= 3:
            file_path = metadata[2].get("f", "")
        else:
            return None

        path_parts = [p for p in file_path.split("/") if p]

        if len(path_parts) < 2:
            return None

        category = path_parts[1]

        # Direct matches: Rings, Amulets, Belts
        if category in ICON_CLASS_MAP:
            return ICON_CLASS_MAP[category]

        # For Armours and Weapons, check the sub-type (index 2)
        if category in ("Armours", "Weapons") and len(path_parts) >= 3:
            sub_type = path_parts[2]
            if sub_type in TWO_HAND_WEAPON_TYPES:
                return ItemClass.TWO_HAND_WEAPONS
            elif sub_type in ONE_HAND_WEAPON_TYPES:
                return ItemClass.ONE_HAND_WEAPONS
            elif sub_type in ICON_CLASS_MAP:
                return ICON_CLASS_MAP[sub_type]
            elif sub_type == "Shields":
                return ItemClass.ONE_HAND_WEAPONS

        return None

    except Exception as e:
        logger.warning("Failed to classify icon: %s - %s", icon_url[:80], e)
        return None


def classify_from_category(category: dict) -> ItemClass | None:
    """Derive item class from the API 'category' field.

    Category is a dict like {"ring": []} or {"armour": ["helmet"]}.
    """
    if not category:
        return None

    for key, subtypes in category.items():
        key_lower = key.lower()

        if key_lower in CATEGORY_CLASS_MAP:
            if key_lower == "weapon" and subtypes:
                subtype_str = " ".join(subtypes).lower()
                if any(t.lower() in subtype_str for t in TWO_HAND_WEAPON_TYPES):
                    return ItemClass.TWO_HAND_WEAPONS
                return ItemClass.ONE_HAND_WEAPONS
            return CATEGORY_CLASS_MAP[key_lower]

        if key_lower in ("armour", "armor") and subtypes:
            for st in subtypes:
                st_lower = st.lower()
                if st_lower in ("helmet", "helm"):
                    return ItemClass.HELMETS
                elif st_lower == "gloves":
                    return ItemClass.GLOVES
                elif st_lower == "boots":
                    return ItemClass.BOOTS
                elif st_lower in ("chest", "body", "bodyarmour"):
                    return ItemClass.BODY_ARMOURS
                elif st_lower == "shield":
                    return ItemClass.ONE_HAND_WEAPONS

    return None


def classify_item(item_data: dict) -> ItemClass | None:
    """Classify an item using icon URL and category data.

    Prefers icon-based classification (more reliable).
    Falls back to category-based classification.
    """
    icon = item_data.get("icon", "")
    category = item_data.get("category", {})

    result = classify_from_icon(icon)
    if result:
        return result

    result = classify_from_category(category)
    if result:
        return result

    logger.debug(
        "Could not classify item: name=%s, typeLine=%s",
        item_data.get("name", "?"),
        item_data.get("typeLine", "?"),
    )
    return None
