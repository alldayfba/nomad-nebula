#!/usr/bin/env python3
from __future__ import annotations
"""
Script: filter_presets.py
Purpose: Pre-configured filter profiles for different seller experience levels.

         Market research shows complexity is the #1 barrier to OA tool adoption.
         Presets eliminate decision fatigue for students.

Usage:
    from execution.filter_presets import get_preset, PRESETS
    preset = get_preset("beginner")
    # Pass preset values to catalog_pipeline.run_pipeline(**preset)
"""


# ── Presets ──────────────────────────────────────────────────────────────────

PRESETS = {
    "beginner": {
        "description": "Safe picks only — high ROI, ungated brands, proven sellers. "
                       "Lower risk, fewer results, higher confidence per deal.",
        "min_roi": 30.0,
        "min_profit": 5.0,
        "max_bsr": 100000,
        "max_price": 50.0,     # Keep buy cost low to limit risk
        "min_sellers": 2,      # Avoid PL/single-seller listings
        "max_sellers": 12,     # Avoid overcrowded listings
        "min_monthly_sales": 20,
        "no_amazon": True,     # Don't compete with Amazon
        "strict": True,        # Only show products that pass ALL filters
        "verify_links": False,
    },

    "intermediate": {
        "description": "Balanced — good margins with moderate risk tolerance. "
                       "More results, some may need verification.",
        "min_roi": 20.0,
        "min_profit": 3.0,
        "max_bsr": 200000,
        "max_price": 0,        # No cap
        "min_sellers": 0,
        "max_sellers": 15,
        "min_monthly_sales": 10,
        "no_amazon": False,    # Show but flag Amazon listings
        "strict": False,       # Tag, don't drop
        "verify_links": False,
    },

    "advanced": {
        "description": "Everything with positive margin — maximum deal flow. "
                       "Includes thin margins, slow movers, gated brands. You filter manually.",
        "min_roi": 10.0,
        "min_profit": 2.0,
        "max_bsr": 500000,
        "max_price": 0,        # No cap
        "min_sellers": 0,
        "max_sellers": 0,      # No filter
        "min_monthly_sales": 0, # No filter
        "no_amazon": False,
        "strict": False,
        "verify_links": False,
    },

    "high_ticket": {
        "description": "High-value items ($50+ buy price) with big dollar profit. "
                       "Fewer deals but $20-$100+ profit per unit.",
        "min_roi": 15.0,
        "min_profit": 15.0,
        "max_bsr": 300000,
        "max_price": 0,
        "min_price": 50.0,
        "min_sellers": 0,
        "max_sellers": 10,
        "min_monthly_sales": 5,
        "no_amazon": False,
        "strict": False,
        "verify_links": False,
    },

    "fast_flips": {
        "description": "Low-price, high-velocity products that sell fast. "
                       "Quick turns, lower profit per unit but high volume.",
        "min_roi": 25.0,
        "min_profit": 3.0,
        "max_bsr": 50000,      # Fast movers only
        "max_price": 30.0,     # Cheap items
        "min_sellers": 2,
        "max_sellers": 8,
        "min_monthly_sales": 50,
        "no_amazon": True,
        "strict": True,
        "verify_links": False,
    },
}


def get_preset(name: str) -> dict:
    """Get filter preset by name.

    Args:
        name: Preset name (beginner, intermediate, advanced, high_ticket, fast_flips).

    Returns:
        Dict of filter parameters ready to pass to run_pipeline().

    Raises:
        ValueError if preset name not found.
    """
    name = name.lower().strip()
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")

    preset = PRESETS[name].copy()
    # Remove description — not a pipeline parameter
    preset.pop("description", None)
    return preset


def list_presets() -> str:
    """Return formatted string of all available presets."""
    lines = []
    for name, config in PRESETS.items():
        desc = config.get("description", "")
        roi = config.get("min_roi", 0)
        profit = config.get("min_profit", 0)
        bsr = config.get("max_bsr", 0)
        lines.append(f"  {name:<15} ROI>{roi}% Profit>${profit} BSR<{bsr:,}")
        lines.append(f"                 {desc}")
        lines.append("")
    return "\n".join(lines)
