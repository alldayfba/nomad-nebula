#!/usr/bin/env python3
from __future__ import annotations
"""
Script: gating_checker.py
Purpose: Check if a brand/category is likely gated (restricted) on Amazon.

         Uses a curated database of known restricted brands + categories.
         Returns risk level: high/medium/low/none.

         Integrated into catalog_pipeline.py as a smart filter.
"""

# ── Known Restricted Brands (Amazon enforces these broadly) ──────────────────

# Source: Amazon Seller Central restricted brands list + community knowledge
# High = almost always gated for new sellers
# Medium = sometimes gated, depends on account age/history

GATED_BRANDS_HIGH = {
    # Electronics
    "apple", "samsung", "sony", "bose", "beats", "jbl", "gopro", "dyson",
    "lg", "microsoft", "google", "amazon", "kindle", "ring", "nest",
    # Luxury / Fashion
    "gucci", "louis vuitton", "chanel", "prada", "burberry", "versace",
    "dior", "hermes", "fendi", "balenciaga", "yves saint laurent",
    "coach", "michael kors", "kate spade", "tory burch", "ray-ban",
    # Sports / Apparel (frequently gated)
    "nike", "adidas", "under armour", "the north face", "patagonia",
    "lululemon", "yeti",
    # Toys (often gated Q4)
    "lego", "hasbro", "mattel", "disney", "pokemon", "nintendo",
    "marvel", "star wars", "barbie", "hot wheels",
    # Health / Beauty
    "olay", "neutrogena", "l'oreal", "maybelline", "clinique",
    "estee lauder", "mac cosmetics", "nars", "too faced",
    # Baby
    "graco", "chicco", "baby jogger", "uppababy",
    # Auto
    "bosch", "denso",
}

GATED_BRANDS_MEDIUM = {
    # Frequently restricted but not always
    "jordan", "puma", "new balance", "reebok", "asics", "converse",
    "vans", "skechers", "columbia", "champion", "fila",
    "calvin klein", "tommy hilfiger", "ralph lauren", "polo",
    "levi's", "levis", "wrangler",
    "revlon", "garnier", "dove", "pantene", "head & shoulders",
    "crest", "oral-b", "gillette", "braun",
    "kitchenaid", "cuisinart", "keurig", "nespresso",
    "dewalt", "makita", "milwaukee", "ryobi", "craftsman",
    "weber", "traeger",
    "fisher-price", "melissa & doug", "vtech", "leapfrog",
    "nerf", "transformers", "my little pony",
    "energizer", "duracell",
    "crocs", "birkenstock", "dr. martens",
    "oakley", "costa del mar",
}

# Categories that are frequently restricted
GATED_CATEGORIES = {
    "high": {
        "grocery", "grocery & gourmet food",
        "fine art",
        "watches", "luxury watches",
        "collectible coins",
        "streaming media players",
        "personal safety and security",
    },
    "medium": {
        "beauty", "luxury beauty", "professional beauty",
        "health & personal care", "health and personal care",
        "baby", "baby products",
        "clothing", "clothing, shoes & jewelry",
        "toys & games", "toys",
        "sports collectibles",
        "music", "music instruments",
        "automotive", "automotive parts & accessories",
    },
}


def check_gating(brand: str, category: str = "") -> dict:
    """Check if a brand/category is likely gated on Amazon.

    Args:
        brand: Product brand name.
        category: Amazon category (optional).

    Returns:
        dict with gating_risk ("high"/"medium"/"low"/"none"),
        reason, and recommendations.
    """
    brand_lower = brand.lower().strip() if brand else ""
    cat_lower = category.lower().strip() if category else ""

    # Check brand
    if brand_lower in GATED_BRANDS_HIGH:
        return {
            "gating_risk": "high",
            "reason": f"Brand '{brand}' is frequently restricted on Amazon",
            "recommendation": "Verify ungating status before purchasing. Apply for brand approval in Seller Central.",
        }

    if brand_lower in GATED_BRANDS_MEDIUM:
        return {
            "gating_risk": "medium",
            "reason": f"Brand '{brand}' is sometimes restricted — depends on account history",
            "recommendation": "Check your Seller Central for approval status. Newer accounts are more likely gated.",
        }

    # Check category
    for cat_gated in GATED_CATEGORIES.get("high", set()):
        if cat_gated in cat_lower:
            return {
                "gating_risk": "medium",  # Category gating is less certain than brand
                "reason": f"Category '{category}' is frequently restricted",
                "recommendation": "Category may require approval. Check Seller Central.",
            }

    for cat_gated in GATED_CATEGORIES.get("medium", set()):
        if cat_gated in cat_lower:
            return {
                "gating_risk": "low",
                "reason": f"Category '{category}' is sometimes restricted for new sellers",
                "recommendation": "Usually accessible for established accounts.",
            }

    return {
        "gating_risk": "none",
        "reason": "",
        "recommendation": "",
    }


def is_likely_gated(brand: str, category: str = "") -> bool:
    """Quick check — returns True if brand/category is high or medium risk."""
    result = check_gating(brand, category)
    return result["gating_risk"] in ("high", "medium")
