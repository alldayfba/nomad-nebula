#!/usr/bin/env python3
from __future__ import annotations
"""
Script: deal_explainer.py
Purpose: Generate natural language explanations for why a deal is good or risky.

         Uses Claude Haiku for cost efficiency (~$0.001 per explanation).
         No competitor OA tool does this — differentiator for 247profits.

Usage:
    from execution.deal_explainer import explain_deal, explain_batch
    explanation = explain_deal(product_dict)
    explanations = explain_batch(products[:20])  # Batch for efficiency
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _build_deal_summary(product: dict) -> str:
    """Build a concise summary string for the AI to analyze."""
    parts = []
    parts.append(f"Product: {product.get('retailer_title') or product.get('amazon_title', 'Unknown')}")
    parts.append(f"Brand: {product.get('brand', 'Unknown')}")
    parts.append(f"Buy: ${product.get('retail_price', 0):.2f} → Sell: ${product.get('amazon_price', 0):.2f}")
    parts.append(f"Profit: ${product.get('profit', 0):.2f} | ROI: {product.get('roi_pct', 0):.1f}%")

    bsr = product.get("bsr")
    if bsr:
        parts.append(f"BSR: {bsr:,}")

    monthly = product.get("monthly_sales_est")
    if monthly:
        parts.append(f"Est. monthly sales: {monthly}")

    sellers = product.get("fba_sellers")
    if sellers is not None:
        parts.append(f"FBA sellers: {sellers}")

    amazon_on = product.get("amazon_on_listing")
    if amazon_on is True:
        parts.append("Amazon IS a seller on this listing")
    elif amazon_on is False:
        parts.append("Amazon is NOT on this listing")

    gating = product.get("gating_risk", "unknown")
    if gating in ("high", "medium"):
        parts.append(f"Gating risk: {gating}")

    ip_risk = product.get("ip_risk", "low")
    if ip_risk in ("high", "medium"):
        parts.append(f"IP complaint risk: {ip_risk}")

    price_stale = product.get("price_stale", False)
    if price_stale:
        age = product.get("price_age_days", "?")
        parts.append(f"Price data is {age} days old (stale)")

    weight = product.get("weight_lbs")
    if weight:
        parts.append(f"Weight: {weight:.1f} lbs")

    on_sale = product.get("on_sale", False)
    if on_sale:
        drop = product.get("price_drop_pct", 0)
        parts.append(f"Currently on sale ({drop:.0f}% off)")

    return " | ".join(parts)


def explain_deal(product: dict) -> str:
    """Generate a 1-2 sentence explanation of why this deal is good or risky.

    Uses Claude Haiku for cost efficiency.
    Falls back to rule-based explanation if API unavailable.
    """
    # Try AI explanation first
    if ANTHROPIC_API_KEY:
        try:
            return _ai_explain(product)
        except Exception:
            pass

    # Fallback: rule-based explanation
    return _rule_based_explain(product)


def _ai_explain(product: dict) -> str:
    """Generate AI-powered deal explanation using Claude Haiku."""
    import anthropic

    summary = _build_deal_summary(product)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"You are an Amazon FBA sourcing expert. In 1-2 sentences, explain whether this is a good deal to buy and resell on Amazon, and flag any risks. Be specific about the numbers.\n\n{summary}"
        }],
    )

    return response.content[0].text.strip()


def _rule_based_explain(product: dict) -> str:
    """Generate rule-based deal explanation (no API needed)."""
    parts = []
    roi = product.get("roi_pct", 0)
    profit = product.get("profit", 0)
    monthly = product.get("monthly_sales_est")
    sellers = product.get("fba_sellers")
    amazon_on = product.get("amazon_on_listing")
    gating = product.get("gating_risk", "none")
    ip_risk = product.get("ip_risk", "low")
    price_stale = product.get("price_stale", False)

    # Positive signals
    if roi >= 50:
        parts.append(f"Strong ROI at {roi:.0f}%")
    elif roi >= 30:
        parts.append(f"Good ROI at {roi:.0f}%")
    elif roi >= 15:
        parts.append(f"Moderate ROI at {roi:.0f}%")
    else:
        parts.append(f"Low ROI at {roi:.0f}% — thin margins")

    if profit >= 20:
        parts.append(f"${profit:.0f} profit per unit is excellent")
    elif profit >= 10:
        parts.append(f"${profit:.0f} profit per unit is solid")

    if monthly and monthly >= 100:
        parts.append(f"high velocity ({monthly} sales/mo)")
    elif monthly and monthly >= 20:
        parts.append(f"decent velocity ({monthly} sales/mo)")
    elif monthly and monthly < 10:
        parts.append(f"slow mover ({monthly} sales/mo)")

    if sellers is not None and 3 <= sellers <= 8:
        parts.append("healthy seller count")
    elif sellers is not None and sellers > 15:
        parts.append(f"crowded listing ({sellers} sellers)")

    # Risk signals
    risks = []
    if amazon_on:
        risks.append("Amazon competes on Buy Box")
    if gating == "high":
        risks.append("likely brand-gated")
    elif gating == "medium":
        risks.append("may be brand-gated")
    if ip_risk in ("high", "medium"):
        risks.append(f"IP complaint risk ({ip_risk})")
    if price_stale:
        risks.append("price data may be stale")

    explanation = ". ".join(parts) + "."
    if risks:
        explanation += " Risks: " + ", ".join(risks) + "."

    return explanation


def explain_batch(products: list[dict], max_products: int = 20) -> list[dict]:
    """Add explanations to a batch of products.

    Modifies products in-place, adding 'deal_explanation' field.

    Args:
        products: List of product dicts from pipeline output.
        max_products: Max products to explain (AI costs ~$0.001 each).

    Returns:
        Same list with 'deal_explanation' field added.
    """
    for i, p in enumerate(products[:max_products]):
        p["deal_explanation"] = explain_deal(p)

    # Products beyond max get rule-based only
    for p in products[max_products:]:
        p["deal_explanation"] = _rule_based_explain(p)

    return products
