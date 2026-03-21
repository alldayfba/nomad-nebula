#!/usr/bin/env python3
"""
Script: schema_adapter.py
Purpose: Bidirectional converters between the 3 output schemas used across the
         sourcing pipeline. Enables source.py output to feed export_to_sheets.py
         and sourcing_alerts.py without manual reformatting.

Schemas:
  A (pipeline): Used by calculate_fba_profitability.py, export_to_sheets.py,
     sourcing_alerts.py. Nested structure:
       {name, retailer, url, amazon: {asin, title, ...}, profitability: {verdict, ...}}

  B (source.py): Flat structure from verify_on_amazon():
       {asin, amazon_title, amazon_price, buy_cost, estimated_profit, estimated_roi,
        verdict, match_confidence, source_url, source_retailer, profitability: {...}}

  C (deal_scanner): Deal-oriented:
       {deal_type, deal_score, current_price, historical_avg, asin, title, ...}

Usage:
  from schema_adapter import schema_b_to_a, schema_c_to_a, normalize_result, wrap_for_export

  # Convert a single source.py result → Schema A
  schema_a_product = schema_b_to_a(source_result)

  # Wrap a list of source.py results into export_to_sheets.py format
  export_data = wrap_for_export(source_results, mode_name="Brand: CeraVe")
"""


def schema_b_to_a(result):
    """Convert a source.py (Schema B) result dict to Schema A (pipeline) format.

    Schema A is what export_to_sheets.py and sourcing_alerts.py expect:
      - product.name
      - product.retailer
      - product.url
      - product.amazon.asin
      - product.amazon.title
      - product.amazon.amazon_price
      - product.amazon.sales_rank
      - product.amazon.fba_seller_count
      - product.amazon.match_confidence
      - product.amazon.product_url
      - product.profitability.verdict
      - product.profitability.buy_cost
      - product.profitability.sell_price
      - product.profitability.profit_per_unit
      - product.profitability.roi_percent
      - product.profitability.estimated_monthly_sales
      - product.profitability.estimated_monthly_profit
      - product.profitability.competition_score
    """
    if not result:
        return result

    # If it already looks like Schema A (has nested amazon dict), return as-is
    if "amazon" in result and isinstance(result["amazon"], dict):
        return result

    prof = result.get("profitability", {})

    return {
        "name": result.get("name") or result.get("amazon_title", ""),
        "retailer": result.get("source_retailer") or result.get("retailer", ""),
        "url": result.get("source_url") or result.get("buy_url", ""),
        "brand": result.get("brand", ""),
        "amazon": {
            "asin": result.get("asin", ""),
            "title": result.get("amazon_title") or result.get("name", ""),
            "amazon_price": result.get("amazon_price") or prof.get("sell_price"),
            "sales_rank": result.get("bsr") or prof.get("sales_rank"),
            "fba_seller_count": result.get("fba_seller_count") or prof.get("fba_seller_count"),
            "match_confidence": result.get("match_confidence", 0),
            "match_method": result.get("match_method", "title"),
            "product_url": result.get("amazon_url", ""),
            "category": result.get("category", ""),
            "brand": result.get("brand", ""),
        },
        "profitability": {
            "verdict": result.get("verdict") or prof.get("verdict", "SKIP"),
            "buy_cost": result.get("buy_cost") or prof.get("buy_cost"),
            "sell_price": result.get("amazon_price") or prof.get("sell_price"),
            "profit_per_unit": result.get("estimated_profit") or prof.get("profit_per_unit"),
            "roi_percent": result.get("estimated_roi") or prof.get("roi_percent"),
            "estimated_monthly_sales": prof.get("estimated_monthly_sales"),
            "estimated_monthly_profit": prof.get("estimated_monthly_profit"),
            "competition_score": prof.get("competition_score", ""),
            "competition_warnings": prof.get("competition_warnings", []),
            "deal_score": prof.get("deal_score", 0),
            "referral_fee": prof.get("referral_fee"),
            "fba_fee": prof.get("fba_fee"),
            "total_fees": prof.get("total_fees"),
            "skip_reason": prof.get("skip_reason", ""),
        },
        # Preserve extra fields
        "auto_ungated": result.get("auto_ungated", False),
        "pack_info": result.get("pack_info", {}),
    }


def schema_c_to_a(deal):
    """Convert a deal_scanner (Schema C) result to Schema A format.

    Schema C keys: deal_type, deal_score, current_price, historical_avg,
    asin, title, bsr, category, fba_seller_count, amazon_on_listing, etc.
    """
    if not deal:
        return deal

    # Already Schema A
    if "amazon" in deal and isinstance(deal["amazon"], dict):
        return deal

    current_price = deal.get("current_price") or deal.get("price", 0)
    historical_avg = deal.get("historical_avg", 0)

    return {
        "name": deal.get("title") or deal.get("name", ""),
        "retailer": "amazon",
        "url": "",
        "brand": deal.get("brand", ""),
        "amazon": {
            "asin": deal.get("asin", ""),
            "title": deal.get("title") or deal.get("name", ""),
            "amazon_price": current_price,
            "sales_rank": deal.get("bsr") or deal.get("sales_rank"),
            "fba_seller_count": deal.get("fba_seller_count"),
            "match_confidence": 1.0,  # Direct Amazon listing
            "match_method": "direct",
            "product_url": f"https://www.amazon.com/dp/{deal.get('asin', '')}",
            "category": deal.get("category", ""),
            "brand": deal.get("brand", ""),
        },
        "profitability": {
            "verdict": deal.get("verdict", "MAYBE"),
            "buy_cost": current_price,
            "sell_price": historical_avg or current_price,
            "profit_per_unit": deal.get("estimated_profit"),
            "roi_percent": deal.get("estimated_roi"),
            "deal_score": deal.get("deal_score", 0),
            "deal_type": deal.get("deal_type", ""),
        },
        "deal_metadata": {
            "deal_type": deal.get("deal_type", ""),
            "price_drop_pct": deal.get("price_drop_pct", 0),
            "historical_avg": historical_avg,
            "days_at_current": deal.get("days_at_current", 0),
        },
    }


def normalize_result(result):
    """Auto-detect schema and convert to Schema A.

    Heuristics:
      - Has 'amazon' dict → already Schema A
      - Has 'amazon_title' or 'estimated_profit' → Schema B (source.py)
      - Has 'deal_type' or 'historical_avg' → Schema C (deal_scanner)
    """
    if not result or not isinstance(result, dict):
        return result

    if "amazon" in result and isinstance(result["amazon"], dict):
        return result  # Already Schema A

    if "deal_type" in result or "historical_avg" in result:
        return schema_c_to_a(result)

    # Default: treat as Schema B
    return schema_b_to_a(result)


def normalize_results(results):
    """Normalize a list of results to Schema A."""
    if not results:
        return []
    return [normalize_result(r) for r in results]


def wrap_for_export(results, mode_name="", retailer="", source_url=""):
    """Wrap normalized results into the full JSON structure expected by
    export_to_sheets.py and sourcing_alerts.py.

    Args:
        results: List of Schema B or C results (auto-normalized).
        mode_name: Scan mode label (e.g., "Brand: CeraVe").
        retailer: Source retailer name.
        source_url: Source URL.

    Returns:
        Dict with keys: products, summary, source_url, retailer, timestamp.
    """
    normalized = normalize_results(results)

    buy_products = [p for p in normalized
                    if p.get("profitability", {}).get("verdict") == "BUY"]
    maybe_products = [p for p in normalized
                      if p.get("profitability", {}).get("verdict") == "MAYBE"]

    rois = [p["profitability"]["roi_percent"]
            for p in normalized
            if p.get("profitability", {}).get("roi_percent")]
    profits = [p["profitability"]["profit_per_unit"]
               for p in normalized
               if p.get("profitability", {}).get("profit_per_unit")]

    return {
        "products": normalized,
        "summary": {
            "total_analyzed": len(normalized),
            "buy_count": len(buy_products),
            "maybe_count": len(maybe_products),
            "avg_roi_percent": round(sum(rois) / len(rois), 1) if rois else 0,
            "avg_profit_per_unit": round(sum(profits) / len(profits), 2) if profits else 0,
            "mode": mode_name,
        },
        "source_url": source_url,
        "retailer": retailer,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
