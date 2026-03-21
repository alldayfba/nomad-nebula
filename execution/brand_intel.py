from __future__ import annotations
"""
Brand Intel — SmartScout-inspired brand market share analysis.
Provides brand-level statistics for OA opportunity assessment:
- Total ASINs in brand catalog
- % where Amazon is actively selling (threat level)
- Dominant category
- Avg BSR, avg FBA seller count
"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def analyze_brand(brand_name: str, keepa_client=None, max_asins: int = 100) -> dict:
    """
    Analyze a brand's Amazon presence for OA opportunity assessment.

    Returns:
        {
            "brand": str,
            "total_asins": int,
            "amazon_active_count": int,
            "amazon_active_pct": float,
            "oa_opportunity_count": int,
            "dominant_category": str,
            "avg_bsr": int,
            "avg_fba_sellers": float,
            "top_asins": list[dict],  # Top 5 by BSR
            "opportunity_score": int,  # 0-100
            "summary": str,
        }
    """
    if keepa_client is None:
        try:
            from keepa_client import KeepaClient
            keepa_client = KeepaClient(os.getenv("KEEPA_API_KEY"))
        except Exception as e:
            return {"brand": brand_name, "error": str(e), "total_asins": 0}

    # Fetch brand catalog
    try:
        catalog = keepa_client.get_brand_catalog(brand_name, max_asins=max_asins)
    except Exception as e:
        logger.warning(f"Could not fetch brand catalog for {brand_name}: {e}")
        return {"brand": brand_name, "error": str(e), "total_asins": 0}

    if not catalog:
        return {"brand": brand_name, "total_asins": 0, "summary": f"No ASINs found for brand '{brand_name}'"}

    # Enrich with per-ASIN data
    asins = [p.get("asin") for p in catalog if p.get("asin")]

    try:
        products = keepa_client.get_products(asins[:max_asins])
    except Exception as e:
        # Fallback — use basic catalog data only
        products = catalog

    # Aggregate stats
    amazon_active = 0
    categories: dict[str, int] = {}
    bsr_total = 0
    bsr_count = 0
    fba_seller_total = 0
    fba_seller_count = 0
    top_asins = []

    for p in products:
        # Amazon active = index 0 is not all -1
        if p.get("amazon_in_stock") or p.get("amazon_price", 0) > 0:
            amazon_active += 1

        cat = p.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1

        bsr = p.get("bsr") or p.get("current_bsr")
        if bsr and 0 < bsr < 2_000_000:
            bsr_total += bsr
            bsr_count += 1
            top_asins.append({"asin": p.get("asin"), "bsr": bsr, "title": p.get("title", "")[:60]})

        fba = p.get("fba_seller_count", 0)
        if fba is not None and fba >= 0:
            fba_seller_total += fba
            fba_seller_count += 1

    total = len(products)
    amazon_pct = amazon_active / total if total > 0 else 0
    oa_count = total - amazon_active
    avg_bsr = int(bsr_total / bsr_count) if bsr_count > 0 else 0
    avg_fba = round(fba_seller_total / fba_seller_count, 1) if fba_seller_count > 0 else 0
    dominant_cat = max(categories, key=categories.get) if categories else "Unknown"

    # Sort top ASINs by BSR (lower = better)
    top_asins.sort(key=lambda x: x.get("bsr", 999999))

    # Opportunity score: higher = better OA opportunity
    # Low Amazon active % = good (less competition from Amazon)
    # More total ASINs = more opportunities
    # Lower avg BSR = products sell well
    opp_score = 0
    opp_score += max(0, 40 - int(amazon_pct * 100)) * 1  # 0-40 pts for low Amazon %
    opp_score += min(20, oa_count // 2)  # Up to 20 pts for volume of opportunities
    if avg_bsr > 0:
        if avg_bsr < 10000:
            opp_score += 30
        elif avg_bsr < 50000:
            opp_score += 20
        elif avg_bsr < 100000:
            opp_score += 10
    opp_score = min(100, opp_score)

    summary = (
        f"{brand_name}: {total} ASINs found. Amazon active on {int(amazon_pct*100)}% ({amazon_active} ASINs). "
        f"{oa_count} potential OA opportunities. Category: {dominant_cat}. "
        f"Avg BSR: {avg_bsr:,}. Opportunity score: {opp_score}/100."
    )

    return {
        "brand": brand_name,
        "total_asins": total,
        "amazon_active_count": amazon_active,
        "amazon_active_pct": round(amazon_pct, 3),
        "oa_opportunity_count": oa_count,
        "dominant_category": dominant_cat,
        "avg_bsr": avg_bsr,
        "avg_fba_sellers": avg_fba,
        "top_asins": top_asins[:5],
        "opportunity_score": opp_score,
        "summary": summary,
    }


if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "Crayola"
    import json
    result = analyze_brand(brand)
    print(json.dumps(result, indent=2))
