#!/usr/bin/env python3
"""
Student-confirmed ungated ASINs — mined from Discord chats 2026-03-16.

Three tiers of confidence:

  TIER_1_SABBO_POSTED  — Sabbo posted these directly as "auto-ungated" in #seller-central-course
                          or #ic-groupchat. Highest confidence.

  TIER_2_STUDENT_CONFIRMED — Students explicitly said they were ungated on these ASINs
                              (direct message + source link). High confidence.

  TIER_3_REVERSE_SOURCE — From Sabbo's "brands to reverse source sellers / auto ungate sell"
                           post. Contains some "click apply to sell" items — verify before sourcing.

Usage:
    from student_ungated_asins import ALL_UNGATED_ASINS, TIER_1_SABBO_POSTED, get_all_asins

    # Feed to sourcing tool
    asins = get_all_asins(min_tier=1)   # only high-confidence
    asins = get_all_asins()             # all tiers

Source: /Users/Shared/antigravity/projects/nomad-nebula/.tmp/discord-content-scrape.json
Mining script: /tmp/mine_ungated.py
"""

# Tier 1 — Sabbo posted directly as auto-ungated (alldayfba in Discord)
# Posted 2025-11-05 in #seller-central-course and #ic-groupchat
TIER_1_SABBO_POSTED = {
    "B07BQ84QNV": "Apple Barrel (auto-ungated brand post)",
    "B0BV886Y94": "Cuddl Duds (auto-ungated brand post)",
    "B0BZZWBSYD": "OUT store (auto-ungated brand post)",
    "B07T9G3CGX": "Plink (auto-ungated brand post)",
    "B00T6QAD1U": "Danner (auto-ungated brand post)",
    "B01LXRYMUL": "Dryel (auto-ungated brand post)",
}

# Tier 2 — Students confirmed ungated with explicit source mention
# Mined from 1,414 ungated keyword mentions across 59,851 Discord messages
TIER_2_STUDENT_CONFIRMED = {
    "B000EN5CQK": "Aramis cologne — Jomashop",
    "B000HASBOU": "Audubon bird feeder — Walmart",
    "B000WM3D78": "Dumont Unscented Day Use",
    "B001AXWBDA": "Aramis aftershave balm — FragranceNet",
    "B001BKPPTE": "Lakewood Organic Pineapple juice",
    "B001F0LYRM": "Pampered Chef pizza stone",
    "B003A8OIWK": "Science Selective rabbit food — Chewy",
    "B009QO2V2Q": "ACME Markets product",
    "B00BIM8GHS": "Arm & Hammer Spinbrush heads — CVS",
    "B00HV8Z7M0": "Love's Baby Soft cologne — ThePerfumeSpot",
    "B00LZSJ642": "Student noted transparency barcode needed",
    "B00X7858Y0": "Numi Tea Breakfast Blend — Thrive Market",
    "B01CI36D2A": "Gold Bond Friction Defense — Thrifty White",
    "B01G971HKO": "Melaleuca Tough & Tender cleaner",
    "B01GWDF5O4": "Golden Girls Complete Series DVD",
    "B01LXHWVS8": "MF Doom vinyl — Walmart",
    "B077L4YPZ2": "Campbell's Liquid Lather shave cream",
    "B078XZRMJL": "Mikasa Trellis fruit bowls",
    "B07GQJY8H1": "White Collar seasons 1-6 DVD",
    "B07J1W6M84": "Milwaukee drill bit set — Home Depot",
    "B07QCD2SJH": "Brava adhesive remover spray",
    "B08BK7BJ1C": "Tesla key card 2-pack",
    "B08LZQ46PN": "Roku Premiere — Walmart",
    "B08Q5Y3NPS": "i-LID n LASH eye drops",
    "B08R5WQYD3": "Equate Corn Starch Baby Powder — Walmart",
    "B0821YDQ8F": "Storck Werther's Chewy Caramels — Walmart",
    "B09P1R7BB4": "Max Warehouse product",
    "B0B8T95D68": "P-Louise Eye Base",
    "B0C4Z33W1R": "Rudolph musical toy — Target",
    "B0C8ZKHWGV": "Ninja Turtles Extended Range — Walmart",
    "B0CJL1P9VS": "Watermelon Probiotic underarm toner",
    "B0CNC81Y9X": "Milwaukee 10pc screwdriver set",
    "B0CQ8VGMYM": "Yellowstone complete DVD",
    "B0D1KVVHYT": "Merit Flush Balm — Sephora",
    "B0DDXPG9MC": "GE Washer Pedestal",
    "B0F2J14F6G": "Round Lab Birch Juice wash — iHerb",
}

# Tier 3 — "Brands to reverse source / auto ungate sell" list from Sabbo's post
# Note: B005LURDJK = grocery auto-ungated; B08CBZVRG4 + B08SR9ZLSY = "click apply to sell" (not instant)
TIER_3_REVERSE_SOURCE = {
    "B0C8YQFPWT": "Reverse source candidate",
    "B005LURDJK": "Grocery auto-ungated (reverse source)",
    "B081TSSZJ3": "Reverse source candidate",
    "B0D8TLXH3J": "Reverse source candidate",
    "B00NB71850": "Reverse source candidate",
    "B0CKM5T1WZ": "Reverse source candidate",
    "B0DH8P2YNG": "Reverse source candidate",
    "B08CBZVRG4": "Click apply to sell (not instant auto-ungate)",
    "B07NRVZ584": "Reverse source candidate",
    "B08SR9ZLSY": "Click apply to sell (not instant auto-ungate)",
    "B0BSP1X7F8": "Reverse source candidate",
    "B073PNYSMP": "Reverse source candidate",
    "B07BRVGKQ6": "Reverse source candidate",
    "B08F5LVT7B": "Reverse source candidate",
    "B0CZDFGH49": "Reverse source candidate",
}

# Merged — all tiers combined
ALL_UNGATED_ASINS = {
    **TIER_1_SABBO_POSTED,
    **TIER_2_STUDENT_CONFIRMED,
    **TIER_3_REVERSE_SOURCE,
}

# Total unique: 57 ASINs


def get_all_asins(max_tier: int = 3) -> list[str]:
    """
    Return all student-confirmed ungated ASINs as a list.

    Args:
        max_tier: Highest tier to include (1=Sabbo-only, 2=+student-confirmed, 3=all).
                  Default is 3 (all 57 ASINs).
                  Use 1 for only the 6 highest-confidence Sabbo-posted ASINs.
    """
    tiers = {}
    tiers.update(TIER_1_SABBO_POSTED)
    if max_tier >= 2:
        tiers.update(TIER_2_STUDENT_CONFIRMED)
    if max_tier >= 3:
        tiers.update(TIER_3_REVERSE_SOURCE)
    return sorted(tiers.keys())


def get_asins_with_notes(max_tier: int = 3) -> dict[str, str]:
    """Return ASIN → note mapping for the given tier threshold."""
    tiers = {}
    tiers.update(TIER_1_SABBO_POSTED)
    if max_tier >= 2:
        tiers.update(TIER_2_STUDENT_CONFIRMED)
    if max_tier >= 3:
        tiers.update(TIER_3_REVERSE_SOURCE)
    return tiers


if __name__ == "__main__":
    all_asins = get_all_asins(max_tier=3)
    print(f"Total student-confirmed ungated ASINs: {len(all_asins)}")
    print(f"  Tier 1 (Sabbo-posted): {len(TIER_1_SABBO_POSTED)}")
    print(f"  Tier 2 (student-confirmed): {len(TIER_2_STUDENT_CONFIRMED)}")
    print(f"  Tier 3 (reverse source): {len(TIER_3_REVERSE_SOURCE)}")
    print()
    print("=== ALL ASINs (Tier 1–3) ===")
    for asin, note in sorted(ALL_UNGATED_ASINS.items()):
        tier = (
            1 if asin in TIER_1_SABBO_POSTED
            else 2 if asin in TIER_2_STUDENT_CONFIRMED
            else 3
        )
        print(f"  [{tier}] {asin}  —  {note}")
