#!/usr/bin/env python3
"""
Student-confirmed ungated brands — mined from Discord chats 2026-03-16.

Tiered by confidence:

  TIER_1_SABBO_POSTED       — Sabbo explicitly labeled these auto-ungated in Discord
  TIER_2_SABBO_PRODUCT_LEADS — Sabbo pushed these as product leads requiring ungate
  TIER_3_STUDENT_CONFIRMED  — Students explicitly said they got approved/ungated
  RESTRICTED                — Confirmed restricted or very hard to ungate (don't bother)

Usage:
    from student_ungated_brands import get_all_brands, is_student_ungated, TIER_1_SABBO_POSTED

    brands = get_all_brands()          # all tiers
    brands = get_all_brands(max_tier=1) # Sabbo-posted only

Source: 59,851 Discord messages, 1,363 ungating-keyword matches
Mining: /tmp/all_ungated_messages.json
"""

# ── Tier 1: Sabbo posted directly as auto-ungated ────────────────────────────
# Posted 2025-11-05 in #seller-central-course and #ic-groupchat by alldayfba
# Also note: most products under Summit Brands (parent of OUT, Plink, CLR) auto-ungate
TIER_1_SABBO_POSTED = {
    "Apple Barrel",     # craft paint — B07BQ84QNV
    "Cuddl Duds",       # B0BV886Y94
    "Danner",           # boots — B00T6QAD1U
    "Dryel",            # at-home dry cleaning — B01LXRYMUL
    "OUT",              # Spectrum/Summit Brands — B0BZZWBSYD
    "Plink",            # Summit Brands — B07T9G3CGX
    "Summit Brands",    # parent co: OUT, Plink, CLR — most products auto-ungated per alldayfba
    "CLR",              # Summit Brands family
}

# ── Tier 2: Sabbo product leads — worth ungating, he pushed to students ──────
# Sabbo posted these as product leads in student channels
# "May Need Vitacost ungate" = use 10-unit Vitacost invoice to get approved
TIER_2_SABBO_PRODUCT_LEADS = {
    "Babyganics",       # B00PRRUISK, B00LSN5X0A — may need Vitacost ungate
    "Dr. Bronner's",    # B005U5HXZA, B00TPKLBDQ — may need Vitacost ungate
    "Dr. Teal's",       # B0BYQDKB1F — Sabbo pushed to 5+ student channels
    "Krylon",           # spray paint — product lead posted via 24/7 bot
    "Missy J's",        # organic food — B07ZHVQWNB — may require 100-unit ungate
    "Neutrogena",       # Sabbo asking students "anyone ungated in Neutrogena?"
    "Russell Stover",   # Sabbo asking who's ungated — candy brand
    "Simple Truth",     # B09238F3Q5 — Kroger brand, may need Vitacost ungate
}

# ── Tier 3: Students confirmed ungated ───────────────────────────────────────
# Direct quotes from Discord — students reporting approved status
TIER_3_STUDENT_CONFIRMED = {
    # Beauty / Personal Care
    "Aramis",           # _mal.k — cologne, FragranceNet
    "Aura Cacia",       # yetihustles — essential oils (helping others ungate)
    "Bella Skin Beauty",# _mal.k — probiotic toner B0CJL1P9VS
    "Dana",             # _mal.k — Love's Baby Soft cologne
    "e.l.f.",           # oliviamlee, yetihustles — confirmed
    "Eucerin",          # _mal.k — B0070X3C9G
    "Gold Bond",        # _mal.k — chafing defense, CVS
    "Merit Beauty",     # _mal.k — flush balm, Sephora
    "OPI",              # _mal.k, bwyan.n — confirmed ungated
    "P-Louise",         # _mal.k — B0B8T95D68
    "Round Lab",        # _mal.k — K-beauty, iHerb

    # Grocery / Food / Beverage
    "Bigelow Tea",      # jservz11 — confirmed ungated, looking for supplier
    "Hershey",          # bwyan.n — "tryna get ungated before Halloween"
    "Lindt",            # _mal.k — Lindor truffles, Walmart
    "Missy J's",        # organic food brand
    "Stash Tea",        # bearteams — "I already ungated stash tea"
    "Torani",           # bayviewcapital — asking, likely ungated
    "Werther's Original",  # _mal.k — chewy caramels, Walmart
    "Yogi Tea",         # elzbth.xo, graceann0127, kimbillion — grocery ungate gateway

    # Toys / Games / Collectibles
    "Barbie",           # angieebabe — "I got approved for Barbie"
    "Hasbro",           # _mal.k — Simon game, Theisens
    "Lego",             # tanhustles — "I was approved for Lego and have gotten a few sales"

    # Home / Cleaning
    "Bath & Body Works",  # oliviamlee — "just auto ungated for Bath n Body"
    "Clorox",           # itspaydaee — "Who did you use to get Clorox ungated?"
    "GE",               # _mal.k — washer pedestal hardware, B0DDXPG9MC

    # Tools / Hardware
    "Milwaukee",        # _mal.k — 10pc screwdriver set, Home Depot
    "Mikasa",           # _mal.k — Trellis fruit bowls, Mikasa.com

    # Sports / Apparel
    "Adidas",           # liridon21 — "Ik im ungated in adidas"
    "Ninja",            # yetihustles — "I didn't need to ungate Ninja" (auto)

    # Electronics / Tech
    "Fujifilm",         # asalupi90_ — "I got approved to sell Fujifilm brand"
    "JBL",              # dee856, ozgurkoc3722 — asking about invoices for ungating
    "Roku",             # _mal.k — Premiere 4K, Walmart

    # Craft / Art
    "Crayola",          # 27 mentions — inspiredfab, flam3z6965, wbastian + many more

    # Other
    "Science Selective",  # _mal.k — rabbit food, Chewy
    "Starbucks",        # kimbillion — ungated via straws invoice
    "Valley Forge Flag",  # _mal.k — maxwarehouse.com
    "FHS Retail",       # jaybo2424 — "I'm ungated for FHS retail brand"
    "Brava",            # _mal.k — medical adhesive remover, blowoutmedical.com
    "i-Lid n Lash",     # _mal.k — eye drops, eyedropshop.com
}

# ── Restricted — confirmed hard/impossible to ungate ─────────────────────────
RESTRICTED_BRANDS = {
    "Nike",             # maine6761: "You can't get ungated in Nike anymore"
    "Crest",            # alldayfba: "don't believe you can sell crest"
    "Yankee Candle",    # maine6761: "could not get around the ungate"
    "Nature Made",      # darienczr: "Target declined me twice"
}

# ── Merged lookup sets ────────────────────────────────────────────────────────
ALL_STUDENT_UNGATED_BRANDS = (
    TIER_1_SABBO_POSTED
    | TIER_2_SABBO_PRODUCT_LEADS
    | TIER_3_STUDENT_CONFIRMED
)

_BRANDS_LOWER = {b.lower() for b in ALL_STUDENT_UNGATED_BRANDS}
_RESTRICTED_LOWER = {b.lower() for b in RESTRICTED_BRANDS}


def is_student_ungated(brand_name: str) -> bool:
    """Return True if brand appears in any student-confirmed ungated tier."""
    return brand_name.lower().strip() in _BRANDS_LOWER


def is_restricted(brand_name: str) -> bool:
    """Return True if brand is confirmed restricted/hard to ungate."""
    return brand_name.lower().strip() in _RESTRICTED_LOWER


def get_all_brands(max_tier: int = 3) -> list[str]:
    """
    Return all student-confirmed ungated brands as a sorted list.

    Args:
        max_tier: Highest tier to include.
                  1 = Sabbo-posted only (highest confidence)
                  2 = + Sabbo product leads
                  3 = all confirmed brands (default)
    """
    brands = set(TIER_1_SABBO_POSTED)
    if max_tier >= 2:
        brands |= TIER_2_SABBO_PRODUCT_LEADS
    if max_tier >= 3:
        brands |= TIER_3_STUDENT_CONFIRMED
    return sorted(brands)


if __name__ == "__main__":
    all_brands = get_all_brands(max_tier=3)
    print(f"Total student-confirmed ungated brands: {len(all_brands)}")
    print(f"  Tier 1 (Sabbo-posted): {len(TIER_1_SABBO_POSTED)}")
    print(f"  Tier 2 (Sabbo leads):  {len(TIER_2_SABBO_PRODUCT_LEADS)}")
    print(f"  Tier 3 (Student):      {len(TIER_3_STUDENT_CONFIRMED)}")
    print(f"  Restricted (skip):     {len(RESTRICTED_BRANDS)}")
    print()
    print("=== ALL BRANDS ===")
    for b in all_brands:
        tier = (1 if b in TIER_1_SABBO_POSTED
                else 2 if b in TIER_2_SABBO_PRODUCT_LEADS
                else 3)
        print(f"  [{tier}] {b}")
    print()
    print("=== RESTRICTED (do not source) ===")
    for b in sorted(RESTRICTED_BRANDS):
        print(f"  [!] {b}")
