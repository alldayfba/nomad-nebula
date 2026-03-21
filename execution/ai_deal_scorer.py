from __future__ import annotations
"""
AI Deal Scorer — Claude Haiku-powered deal analysis.
Replaces algorithmic deal_score with LLM reasoning that sees all signals at once.
Only runs on products that already pass hard filters (BUY or MAYBE from calc).
Cost: ~$0.00025 per product at Haiku prices.
"""
import json
import os
import sys
import logging

logger = logging.getLogger(__name__)


def score_deal_with_ai(product: dict, anthropic_client=None) -> dict:
    """
    Score a single deal using Claude Haiku.

    Args:
        product: Full product dict with profitability data
        anthropic_client: Optional pre-initialized Anthropic client

    Returns:
        {
            "ai_score": 0-100,
            "ai_verdict": "BUY" | "MAYBE" | "SKIP",
            "ai_buy_reason": str (why to buy),
            "ai_skip_reason": str (why to be cautious),
            "ai_summary": str (one sentence plain English verdict),
            "ai_confidence": "HIGH" | "MEDIUM" | "LOW"
        }
    """
    if anthropic_client is None:
        try:
            import anthropic
            from dotenv import load_dotenv
            load_dotenv()
            anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        except Exception as e:
            logger.warning(f"Could not initialize Anthropic client: {e}")
            return _fallback_score(product)

    prof = product.get("profitability", product)

    # Build the signal summary for the prompt
    signals = {
        "roi_percent": prof.get("roi_percent", 0),
        "profit_per_unit": prof.get("profit_per_unit", 0),
        "estimated_monthly_profit": prof.get("estimated_monthly_profit", 0),
        "bsr": prof.get("bsr") or product.get("bsr", "unknown"),
        "bsr_drops_30d": prof.get("bsr_drops_30d", 0),
        "bsr_drops_90d": prof.get("bsr_drops_90d", 0),
        "fba_seller_count": prof.get("fba_seller_count") or product.get("fba_seller_count", 0),
        "amazon_on_listing": prof.get("amazon_on_listing", False),
        "amazon_bb_pct_90d": prof.get("amazon_bb_pct_90d", 0),
        "match_confidence": product.get("match_confidence", 0),
        "match_method": product.get("match_method", "title"),
        "category": product.get("category", "unknown"),
        "brand": product.get("brand", "unknown"),
        "competition_score": prof.get("competition_score", "unknown"),
        "hazmat_risk": prof.get("hazmat_risk", False),
        "ip_risk": prof.get("ip_risk", False),
        "is_gated": prof.get("is_gated", False),
        "price_trend": prof.get("price_trend", "unknown"),
        "deal_score_algorithmic": prof.get("deal_score", 0),
        "verdict_algorithmic": prof.get("verdict", "SKIP"),
        "buy_cost": product.get("buy_cost", 0),
        "sell_price": prof.get("sell_price", 0),
        "max_cost": prof.get("max_cost", 0),
    }

    prompt = f"""You are an expert Amazon FBA online arbitrage analyst. Analyze this sourcing opportunity and provide a deal verdict.

PRODUCT SIGNALS:
{json.dumps(signals, indent=2)}

SCORING RULES:
- ROI < 20% OR profit < $2 → SKIP regardless
- Amazon on listing AND buy box % > 50% → SKIP (Amazon will dominate)
- IP risk flagged → downgrade to SKIP or strong MAYBE
- Match confidence < 0.80 (title match) → be more cautious
- BSR drops 30d < 5 → very slow mover, be cautious
- FBA seller count > 12 → heavy competition, margin pressure likely
- Deal score algorithmic < 40 → lean SKIP

RESPOND IN THIS EXACT JSON FORMAT (no other text):
{{
  "ai_score": <integer 0-100>,
  "ai_verdict": "<BUY|MAYBE|SKIP>",
  "ai_buy_reason": "<main reason to buy, or empty string if SKIP>",
  "ai_skip_reason": "<main risk or reason to be cautious>",
  "ai_summary": "<one sentence plain English: should a beginner buy this? Why or why not?>",
  "ai_confidence": "<HIGH|MEDIUM|LOW>"
}}"""

    try:
        import anthropic
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # Extract JSON
        if "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        result = json.loads(text)
        return result
    except Exception as e:
        logger.warning(f"AI deal scorer failed: {e}")
        return _fallback_score(product)


def _fallback_score(product: dict) -> dict:
    """Fallback to algorithmic score when AI is unavailable."""
    prof = product.get("profitability", product)
    score = prof.get("deal_score", 0)
    verdict = prof.get("verdict", "SKIP")
    return {
        "ai_score": score,
        "ai_verdict": verdict,
        "ai_buy_reason": "" if verdict == "SKIP" else f"ROI: {prof.get('roi_percent', 0):.0f}%, Profit: ${prof.get('profit_per_unit', 0):.2f}",
        "ai_skip_reason": prof.get("skip_reason", ""),
        "ai_summary": f"Algorithmic score: {score}/100. Verify manually.",
        "ai_confidence": "LOW",
    }


def batch_score_deals(products: list, max_batch: int = 20) -> list:
    """
    Score multiple products. Only scores BUY/MAYBE products (SKIPs are passed through).
    Limits batch to max_batch to control costs.
    """
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception as e:
        logger.warning(f"AI batch scorer unavailable: {e}")
        return products  # Return unchanged

    scored = []
    count = 0
    for product in products:
        prof = product.get("profitability", product)
        verdict = prof.get("verdict", "SKIP")
        if verdict in ("BUY", "MAYBE") and count < max_batch:
            ai_result = score_deal_with_ai(product, client)
            product = {**product, **ai_result}
            count += 1
        scored.append(product)
    return scored


if __name__ == "__main__":
    # Test with a sample product
    sample = {
        "brand": "Crayola",
        "category": "Arts & Crafts",
        "match_confidence": 0.92,
        "match_method": "title",
        "buy_cost": 5.99,
        "profitability": {
            "roi_percent": 45.2,
            "profit_per_unit": 4.20,
            "estimated_monthly_profit": 126.0,
            "bsr": 8500,
            "bsr_drops_30d": 28,
            "bsr_drops_90d": 82,
            "fba_seller_count": 4,
            "amazon_on_listing": False,
            "amazon_bb_pct_90d": 0.1,
            "competition_score": "MODERATE",
            "hazmat_risk": False,
            "ip_risk": False,
            "deal_score": 74,
            "verdict": "BUY",
            "sell_price": 14.99,
            "max_cost": 8.50,
        }
    }
    result = score_deal_with_ai(sample)
    print(json.dumps(result, indent=2))
