#!/usr/bin/env python3
"""
Script: calculate_fba_profitability.py
Purpose: Calculate FBA profitability for matched products (fees, ROI, profit margin, verdict)
Inputs:  --input (JSON with Amazon matches), --output (JSON with profitability),
         --min-roi (%), --min-profit ($), --max-price ($), --shipping-cost ($),
         --cashback-percent (%), --coupon-discount ($), --auto-cashback
Outputs: JSON with profitability calculations, filtered and ranked by ROI
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ─── Amazon Referral Fee Rates by Category ───────────────────────────────────
# Source: https://sellercentral.amazon.com/help/hub/reference/GTG4BAWSY39Z98Z3
# Updated: 2026-02 (update quarterly)
REFERRAL_FEE_RATES = {
    "default": 0.15,
    "Amazon Device Accessories": 0.45,
    "Appliances": 0.15,
    "Arts, Crafts & Sewing": 0.15,
    "Automotive": 0.12,
    "Baby Products": 0.08,
    "Beauty": 0.08,
    "Books": 0.15,
    "Camera & Photo": 0.08,
    "Cell Phones & Accessories": 0.08,
    "Clothing & Accessories": 0.17,
    "Clothing, Shoes & Jewelry": 0.17,
    "Computers": 0.08,
    "Electronics": 0.08,
    "Grocery & Gourmet Food": 0.08,
    "Health & Household": 0.08,
    "Health & Personal Care": 0.08,
    "Home & Garden": 0.15,
    "Home & Kitchen": 0.15,
    "Industrial & Scientific": 0.12,
    "Jewelry": 0.20,
    "Kitchen & Dining": 0.15,
    "Musical Instruments": 0.15,
    "Office Products": 0.15,
    "Patio, Lawn & Garden": 0.15,
    "Pet Supplies": 0.15,
    "Software": 0.15,
    "Sports & Outdoors": 0.15,
    "Tools & Home Improvement": 0.15,
    "Toys & Games": 0.15,
    "Video Games": 0.15,
    "Watches": 0.16,
}

# ─── FBA Fulfillment Fee Estimates (by sell price bracket) ────────────────────
# Simplified when weight/dimensions aren't known.
# Conservative estimates — rounds UP to protect profit calculations.
FBA_FEE_BY_PRICE = [
    (10, 3.22),     # items under $10 (updated 2026-02)
    (15, 3.40),     # $10-15
    (20, 4.08),     # $15-20
    (25, 4.55),     # $20-25
    (30, 5.00),     # $25-30
    (40, 5.25),     # $30-40
    (50, 5.50),     # $40-50
    (75, 6.00),     # $50-75
    (100, 6.75),    # $75-100
    (150, 7.50),    # $100-150
    (999999, 8.25), # $150+
]

# ─── BSR (Best Sellers Rank) → Estimated Monthly Sales ───────────────────────
# Based on publicly available research (Jungle Scout, etc.)
# Very rough — varies by category. These are for "average" categories.
BSR_TO_MONTHLY_SALES = [
    (50, 5000),
    (100, 3000),
    (200, 2000),
    (500, 1200),
    (1000, 800),
    (2000, 500),
    (5000, 250),
    (10000, 120),
    (20000, 75),
    (50000, 40),
    (100000, 20),
    (200000, 10),
    (500000, 5),
    (1000000, 2),
    (999999999, 1),
]

# ─── Category-Specific BSR Multipliers ────────────────────────────────────────
# Adjusts base BSR_TO_MONTHLY_SALES estimates per category.
# >1.0 = category sells faster than average; <1.0 = slower.
BSR_CATEGORY_MULTIPLIERS = {
    "Toys & Games": 1.5,
    "Grocery & Gourmet Food": 1.8,
    "Health & Personal Care": 1.3,
    "Beauty": 1.3,
    "Home & Kitchen": 0.9,
    "Sports & Outdoors": 1.0,
    "Books": 0.7,
    "Electronics": 1.2,
    "Office Products": 0.8,
    "Pet Supplies": 1.1,
    "Baby": 1.2,
    "Clothing": 0.6,
}

# ─── Retailer Cashback Estimates (Rakuten approximate rates) ─────────────────
RETAILER_CASHBACK_ESTIMATES = {
    "Walmart": 3.0, "Target": 2.0, "Home Depot": 2.0, "CVS": 3.0,
    "Walgreens": 3.0, "Costco": 1.0, "Kohl's": 4.0, "Best Buy": 1.0,
    "Staples": 3.0, "Office Depot": 3.0, "BJ's": 1.0, "Sam's Club": 1.0,
    "Lowe's": 1.0, "Macy's": 2.5, "Ulta Beauty": 2.0,
    "Dick's Sporting Goods": 2.0, "Kroger": 1.0, "Vitamin Shoppe": 3.0,
    "GNC": 2.0, "Nordstrom": 2.0, "Wayfair": 2.0, "Overstock": 2.0,
    "Big Lots": 1.0, "GameStop": 1.0, "Academy Sports": 2.0,
    "Petco": 2.0, "PetSmart": 2.0, "Newegg": 1.0, "Sierra": 2.0,
    "Tractor Supply": 1.0, "At Home": 1.0, "World Market": 2.0,
    "Crate & Barrel": 2.0, "Pottery Barn": 2.0, "West Elm": 2.0,
    "Williams Sonoma": 2.0, "Sur La Table": 2.0, "Carter's": 2.0,
    "OshKosh B'gosh": 2.0, "Old Navy": 2.0, "Gap": 2.0,
    "Banana Republic": 2.0, "JCPenney": 2.0, "Belk": 2.0,
    "American Eagle": 2.0, "Urban Outfitters": 2.0, "PacSun": 2.0,
    "Michaels": 1.0, "Joann": 1.0, "Party City": 1.0, "DSW": 2.0,
    "Shoe Carnival": 1.0, "Famous Footwear": 2.0, "REI": 2.0,
    "Cabela's": 1.0, "Bass Pro Shops": 1.0, "Journeys": 1.0,
    # Expansion retailers with cashback
    "Sephora": 2.0, "Sally Beauty": 2.0, "Dermstore": 3.0, "ColourPop": 2.0,
    "e.l.f. Cosmetics": 2.0, "Bath & Body Works": 2.0, "Lookfantastic": 3.0,
    "FragranceNet": 3.0, "L'Occitane": 3.0, "iHerb": 2.0, "Thrive Market": 1.0,
    "Chewy": 2.0, "EntirelyPets": 2.0, "1-800-PetMeds": 2.0,
    "Adorama": 1.0, "Monoprice": 2.0, "Dell": 2.0, "HP": 2.0, "Lenovo": 3.0,
    "Abt Electronics": 1.0, "Backcountry": 3.0, "Moosejaw": 3.0,
    "Eastern Mountain Sports": 2.0, "Running Warehouse": 2.0,
    "Sportsman's Warehouse": 1.0, "Soccer.com": 2.0, "Golf Galaxy": 2.0,
    "Foot Locker": 2.0, "Finish Line": 2.0, "6pm": 2.0, "Shoebacca": 2.0,
    "New Balance": 2.0, "Skechers": 2.0, "Entertainment Earth": 2.0,
    "Fat Brain Toys": 2.0, "Barnes & Noble": 2.0, "Nordstrom Rack": 2.0,
    "Saks Off 5th": 2.0, "Neiman Marcus Last Call": 2.0,
    "ASOS": 3.0, "SHEIN": 2.0, "H&M": 2.0, "Express": 3.0, "Forever 21": 2.0,
    "Abercrombie & Fitch": 2.0, "Hollister": 2.0, "Torrid": 3.0,
    "Lane Bryant": 3.0, "Hot Topic": 2.0, "BoxLunch": 2.0,
    "Anthropologie": 2.0, "Free People": 2.0, "Dolls Kill": 2.0,
    "The Children's Place": 3.0, "Gymboree": 2.0, "Primary": 2.0,
    "buybuy BABY": 2.0, "Quill": 2.0, "Bulk Office Supply": 1.0,
    "Ace Hardware": 1.0, "Build.com": 2.0, "The Container Store": 2.0,
    "Kirkland's": 2.0, "Yankee Candle": 3.0, "Brookstone": 2.0,
    "Sharper Image": 2.0, "Oriental Trading": 3.0, "Houzz": 1.0,
    "Pier 1": 2.0, "Z Gallerie": 2.0, "Hayneedle": 1.0, "Boxed": 1.0,
    "Musician's Friend": 2.0, "Guitar Center": 1.0, "MidwayUSA": 1.0,
    "Swanson Vitamins": 3.0, "PureFormulas": 2.0, "Lucky Vitamin": 2.0,
    "FSA Store": 1.0, "AutoZone": 1.0, "Advance Auto Parts": 2.0,
    "Pep Boys": 1.0, "Gardener's Supply": 2.0,
}

# ─── Retailer Coupon Code Database ───────────────────────────────────────────
# Format: retailer_key_or_name → list of {code, discount_type, value, notes}
# discount_type: "percent" = % off total, "flat" = $ off, "min_order" = min $ for flat off
# Keep updated — check retailer sites and Honey/RetailMeNot quarterly.
RETAILER_COUPON_CODES = {
    "Vitacost": [
        {"code": "20FOODIE", "discount_type": "percent", "value": 20.0, "notes": "20% off, may have min order"},
        {"code": "25FOR814", "discount_type": "percent", "value": 25.0, "notes": "25% off flash code, rotates"},
    ],
    "Dr. Bronner's": [
        {"code": "20DOCBRON", "discount_type": "percent", "value": 20.0, "notes": "20% off brand-direct"},
    ],
    "Native": [
        {"code": "20SITEWIDE", "discount_type": "percent", "value": 20.0, "notes": "20% off native.com"},
    ],
    "Yankee Candle": [
        {"code": "SAVE20", "discount_type": "percent", "value": 20.0, "notes": "Check current promo, rotates"},
    ],
    "Bath & Body Works": [
        {"code": "SALE20", "discount_type": "percent", "value": 20.0, "notes": "Frequent 20% off codes"},
    ],
    "Fenty Beauty": [
        {"code": "FENTY10", "discount_type": "percent", "value": 10.0, "notes": "Check current promo"},
    ],
    "Jones Road Beauty": [
        {"code": "JRB15", "discount_type": "percent", "value": 15.0, "notes": "Check current promo"},
    ],
    "Jellycat": [
        {"code": None, "discount_type": "none", "value": 0.0, "notes": "No standard code — monitor sale section"},
    ],
    "Stylevana": [
        {"code": "STYLE10", "discount_type": "percent", "value": 10.0, "notes": "Check current promo, new user codes available"},
    ],
    "iHerb": [
        {"code": "CGN5136", "discount_type": "percent", "value": 5.0, "notes": "Referral code, 5% off"},
    ],
    "Oriental Trading": [
        {"code": "OTC25", "discount_type": "percent", "value": 25.0, "notes": "25% off, rotates"},
    ],
    "Quill": [
        {"code": "SAVE20", "discount_type": "percent", "value": 20.0, "notes": "Check current promo"},
    ],
}

# ─── FBM Fee Rates ────────────────────────────────────────────────────────────
# FBM: seller ships directly to buyer. No FBA fulfillment fee, but must cover
# your own shipping cost. Amazon still charges referral fee.
# Typical shipping costs for FBM (standard items, non-hazmat):
FBM_SHIPPING_ESTIMATES = [
    (10, 4.00),    # items under $10 sell price — use USPS First Class
    (20, 5.50),    # $10-20 — USPS Priority or Pirateship
    (30, 6.50),    # $20-30
    (50, 7.50),    # $30-50
    (75, 9.00),    # $50-75
    (100, 10.50),  # $75-100
    (999999, 13.00), # $100+
]

# ─── Gating, Hazmat, and IP Risk Data ────────────────────────────────────────
GATED_CATEGORIES = {
    "Grocery & Gourmet Food", "Jewelry", "Watches", "Dietary Supplements",
    "Collectible Coins", "Fine Art", "Sports Collectibles",
}

HAZMAT_KEYWORDS = [
    "lithium battery", "lithium-ion", "aerosol can", "flammable",
    "nail polish remover", "acetone", "solvent", "adhesive remover",
    "pesticide", "propane", "butane", "lighter fluid",
    "corrosive", "oxidizer", "compressed gas",
]

IP_RISK_BRANDS = [
    "Nike", "Adidas", "Apple", "Samsung", "Sony", "LEGO", "Disney",
    "Hasbro", "Mattel", "GoPro", "Bose", "Under Armour",
    "MAC", "Clinique", "Too Faced", "Funko",
]


# ─── Multi-pack Detection Patterns ───────────────────────────────────────────
MULTIPACK_PATTERNS = [
    r"(\d+)\s*-?\s*pack", r"pack\s*of\s*(\d+)", r"(\d+)\s*count",
    r"(\d+)\s*ct\b", r"set\s*of\s*(\d+)", r"(\d+)\s*piece",
    r"(\d+)\s*pk\b", r"bundle\s*of\s*(\d+)",
]

# Weight/volume normalization (all → oz for comparison)
WEIGHT_CONVERSIONS = {
    "oz": 1.0, "ounce": 1.0, "ounces": 1.0,
    "lb": 16.0, "lbs": 16.0, "pound": 16.0, "pounds": 16.0,
    "g": 0.03527, "gram": 0.03527, "grams": 0.03527,
    "kg": 35.274, "kilogram": 35.274,
    "fl oz": 1.0, "fl. oz": 1.0, "fluid ounce": 1.0,
    "ml": 0.03381, "milliliter": 0.03381,
    "l": 33.814, "liter": 33.814, "litre": 33.814,
    "gal": 128.0, "gallon": 128.0,
    "qt": 32.0, "quart": 32.0,
    "pt": 16.0, "pint": 16.0,
}

WEIGHT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(fl\.?\s*oz|fluid\s*ounce|ounces?|oz|lbs?|pounds?|grams?|kg|kilogram|"
    r"ml|milliliter|liters?|litres?|l\b|gal(?:lon)?|quarts?|qt|pints?|pt|g\b)",
    re.IGNORECASE,
)

# ─── Prep & Overhead Costs ──────────────────────────────────────────────────
# Per-unit costs for FBA prep (poly bag, label, bubble wrap, etc.)
PREP_COSTS = {
    "fnsku_label": 0.10,       # FNSKU barcode sticker
    "poly_bag": 0.15,          # required for many categories
    "bubble_wrap": 0.25,       # fragile items
    "default": 0.30,           # FNSKU label + poly bag (most common)
}

# Categories that typically require extra prep (bubble wrap, etc.)
EXTRA_PREP_CATEGORIES = {
    "Beauty", "Health & Personal Care", "Health & Household",
    "Grocery & Gourmet Food", "Baby Products", "Glass",
}

# ─── Sales Tax Rates by State ───────────────────────────────────────────────
# Top e-commerce states — used when auto_tax is enabled.
# These are averages (combined state + local). Set to your state.
STATE_SALES_TAX = {
    "CA": 8.68, "TX": 8.20, "NY": 8.52, "FL": 7.02, "WA": 10.25,
    "IL": 8.82, "PA": 6.34, "OH": 7.24, "NJ": 6.625, "NC": 6.98,
    "GA": 7.35, "MI": 6.0, "VA": 5.75, "AZ": 8.40, "TN": 9.55,
    "CO": 7.72, "IN": 7.0, "MO": 8.27, "WI": 5.43, "MN": 7.49,
    "none": 0.0,  # no tax (Delaware, Montana, Oregon, New Hampshire)
}

# ─── Monthly Storage Fee Estimates ──────────────────────────────────────────
# Amazon charges per cubic foot per month. Estimated per unit.
STORAGE_FEE_PER_UNIT = {
    "standard_jan_sep": 0.10,   # $0.87/cu ft → ~$0.10 for standard item
    "standard_oct_dec": 0.25,   # $2.40/cu ft → ~$0.25 for standard item (Q4 surge)
    "slow_mover_penalty": 0.50, # extra charge if BSR > 100K (slow seller)
}

# ─── Inbound Placement Fee ──────────────────────────────────────────────────
# Amazon added March 2024. Single FC rate (default).
# small_standard=$0.30, large_standard=$0.65, oversize=$1.50
INBOUND_PLACEMENT_FEE = {
    "small_standard": 0.30,
    "large_standard": 0.65,
    "oversize": 1.50,
    "default": 0.30,
}

# ─── Max BSR Threshold ──────────────────────────────────────────────────────
MAX_BSR_THRESHOLD = 500000  # Skip products above this BSR (practically dead)


def get_referral_fee_rate(category):
    """Get referral fee rate for a category. Defaults to 15%."""
    if not category:
        return REFERRAL_FEE_RATES["default"]
    # Try exact match first
    if category in REFERRAL_FEE_RATES:
        return REFERRAL_FEE_RATES[category]
    # Try partial match (category name might be a substring)
    category_lower = category.lower()
    for cat_name, rate in REFERRAL_FEE_RATES.items():
        if cat_name.lower() in category_lower or category_lower in cat_name.lower():
            return rate
    return REFERRAL_FEE_RATES["default"]


def estimate_fba_fee(sell_price):
    """Estimate FBA fulfillment fee based on price bracket."""
    if not sell_price or sell_price <= 0:
        return 5.00  # safe default
    for max_price, fee in FBA_FEE_BY_PRICE:
        if sell_price <= max_price:
            return fee
    return 8.50


def estimate_fbm_fee(sell_price):
    """Estimate FBM shipping cost based on sell price bracket.
    FBM has NO Amazon fulfillment fee — only referral fee + your shipping cost.
    Returns estimated self-ship cost (Pirateship/USPS ground advantage rates).
    """
    if not sell_price or sell_price <= 0:
        return 6.50  # safe default
    for max_price, fee in FBM_SHIPPING_ESTIMATES:
        if sell_price <= max_price:
            return fee
    return 13.00


def _resolve_coupon_code(product):
    """Look up best available coupon code for a retailer.

    Returns dict: {code, discount_type, value, notes} or None.
    Picks the highest-value code available.
    """
    retailer = product.get("retailer", "")
    if not retailer:
        return None
    # Exact match
    if retailer in RETAILER_COUPON_CODES:
        codes = [c for c in RETAILER_COUPON_CODES[retailer] if c.get("value", 0) > 0]
        if codes:
            return max(codes, key=lambda c: c["value"])
    # Partial match
    retailer_lower = retailer.lower()
    for name, codes in RETAILER_COUPON_CODES.items():
        if name.lower() in retailer_lower or retailer_lower in name.lower():
            active = [c for c in codes if c.get("value", 0) > 0]
            if active:
                return max(active, key=lambda c: c["value"])
    return None


def estimate_monthly_sales(sales_rank, category=None):
    """Estimate monthly sales from BSR with category-specific multiplier.
    Returns None if no rank."""
    if not sales_rank or sales_rank <= 0:
        return None
    base_sales = 1
    for max_rank, sales in BSR_TO_MONTHLY_SALES:
        if sales_rank <= max_rank:
            base_sales = sales
            break
    # Apply category multiplier if available
    if category:
        multiplier = _get_category_multiplier(category)
        return max(1, round(base_sales * multiplier))
    return base_sales


def _get_category_multiplier(category):
    """Look up BSR category multiplier. Falls back to 1.0."""
    if not category:
        return 1.0
    if category in BSR_CATEGORY_MULTIPLIERS:
        return BSR_CATEGORY_MULTIPLIERS[category]
    # Partial match
    category_lower = category.lower()
    for cat_name, mult in BSR_CATEGORY_MULTIPLIERS.items():
        if cat_name.lower() in category_lower or category_lower in cat_name.lower():
            return mult
    return 1.0


def score_competition(amazon_data):
    """Score competition risk from Amazon matching data."""
    fba_seller_count = amazon_data.get("fba_seller_count")
    amazon_on_listing = amazon_data.get("amazon_on_listing", False)

    warnings = []
    competition_score = "UNKNOWN"

    if amazon_on_listing:
        warnings.append("Amazon is a seller on this listing - Buy Box risk is high")
        competition_score = "HIGH_RISK"
    elif fba_seller_count is not None:
        if fba_seller_count <= 3:
            competition_score = "LOW"
        elif fba_seller_count <= 7:
            competition_score = "MODERATE"
        elif fba_seller_count <= 15:
            competition_score = "HIGH"
            warnings.append(f"{fba_seller_count} FBA sellers - crowded listing")
        else:
            competition_score = "SATURATED"
            warnings.append(f"{fba_seller_count} FBA sellers - listing is saturated, avoid")

    return competition_score, warnings


def check_restrictions(product_name, category, brand=None):
    """Check for gating, hazmat, and IP risk flags.

    Returns dict with:
        is_gated (bool), hazmat_risk (bool), ip_risk (bool),
        restriction_warnings (list of str)
    """
    warnings = []
    is_gated = False
    hazmat_risk = False
    ip_risk = False

    # Gated category check
    if category and category in GATED_CATEGORIES:
        is_gated = True
        warnings.append(f"Category '{category}' is gated - requires Amazon approval to sell")
    # Also partial match for gated categories
    if category and not is_gated:
        cat_lower = category.lower()
        for gated in GATED_CATEGORIES:
            if gated.lower() in cat_lower or cat_lower in gated.lower():
                is_gated = True
                warnings.append(f"Category '{category}' may be gated (matches '{gated}')")
                break

    # Hazmat keyword check
    name_lower = (product_name or "").lower()
    for keyword in HAZMAT_KEYWORDS:
        if keyword in name_lower:
            hazmat_risk = True
            warnings.append(f"Hazmat risk: product name contains '{keyword}'")
            break  # one match is enough

    # IP risk brand check — these brands aggressively file IP complaints
    # regardless of gating status. Being "auto-ungated" does NOT make them safe.
    combined_text = f"{product_name or ''} {brand or ''}".lower()
    for risky_brand in IP_RISK_BRANDS:
        if risky_brand.lower() in combined_text:
            ip_risk = True
            warnings.append(f"IP risk: '{risky_brand}' is known for filing IP complaints — avoid for arbitrage")
            break  # one match is enough

    return {
        "is_gated": is_gated,
        "hazmat_risk": hazmat_risk,
        "ip_risk": ip_risk,
        "restriction_warnings": warnings,
    }


def _extract_pack_quantity(title):
    """Extract pack/bundle quantity from a product title. Returns 1 if none found."""
    if not title:
        return 1
    title_lower = title.lower()
    for pattern in MULTIPACK_PATTERNS:
        match = re.search(pattern, title_lower)
        if match:
            qty = int(match.group(1))
            if 2 <= qty <= 200:  # sanity check — ignore "1 pack" or absurd numbers
                return qty
    return 1


def _extract_weight_oz(title):
    """Extract weight/volume from title, normalized to oz. Returns None if not found."""
    if not title:
        return None
    match = WEIGHT_PATTERN.search(title)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower().strip()
    # Normalize "fl. oz" variants
    if unit.startswith("fl"):
        unit = "fl oz"
    factor = WEIGHT_CONVERSIONS.get(unit)
    if not factor:
        return None
    return round(value * factor, 2)


def detect_multipack(retail_title, amazon_title):
    """Detect multi-pack/bundle mismatches between retail and Amazon listings.

    Returns dict with:
        retail_quantity (int), amazon_quantity (int),
        multipack_mismatch (bool), multipack_warning (str or None),
        cost_multiplier (float) — multiply retail price by this for true cost,
        retail_weight_oz (float or None), amazon_weight_oz (float or None)
    """
    retail_qty = _extract_pack_quantity(retail_title)
    amazon_qty = _extract_pack_quantity(amazon_title)
    retail_wt = _extract_weight_oz(retail_title)
    amazon_wt = _extract_weight_oz(amazon_title)

    mismatch = False
    warning = None
    cost_multiplier = 1.0

    # Check pack count mismatch
    if amazon_qty != retail_qty:
        mismatch = True
        cost_multiplier = amazon_qty / retail_qty
        warning = (f"Pack mismatch: Amazon={amazon_qty}-pack, Retail={retail_qty}-pack. "
                   f"Need {cost_multiplier:.1f}x retail units to fill 1 Amazon listing.")

    # Check weight/volume mismatch (only if pack counts matched or were both 1)
    elif retail_wt and amazon_wt and not mismatch:
        ratio = amazon_wt / retail_wt
        if ratio > 1.3 or ratio < 0.7:  # >30% difference = mismatch
            mismatch = True
            cost_multiplier = ratio
            warning = (f"Size mismatch: Amazon={amazon_wt}oz, Retail={retail_wt}oz. "
                       f"Cost multiplier: {ratio:.1f}x.")

    return {
        "retail_quantity": retail_qty,
        "amazon_quantity": amazon_qty,
        "retail_weight_oz": retail_wt,
        "amazon_weight_oz": amazon_wt,
        "multipack_mismatch": mismatch,
        "multipack_warning": warning,
        "cost_multiplier": cost_multiplier,
    }


def estimate_prep_cost(category=None, fragile=False):
    """Estimate per-unit FBA prep cost based on category.

    Default: $0.30 (FNSKU label + poly bag).
    Fragile or extra-prep categories add bubble wrap ($0.25).
    """
    base = PREP_COSTS["default"]
    if fragile:
        base += PREP_COSTS["bubble_wrap"]
    elif category:
        cat_lower = category.lower()
        for extra_cat in EXTRA_PREP_CATEGORIES:
            if extra_cat.lower() in cat_lower or cat_lower in extra_cat.lower():
                base += PREP_COSTS["bubble_wrap"]
                break
    return round(base, 2)


def estimate_sales_tax(buy_cost, tax_state="none"):
    """Calculate sales tax on the retail purchase price.

    Args:
        buy_cost: Retail purchase price.
        tax_state: 2-letter state code or 'none'. Default: no tax.

    Returns:
        Tax amount in dollars.
    """
    rate = STATE_SALES_TAX.get(tax_state.upper(), STATE_SALES_TAX.get(tax_state, 0.0))
    return round(buy_cost * rate / 100, 2)


def estimate_storage_fee(monthly_sales=None, sales_rank=None, months_held=3):
    """Estimate total storage fees based on expected time to sell.

    Slow movers (BSR > 100K or monthly_sales < 10) get a penalty.
    Assumes standard-size items.

    Args:
        monthly_sales: Estimated monthly units sold.
        sales_rank: BSR rank.
        months_held: Estimated months of inventory holding (default: 3).

    Returns:
        Estimated total storage cost per unit.
    """
    import datetime
    current_month = datetime.datetime.now().month
    if current_month in (10, 11, 12):
        base_monthly = STORAGE_FEE_PER_UNIT.get("standard_oct_dec", 0.25)
    else:
        base_monthly = STORAGE_FEE_PER_UNIT.get("standard_jan_sep", 0.10)

    # Slow mover penalty — only use estimated sales velocity, not raw BSR
    # (BSR 100K in Grocery is ~20 units/mo, not slow)
    is_slow = monthly_sales is not None and monthly_sales < 10

    if is_slow:
        base_monthly += STORAGE_FEE_PER_UNIT["slow_mover_penalty"]

    # Estimate actual months held based on sales velocity
    if monthly_sales and monthly_sales > 0:
        est_months = min(months_held, max(1, round(1 / (monthly_sales / 30))))
    else:
        est_months = months_held

    return round(base_monthly * est_months, 2)


def calculate_deal_score(roi, monthly_sales, competition_score, restrictions,
                         sales_rank=None, match_confidence=1.0,
                         buy_box_data=None):
    """Calculate a composite deal score (0-100) for ranking products.

    Weights:
      - ROI quality: 25 points
      - Sales velocity: 20 points
      - Competition: 20 points
      - Risk (no hazmat/gating/IP): 10 points
      - BSR quality: 15 points
      - Buy Box accessibility: 10 points

    Returns:
        Integer score 0-100.
    """
    score = 0.0

    # ROI quality (25 pts): 30% = 15pts, 50% = 20pts, 100%+ = 25pts
    if roi is not None and roi > 0:
        score += min(25, roi / 4)

    # Sales velocity (20 pts): 30/mo = 8pts, 100/mo = 17pts, 300+ = 20pts
    if monthly_sales is not None and monthly_sales > 0:
        score += min(20, monthly_sales / 15)

    # Competition (20 pts)
    comp_scores = {"LOW": 20, "MODERATE": 14, "HIGH": 7, "SATURATED": 0,
                   "HIGH_RISK": 0, "UNKNOWN": 10}
    score += comp_scores.get(competition_score, 10)

    # Risk flags (10 pts) — lose points for each flag
    risk_pts = 10
    if restrictions.get("hazmat_risk"):
        risk_pts -= 5
    if restrictions.get("is_gated"):
        risk_pts -= 3
    if restrictions.get("ip_risk"):
        risk_pts -= 5
    score += max(0, risk_pts)

    # BSR quality (15 pts): <5K = 15, <20K = 12, <50K = 8, <100K = 4, >100K = 0
    if sales_rank is not None and sales_rank > 0:
        if sales_rank < 5000:
            score += 15
        elif sales_rank < 20000:
            score += 12
        elif sales_rank < 50000:
            score += 8
        elif sales_rank < 100000:
            score += 4
        # >100K = 0 points
    else:
        score += 5  # unknown BSR = half credit

    # Buy Box accessibility (10 pts) — penalize Amazon-dominated or exclusive listings
    if buy_box_data and isinstance(buy_box_data, dict):
        amazon_pct = buy_box_data.get("amazon_pct", 0) or 0
        dominant_pct = buy_box_data.get("dominant_seller_pct", 0) or 0
        seller_count = buy_box_data.get("seller_count", 0) or 0

        if amazon_pct > 50:
            # Amazon holds >50% Buy Box — heavy penalty
            score += 0
        elif dominant_pct > 70:
            # One seller holds >70% — likely exclusive distribution
            score += 2
        elif seller_count >= 3 and dominant_pct < 50:
            # Healthy rotation — good Buy Box access
            score += 10
        elif seller_count >= 2:
            score += 7
        else:
            score += 4
    else:
        score += 5  # unknown = half credit

    # Penalize low match confidence
    if match_confidence < 0.7:
        score *= match_confidence

    return min(100, max(0, round(score)))


def _resolve_cashback(product, cashback_percent, auto_cashback):
    """Determine effective cashback percent.

    If explicit cashback_percent > 0, use it.
    If auto_cashback is True and cashback_percent is 0, look up retailer estimate.
    """
    if cashback_percent and cashback_percent > 0:
        return cashback_percent
    if auto_cashback:
        retailer = product.get("retailer", "")
        if retailer:
            # Exact match
            if retailer in RETAILER_CASHBACK_ESTIMATES:
                return RETAILER_CASHBACK_ESTIMATES[retailer]
            # Partial match
            retailer_lower = retailer.lower()
            for name, rate in RETAILER_CASHBACK_ESTIMATES.items():
                if name.lower() in retailer_lower or retailer_lower in name.lower():
                    return rate
    return 0.0


def _resolve_gift_card_discount(product, gift_card_discount, auto_giftcard):
    """Determine effective gift card discount percent from CardBear data.

    If explicit gift_card_discount > 0, use it.
    If auto_giftcard is True and gift_card_discount is 0, look up from CardBear DB.
    """
    if gift_card_discount and gift_card_discount > 0:
        return gift_card_discount
    if auto_giftcard:
        retailer = product.get("retailer", "")
        if retailer:
            try:
                from scrape_cardbear import get_gift_card_discount
                return get_gift_card_discount(retailer)
            except (ImportError, Exception):
                pass
    return 0.0


def calculate_product_profitability(product, shipping_to_fba=1.00,
                                    cashback_percent=0.0, coupon_discount=0.0,
                                    auto_cashback=False,
                                    gift_card_discount=0.0, auto_giftcard=False,
                                    prep_cost=None, tax_state="none",
                                    include_storage=True, fbm_mode=False,
                                    auto_coupon=False):
    """Calculate full profitability for a single matched product.

    New in v3.0: prep costs, sales tax, storage fees, BSR auto-filter, deal scoring.
    """
    amazon_data = product.get("amazon", {})
    asin = amazon_data.get("asin")
    match_confidence = amazon_data.get("match_confidence", 0)

    # Determine buy cost (prefer sale price, fall back to retail price)
    raw_buy_cost = product.get("sale_price") or product.get("retail_price")
    sell_price = amazon_data.get("amazon_price")
    category = amazon_data.get("category")
    sales_rank = amazon_data.get("sales_rank")
    product_name = product.get("name", "") or amazon_data.get("title", "")
    brand = product.get("brand") or amazon_data.get("brand")
    amazon_title = amazon_data.get("title", "")
    retail_title = product.get("name", "")

    # ─── Gift card + Cashback + coupon layer ──────────────────────────────
    effective_giftcard = _resolve_gift_card_discount(product, gift_card_discount, auto_giftcard)
    effective_cashback = _resolve_cashback(product, cashback_percent, auto_cashback)

    # Auto-coupon: look up best available code if none manually supplied
    effective_coupon_discount = coupon_discount
    applied_coupon_code = None
    if auto_coupon and coupon_discount == 0.0:
        best_coupon = _resolve_coupon_code(product)
        if best_coupon and best_coupon.get("discount_type") == "percent":
            # Will be applied after gift card + cashback as percent off remaining cost
            applied_coupon_code = best_coupon.get("code")
            effective_coupon_percent = best_coupon.get("value", 0.0)
        else:
            effective_coupon_percent = 0.0
    else:
        effective_coupon_percent = 0.0

    if raw_buy_cost and raw_buy_cost > 0:
        # Stack: gift card → cashback → coupon percent → flat coupon
        after_giftcard = raw_buy_cost * (1 - effective_giftcard / 100)
        after_cashback = after_giftcard * (1 - effective_cashback / 100)
        after_coupon_pct = after_cashback * (1 - effective_coupon_percent / 100)
        effective_buy_cost = after_coupon_pct - effective_coupon_discount
        effective_buy_cost = max(0.01, round(effective_buy_cost, 2))  # floor at $0.01
    else:
        effective_buy_cost = raw_buy_cost

    buy_cost = effective_buy_cost

    # ─── IP Alert check using curated brand database ─────────────────────
    ip_risk = False
    ip_severity = ""
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from ip_alert_brands import is_ip_risk as _is_ip_risk
        _brand = brand or ""
        if _brand:
            ip_risk, ip_severity = _is_ip_risk(_brand)
    except ImportError:
        pass  # Non-fatal — fall through to check_restrictions below

    # ─── Competition scoring ──────────────────────────────────────────────
    competition_score, competition_warnings = score_competition(amazon_data)

    # ─── Restriction checks ───────────────────────────────────────────────
    restrictions = check_restrictions(product_name, category, brand)

    # Merge ip_alert_brands result into restrictions (takes precedence if found)
    if ip_risk:
        restrictions["ip_risk"] = True
        if ip_severity:
            _rw = restrictions.get("restriction_warnings")
            if not isinstance(_rw, list):
                _rw = []
                restrictions["restriction_warnings"] = _rw
            _rw.append(
                f"IP risk [{ip_severity}]: '{brand}' flagged in curated IP alert database"
            )

    # ─── Multi-pack detection ─────────────────────────────────────────────
    multipack = detect_multipack(retail_title, amazon_title)

    # Can't calculate without both prices
    if not buy_cost or not sell_price:
        return {
            "raw_buy_cost": round(raw_buy_cost, 2) if raw_buy_cost else None,
            "gift_card_discount_applied": effective_giftcard,
            "cashback_percent_applied": effective_cashback,
            "coupon_discount_applied": coupon_discount,
            "buy_cost": buy_cost,
            "sales_tax": 0.0,
            "sell_price": sell_price,
            "referral_fee": None,
            "fba_fee": None,
            "prep_cost": None,
            "storage_fee": None,
            "estimated_shipping_to_fba": shipping_to_fba,
            "total_fees": None,
            "profit_per_unit": None,
            "roi_percent": None,
            "estimated_monthly_sales": estimate_monthly_sales(sales_rank, category),
            "estimated_monthly_profit": None,
            "deal_score": 0,
            "verdict": "SKIP",
            "skip_reason": "Missing buy cost or sell price",
            "competition_score": competition_score,
            "competition_warnings": competition_warnings,
            **restrictions,
            **multipack,
        }

    # ─── Prep cost ────────────────────────────────────────────────────────
    # FBM: no prep needed (ship directly from retail)
    if fbm_mode:
        effective_prep_cost = 0.0
    else:
        effective_prep_cost = prep_cost if prep_cost is not None else estimate_prep_cost(category)

    # ─── Sales tax ──────────────────────────────────────────────────────
    sales_tax = estimate_sales_tax(buy_cost, tax_state) if buy_cost else 0.0

    # Calculate fees — FBA vs FBM branch
    referral_fee_rate = get_referral_fee_rate(category)
    referral_fee = round(sell_price * referral_fee_rate, 2)
    if fbm_mode:
        # FBM: no FBA fulfillment fee; you pay your own shipping to buyer
        fba_fee = 0.0
        fbm_shipping = estimate_fbm_fee(sell_price)
        inbound_placement_fee = 0.0  # FBM ships direct — no inbound placement fee
        total_amazon_fees = round(referral_fee + fbm_shipping + effective_prep_cost, 2)
    else:
        fba_fee = estimate_fba_fee(sell_price)
        fbm_shipping = 0.0
        # Inbound Placement Fee — large_standard rate if sell_price suggests heavier item (>$30 proxy)
        weight_proxy = amazon_data.get("weight_lbs") or 0
        if weight_proxy > 1 or sell_price > 30:
            inbound_placement_fee = INBOUND_PLACEMENT_FEE["large_standard"]
        else:
            inbound_placement_fee = INBOUND_PLACEMENT_FEE["default"]
        total_amazon_fees = round(
            referral_fee + fba_fee + shipping_to_fba + effective_prep_cost + inbound_placement_fee, 2
        )

    # Estimate monthly sales and profit (category-aware)
    monthly_sales = estimate_monthly_sales(sales_rank, category)

    # ─── Storage fee ────────────────────────────────────────────────────
    # FBM: no Amazon storage fees (inventory stays at home/warehouse)
    storage_fee = 0.0
    if include_storage and not fbm_mode:
        storage_fee = estimate_storage_fee(monthly_sales, sales_rank)
    total_fees = round(total_amazon_fees + storage_fee, 2)

    # Calculate profit and ROI (including tax as a cost)
    profit = round(sell_price - buy_cost - sales_tax - total_fees, 2)
    roi = round((profit / (buy_cost + sales_tax)) * 100, 1) if (buy_cost + sales_tax) > 0 else 0

    # Max Cost — maximum retail price to hit 30% ROI target (SellerAmp-style)
    _target_roi = 30
    _total_amazon_fees_for_max = referral_fee + fba_fee + effective_prep_cost + storage_fee + inbound_placement_fee + shipping_to_fba
    max_cost_for_roi = round((sell_price - _total_amazon_fees_for_max) / (1 + _target_roi / 100), 2) if sell_price else 0.0

    monthly_profit = round(profit * monthly_sales, 2) if monthly_sales else None

    # ─── Private label & multi-seller verification (v3.0) ────────────────
    private_label_info = amazon_data.get("private_label", {})
    is_private_label = (isinstance(private_label_info, dict) and
                        private_label_info.get("is_private_label") is True)

    fba_seller_count = amazon_data.get("fba_seller_count")

    # ─── Verdict logic (pro criteria — v3.0) ───────────────────────────
    verdict = None
    skip_reason = None

    if not asin or match_confidence < 0.4:
        verdict = "SKIP"
        skip_reason = "No Amazon match or low confidence"
    elif is_private_label:
        verdict = "SKIP"
        pl_reason = private_label_info.get("reason", "brand is only seller") if isinstance(private_label_info, dict) else "brand is only seller"
        skip_reason = f"Private label — {pl_reason}"
    elif fba_seller_count is not None and fba_seller_count < 2:
        verdict = "SKIP"
        skip_reason = f"Only {fba_seller_count} FBA seller(s) — need 2+ for arbitrage"
    elif multipack["multipack_mismatch"]:
        # Adjust cost instead of hard skip — recalculate with true cost
        cost_mult = multipack.get("cost_multiplier", 1.0)
        adjusted_cost = (buy_cost or 0) * cost_mult
        adjusted_fees = adjusted_cost * 0.15 + 4.0
        adjusted_profit = (sell_price or 0) - adjusted_cost - adjusted_fees
        if adjusted_profit < 2.0:
            verdict = "SKIP"
            skip_reason = (f"Pack mismatch kills profit — need {cost_mult:.1f}x units "
                           f"(${adjusted_cost:.2f} true cost, ${adjusted_profit:.2f} profit)")
        else:
            # Still profitable after adjustment — flag but don't skip
            profit = adjusted_profit
            roi = (adjusted_profit / adjusted_cost * 100) if adjusted_cost > 0 else 0
    elif sales_rank and sales_rank > MAX_BSR_THRESHOLD:
        verdict = "SKIP"
        skip_reason = f"BSR {sales_rank:,} exceeds {MAX_BSR_THRESHOLD:,} — product sells too slowly"
    elif competition_score == "SATURATED":
        verdict = "SKIP"
        skip_reason = f"Listing is saturated ({amazon_data.get('fba_seller_count', '?')} FBA sellers)"
    elif amazon_data.get("amazon_on_listing", False):
        # Nuanced check: if Amazon's price is >15% above Buy Box, they're not
        # competitive and other sellers can still win the Buy Box
        amz_direct = amazon_data.get("amazon_direct_price") or amazon_data.get("amz_direct_price")
        bb_or_sell = amazon_data.get("buy_box_price") or amazon_data.get("bb_price") or sell_price
        if (amz_direct and bb_or_sell and amz_direct > bb_or_sell * 1.15):
            # Amazon is on listing but priced significantly above Buy Box — still sourceable
            skip_reason = None  # will be set to BUY/MAYBE below
        else:
            verdict = "SKIP"
            skip_reason = "Amazon is a seller on this listing - Buy Box risk is high"

    # ─── Historical Buy Box analysis (E2) ────────────────────────────────
    # Use amazon_oos_pct from keepa_data: OOS% < 50% means Amazon active > 50% of time
    _keepa_data = amazon_data  # amazon_data is the keepa-enriched dict
    amazon_bb_pct = _keepa_data.get("amazon_oos_pct", 1.0)
    if not isinstance(amazon_bb_pct, (int, float)):
        amazon_bb_pct = 1.0
    amazon_active_historically = (1.0 - amazon_bb_pct) > 0.50
    if amazon_active_historically and not amazon_data.get("amazon_on_listing", False):
        competition_warnings.append(
            "CAUTION: Amazon active 50%+ historically (currently not selling)"
        )
    elif roi >= 30 and profit >= 3.00 and (monthly_sales is None or monthly_sales >= 15):
        verdict = "BUY"
        skip_reason = None
    elif roi >= 20 and profit >= 2.00:
        verdict = "MAYBE"
        skip_reason = None
    else:
        verdict = "SKIP"
        skip_reason = f"ROI {roi}% or profit ${profit} below threshold"

    # ─── Hazmat downgrade (v4.0): warning not hard-SKIP ─────────────────
    if restrictions["hazmat_risk"] and verdict == "BUY":
        verdict = "MAYBE"
        skip_reason = "Potential hazmat — verify in Seller Central before shipping"

    # ─── Review count filter (v3.0): <50 reviews → downgrade BUY to MAYBE ──
    review_count = amazon_data.get("review_count")
    if verdict == "BUY" and review_count is not None and review_count < 50:
        verdict = "MAYBE"
        skip_reason = f"Low review count ({review_count}) — downgraded from BUY"

    # ─── Deal score ─────────────────────────────────────────────────────
    deal_score = calculate_deal_score(
        roi, monthly_sales, competition_score, restrictions,
        sales_rank, match_confidence
    )

    # ─── Price trend bonus (v3.0): +5 for rising, +5 for not at historical low ──
    price_trends = amazon_data.get("price_trends", {})
    if isinstance(price_trends, dict):
        if price_trends.get("trend") == "rising":
            deal_score = min(100, deal_score + 5)
        if price_trends.get("at_historical_low") is False:
            deal_score = min(100, deal_score + 5)

    return {
        "raw_buy_cost": round(raw_buy_cost, 2) if raw_buy_cost else None,
        "gift_card_discount_applied": effective_giftcard,
        "cashback_percent_applied": effective_cashback,
        "coupon_discount_applied": coupon_discount,
        "coupon_percent_applied": effective_coupon_percent,
        "coupon_code_used": applied_coupon_code,
        "buy_cost": round(buy_cost, 2),
        "sales_tax": sales_tax,
        "sell_price": round(sell_price, 2),
        "referral_fee": referral_fee,
        "referral_fee_rate": referral_fee_rate,
        "fba_fee": fba_fee,
        "inbound_placement_fee": inbound_placement_fee,
        "fbm_mode": fbm_mode,
        "fbm_shipping": fbm_shipping,
        "prep_cost": effective_prep_cost,
        "storage_fee": storage_fee,
        "estimated_shipping_to_fba": shipping_to_fba if not fbm_mode else 0.0,
        "total_fees": total_fees,
        "max_cost": max_cost_for_roi,
        "profit_per_unit": profit,
        "roi_percent": roi,
        "estimated_monthly_sales": monthly_sales,
        "estimated_monthly_profit": monthly_profit,
        "deal_score": deal_score,
        "verdict": verdict,
        "skip_reason": skip_reason,
        "competition_score": competition_score,
        "competition_warnings": competition_warnings,
        "ip_severity": ip_severity,
        "bsr_drops_30d": amazon_data.get("bsr_drops_30d", 0) if isinstance(amazon_data, dict) else 0,
        "bsr_drops_60d": amazon_data.get("bsr_drops_60d", 0) if isinstance(amazon_data, dict) else 0,
        "bsr_drops_90d": amazon_data.get("bsr_drops_90d", 0) if isinstance(amazon_data, dict) else 0,
        "amazon_bb_pct_90d": amazon_data.get("amazon_oos_pct", 0.0) if isinstance(amazon_data, dict) else 0.0,
        **restrictions,
        **multipack,
    }


def run_profitability(input_path, output_path, min_roi=30, min_profit=3.0,
                      max_price=50.0, shipping_cost=1.00,
                      cashback_percent=0.0, coupon_discount=0.0,
                      auto_cashback=False,
                      gift_card_discount=0.0, auto_giftcard=False,
                      prep_cost=None, tax_state="none",
                      include_storage=True, fbm_mode=False,
                      auto_coupon=False):
    """Calculate profitability for all products, filter, and rank."""
    with open(input_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    print(f"[profit] Calculating profitability for {len(products)} products...", file=sys.stderr)
    if tax_state and tax_state != "none":
        print(f"[profit] Sales tax: {tax_state} ({STATE_SALES_TAX.get(tax_state.upper(), 0)}%)",
              file=sys.stderr)

    for product in products:
        product["profitability"] = calculate_product_profitability(
            product, shipping_cost,
            cashback_percent=cashback_percent,
            coupon_discount=coupon_discount,
            auto_cashback=auto_cashback,
            gift_card_discount=gift_card_discount,
            auto_giftcard=auto_giftcard,
            prep_cost=prep_cost,
            tax_state=tax_state,
            include_storage=include_storage,
            fbm_mode=fbm_mode,
            auto_coupon=auto_coupon,
        )

    # Separate by verdict
    buy_products = []
    maybe_products = []
    skip_products = []

    for product in products:
        prof = product["profitability"]
        verdict = prof.get("verdict", "SKIP")
        buy_cost = prof.get("buy_cost")

        # Apply max_price filter
        if buy_cost and buy_cost > max_price:
            prof["verdict"] = "SKIP"
            prof["skip_reason"] = f"Buy cost ${buy_cost} exceeds max ${max_price}"
            verdict = "SKIP"

        if verdict == "BUY":
            buy_products.append(product)
        elif verdict == "MAYBE":
            maybe_products.append(product)
        else:
            skip_products.append(product)

    # Sort BUY and MAYBE by ROI descending
    buy_products.sort(key=lambda p: p["profitability"].get("roi_percent", 0), reverse=True)
    maybe_products.sort(key=lambda p: p["profitability"].get("roi_percent", 0), reverse=True)

    # Recombine: BUY first, then MAYBE, then SKIP
    all_products = buy_products + maybe_products + skip_products

    # Summary stats
    all_rois = [p["profitability"]["roi_percent"] for p in buy_products + maybe_products
                if p["profitability"].get("roi_percent") is not None]
    avg_roi = round(sum(all_rois) / len(all_rois), 1) if all_rois else 0
    all_profits = [p["profitability"]["profit_per_unit"] for p in buy_products + maybe_products
                   if p["profitability"].get("profit_per_unit") is not None]
    avg_profit = round(sum(all_profits) / len(all_profits), 2) if all_profits else 0

    # Count restriction flags across all products
    hazmat_count = sum(1 for p in products if p["profitability"].get("hazmat_risk"))
    gated_count = sum(1 for p in products if p["profitability"].get("is_gated"))
    ip_risk_count = sum(1 for p in products if p["profitability"].get("ip_risk"))
    multipack_mismatch_count = sum(1 for p in products if p["profitability"].get("multipack_mismatch"))

    output_data = {
        "retailer": data.get("retailer", "unknown"),
        "url": data.get("url", ""),
        "products": all_products,
        "count": len(all_products),
        "summary": {
            "total_analyzed": len(products),
            "buy_count": len(buy_products),
            "maybe_count": len(maybe_products),
            "skip_count": len(skip_products),
            "avg_roi_percent": avg_roi,
            "avg_profit_per_unit": avg_profit,
            "hazmat_flagged": hazmat_count,
            "gated_flagged": gated_count,
            "ip_risk_flagged": ip_risk_count,
            "multipack_mismatches": multipack_mismatch_count,
            "filters_applied": {
                "min_roi": min_roi,
                "min_profit": min_profit,
                "max_price": max_price,
                "shipping_cost": shipping_cost,
                "cashback_percent": cashback_percent,
                "coupon_discount": coupon_discount,
                "auto_cashback": auto_cashback,
                "gift_card_discount": gift_card_discount,
                "auto_giftcard": auto_giftcard,
                "prep_cost": prep_cost,
                "tax_state": tax_state,
                "include_storage": include_storage,
            },
        },
        "calculated_at": datetime.now().isoformat(),
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"[profit] Done. {len(buy_products)} BUY | {len(maybe_products)} MAYBE | "
          f"{len(skip_products)} SKIP", file=sys.stderr)
    if all_rois:
        print(f"[profit] Avg ROI: {avg_roi}% | Avg profit: ${avg_profit}", file=sys.stderr)
    if hazmat_count:
        print(f"[profit] {hazmat_count} product(s) flagged as potential hazmat", file=sys.stderr)
    if gated_count:
        print(f"[profit] {gated_count} product(s) in gated categories", file=sys.stderr)
    if multipack_mismatch_count:
        print(f"[profit] {multipack_mismatch_count} multi-pack mismatch(es) detected", file=sys.stderr)
    print(f"[profit] Results -> {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Calculate FBA profitability for matched products")
    parser.add_argument("--input", required=True, help="Input JSON from match_amazon_products.py")
    parser.add_argument("--output", required=True, help="Output JSON with profitability data")
    parser.add_argument("--min-roi", type=float, default=30, help="Min ROI %% for BUY verdict (default: 30)")
    parser.add_argument("--min-profit", type=float, default=3.0, help="Min profit per unit for BUY (default: $3)")
    parser.add_argument("--max-price", type=float, default=50.0, help="Max buy price to include (default: $50)")
    parser.add_argument("--shipping-cost", type=float, default=1.00,
                        help="Est. shipping cost per unit to FBA (default: $1.00)")
    parser.add_argument("--cashback-percent", type=float, default=0.0,
                        help="Cashback %% to reduce effective buy cost (default: 0)")
    parser.add_argument("--coupon-discount", type=float, default=0.0,
                        help="Flat coupon discount ($) to reduce effective buy cost (default: 0)")
    parser.add_argument("--auto-cashback", action="store_true",
                        help="Auto-apply estimated Rakuten cashback based on retailer name")
    parser.add_argument("--gift-card-discount", type=float, default=0.0,
                        help="Gift card discount %% to reduce buy cost (default: 0)")
    parser.add_argument("--auto-giftcard", action="store_true",
                        help="Auto-apply CardBear gift card discount based on retailer name")
    parser.add_argument("--prep-cost", type=float, default=None,
                        help="Manual prep cost per unit (default: auto-estimate $0.30-$0.55)")
    parser.add_argument("--tax-state", type=str, default="none",
                        help="State code for sales tax on retail purchases (e.g., CA, TX, none)")
    parser.add_argument("--no-storage", action="store_true",
                        help="Disable estimated storage fee calculation")
    parser.add_argument("--fbm", action="store_true",
                        help="Calculate as FBM (Fulfilled by Merchant): no FBA fee, no prep, "
                             "estimates self-ship cost instead. Use for fragrances, hazmat, "
                             "or direct-ship plays (Zara, MAC, etc.)")
    parser.add_argument("--auto-coupon", action="store_true",
                        help="Auto-apply best known coupon code from RETAILER_COUPON_CODES db")
    args = parser.parse_args()

    run_profitability(args.input, args.output, args.min_roi, args.min_profit,
                      args.max_price, args.shipping_cost,
                      cashback_percent=args.cashback_percent,
                      coupon_discount=args.coupon_discount,
                      auto_cashback=args.auto_cashback,
                      gift_card_discount=args.gift_card_discount,
                      auto_giftcard=args.auto_giftcard,
                      prep_cost=args.prep_cost,
                      tax_state=args.tax_state,
                      include_storage=not args.no_storage,
                      fbm_mode=args.fbm,
                      auto_coupon=args.auto_coupon)


if __name__ == "__main__":
    main()
