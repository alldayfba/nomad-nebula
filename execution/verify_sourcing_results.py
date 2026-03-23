#!/usr/bin/env python3
"""
Script: verify_sourcing_results.py
Purpose: Mega verification layer for sourcing output quality.
         Every sourcing result passes through this before being shown to the user.
         Validates buy links, product identity, pricing math, and retailer legitimacy.

Usage:
    from verify_sourcing_results import verify_results
    verification = verify_results(results, strict=True)
    # verification["verified"] = passed all checks
    # verification["flagged"]  = passed with warnings (RESEARCH verdict)
    # verification["rejected"] = failed checks, not shown
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional

# Import retailer whitelist
try:
    from retailer_registry import get_retailer
except ImportError:
    from execution.retailer_registry import get_retailer

# Import pack size detection
try:
    from calculate_fba_profitability import _extract_pack_quantity, _extract_weight_oz
except ImportError:
    from execution.calculate_fba_profitability import _extract_pack_quantity, _extract_weight_oz


# ── Known Amazon domains ─────────────────────────────────────────────────────
AMAZON_DOMAINS = {
    "amazon.com", "www.amazon.com", "smile.amazon.com",
    "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.co.jp",
}

# ── Modes that legitimately have no retail buy link ──────────────────────────
NO_RETAIL_LINK_MODES = {"FINDER_CANDIDATE", "OOS_OPPORTUNITY", "A2A_WAREHOUSE", "A2A_VARIATION"}

# ── ASIN regex ───────────────────────────────────────────────────────────────
ASIN_PATTERN = re.compile(r"^B[A-Z0-9]{9}$")


def _get_source_url(result: dict) -> str:
    """Extract source/buy URL from result, checking all known field names."""
    for key in ("source_url", "buy_url", "retail_url", "url"):
        val = result.get(key, "")
        if val and val != "N/A" and val.startswith("http"):
            return val
    return ""


def _get_amazon_url(result: dict) -> str:
    """Extract or construct Amazon URL from result."""
    asin = result.get("asin", "")
    explicit = result.get("amazon_url", "")
    if explicit and "amazon.com/dp/" in explicit:
        return explicit
    if asin and ASIN_PATTERN.match(asin):
        return f"https://www.amazon.com/dp/{asin}"
    return ""


def _is_valid_retailer_url(url: str) -> tuple:
    """Check if URL domain is a known retailer. Returns (is_valid, retailer_name)."""
    if not url:
        return False, ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return False, ""

    # Amazon domains are valid for A2A mode
    if domain in AMAZON_DOMAINS or "amazon." in domain:
        return True, "Amazon"

    retailer = get_retailer(domain)
    if retailer:
        return True, retailer.get("name", domain)
    return False, ""


def _check_retailer_match(result: dict, url: str) -> tuple:
    """Check if URL domain matches the stated retailer in the result."""
    stated_retailer = (result.get("retailer", "") or result.get("source_retailer", "")).lower().strip()
    if not stated_retailer or not url:
        return True, ""  # Can't check, pass

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return False, f"Invalid URL: {url}"

    # Check if domain contains the retailer name or vice versa
    domain_base = domain.split(".")[0]
    if stated_retailer in domain_base or domain_base in stated_retailer:
        return True, ""

    # Check via registry
    retailer = get_retailer(domain)
    if retailer:
        reg_name = retailer.get("name", "").lower()
        if stated_retailer in reg_name or reg_name in stated_retailer:
            return True, ""

    return False, f"Retailer mismatch: stated '{stated_retailer}' but URL domain is '{domain}'"


def _title_word_overlap(title_a: str, title_b: str) -> float:
    """Calculate word overlap between two titles (0.0 - 1.0)."""
    if not title_a or not title_b:
        return 0.0
    stop_words = {"the", "a", "an", "and", "or", "for", "with", "in", "of", "to", "by", "-", "&", "+"}
    words_a = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", title_a)} - stop_words
    words_b = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", title_b)} - stop_words
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b))


def verify_single(result: dict, strict: bool = True) -> dict:
    """Verify a single sourcing result. Returns result with verification metadata."""
    issues = []
    warnings = []
    verified = True

    asin = result.get("asin", "")
    verdict = result.get("verdict", "")
    mode = result.get("match_method", "") or result.get("mode", "")
    buy_price = result.get("buy_price") or result.get("retail_price") or 0
    amazon_price = result.get("amazon_price") or result.get("sell_price") or 0
    profit = result.get("profit") or result.get("estimated_profit") or 0
    roi = result.get("roi") or 0
    retail_title = result.get("retail_title", "") or result.get("name", "")
    amazon_title = result.get("title", "") or result.get("amazon_title", "")
    match_confidence = result.get("match_confidence") or result.get("confidence") or 0

    source_url = _get_source_url(result)
    amazon_url = _get_amazon_url(result)

    # ── Check 1: ASIN format ─────────────────────────────────────────────
    if not asin:
        issues.append("Missing ASIN")
        verified = False
    elif not ASIN_PATTERN.match(asin):
        issues.append(f"Invalid ASIN format: {asin}")
        verified = False

    # ── Check 2: Amazon URL ──────────────────────────────────────────────
    if not amazon_url:
        issues.append("Missing Amazon URL")
        verified = False
    else:
        # Ensure it's correctly formatted
        result["amazon_url"] = amazon_url

    # ── Check 3: Buy link exists ─────────────────────────────────────────
    is_no_link_mode = verdict in NO_RETAIL_LINK_MODES or mode in NO_RETAIL_LINK_MODES
    if not source_url:
        if is_no_link_mode:
            # Expected — these modes don't have retail links
            if verdict not in ("RESEARCH", "SKIP"):
                warnings.append("No buy link (expected for this mode) — marked RESEARCH")
                result["verdict"] = "RESEARCH"
                result["verdict_note"] = "No retail buy link — find at retail manually"
        else:
            issues.append("Missing buy link — no retailer URL to purchase from")
            if verdict in ("BUY", "MAYBE"):
                result["verdict"] = "RESEARCH"
                result["verdict_note"] = "Downgraded: no verified buy link"
            verified = False

    # ── Check 4: Buy link is a real retailer ─────────────────────────────
    if source_url:
        is_valid, retailer_name = _is_valid_retailer_url(source_url)
        if not is_valid:
            issues.append(f"Buy link domain not a known retailer: {source_url}")
            if strict:
                verified = False
                if verdict in ("BUY", "MAYBE"):
                    result["verdict"] = "RESEARCH"
                    result["verdict_note"] = "Unknown retailer — verify manually"

    # ── Check 5: Retailer name matches URL domain ────────────────────────
    if source_url:
        matches, mismatch_msg = _check_retailer_match(result, source_url)
        if not matches:
            issues.append(mismatch_msg)
            if strict:
                verified = False

    # ── Check 6: Buy price < Amazon price (basic arbitrage check) ────────
    if buy_price and amazon_price:
        if buy_price >= amazon_price:
            issues.append(f"Not arbitrage: buy ${buy_price:.2f} >= Amazon ${amazon_price:.2f}")
            verified = False
            result["verdict"] = "SKIP"
            result["verdict_note"] = "Buy price exceeds Amazon price"

    # ── Check 7: Price sanity bounds ─────────────────────────────────────
    if buy_price:
        if buy_price < 0.50:
            warnings.append(f"Suspiciously low buy price: ${buy_price:.2f}")
        if buy_price > 500:
            warnings.append(f"High buy price: ${buy_price:.2f} — verify capital risk")
    if amazon_price:
        if amazon_price > 2000:
            warnings.append(f"Unusually high Amazon price: ${amazon_price:.2f} — verify listing")
        if amazon_price < 1.00 and not is_no_link_mode:
            warnings.append(f"Very low Amazon price: ${amazon_price:.2f} — may not be worth it")

    # ── Check 8: ROI sanity cap ──────────────────────────────────────────
    if roi and roi > 1000:
        warnings.append(f"ROI {roi:.0f}% exceeds 1000% — likely pack mismatch or wrong match")
        if verdict == "BUY":
            result["verdict"] = "MAYBE"
            result["verdict_note"] = f"Capped: ROI {roi:.0f}% suspiciously high — verify pack sizes"

    # ── Check 8b: Price ratio pack mismatch (NEW) ────────────────────────
    # If Amazon is 3x+ more expensive than retail buy price and pack counts
    # can't be confirmed from both titles, it's almost certainly a pack mismatch
    if buy_price > 0 and amazon_price > 0 and amazon_price / buy_price >= 3.0:
        price_ratio = amazon_price / buy_price
        retail_has_pack = bool(re.search(r'\d+\s*(?:pack|count|ct|pk)\b', retail_title.lower())) if retail_title else False
        amazon_has_pack = bool(re.search(r'\d+\s*(?:pack|count|ct|pk)\b', amazon_title.lower())) if amazon_title else False
        if not (retail_has_pack and amazon_has_pack):
            issues.append(f"Price ratio {price_ratio:.1f}x with unconfirmed pack sizes — likely mismatch")
            verified = False
            result["verdict"] = "SKIP"
            result["verdict_note"] = f"Rejected: ${buy_price:.2f} retail vs ${amazon_price:.2f} Amazon ({price_ratio:.0f}x ratio) — pack mismatch"

    # ── Check 8c: Buy link must be product page, not category (NEW) ──────
    if source_url:
        bad_patterns = ["/productlist/", "/browse/", "/sale-event/",
                        "?q=", "/search/", "Brands=yes", "/c/"]
        product_patterns = ["/p/", "/product/", "/dp/", "/ip/", "/A-", "ID=prod"]
        is_category = any(pat in source_url for pat in bad_patterns)
        is_product = any(pat in source_url for pat in product_patterns)
        if is_category and not is_product:
            issues.append(f"Buy link is a category page, not a product: {source_url[:80]}")
            verified = False

    # ── Check 9: Pack size cross-check ───────────────────────────────────
    if retail_title and amazon_title:
        retail_pack = _extract_pack_quantity(retail_title)
        amazon_pack = _extract_pack_quantity(amazon_title)
        if retail_pack != amazon_pack and amazon_pack > 1:
            warnings.append(
                f"Pack mismatch: retail={retail_pack}-pack, Amazon={amazon_pack}-pack"
            )
            if verdict in ("BUY", "MAYBE"):
                result["verdict"] = "RESEARCH"
                result["verdict_note"] = f"Pack mismatch detected ({retail_pack} vs {amazon_pack}) — verify before buying"

    # ── Check 9b: Price stability (NEW) ────────────────────────────────
    # If current Amazon price is >20% above 90-day average, it's a spike
    price_stability = result.get("price_stability", {})
    avg90 = price_stability.get("avg_90d") or result.get("avg90_price")
    if avg90 and avg90 > 0 and amazon_price > 0:
        spike_pct = ((amazon_price - avg90) / avg90) * 100
        if spike_pct > 20:
            warnings.append(f"PRICE SPIKE: current ${amazon_price:.2f} is {spike_pct:.0f}% above 90-day avg ${avg90:.2f} — may revert")
            if verdict == "BUY":
                result["verdict"] = "MAYBE"
                result["verdict_note"] = f"Price spike detected ({spike_pct:.0f}% above 90d avg)"

    # ── Check 9c: Price sensitivity (NEW) ────────────────────────────────
    # Would this still be profitable if Amazon price drops 15%?
    if amazon_price > 0 and buy_price > 0:
        stressed_price = amazon_price * 0.85
        stressed_fees = stressed_price * 0.15 + 5.0  # rough fee estimate
        stressed_profit = stressed_price - buy_price - stressed_fees
        if stressed_profit <= 0:
            warnings.append(f"THIN MARGIN: unprofitable if Amazon price drops 15% (to ${stressed_price:.2f})")
            if verdict == "BUY":
                result["verdict"] = "MAYBE"
                result["verdict_note"] = "Thin margin — vulnerable to price drop"

    # ── Check 10: Title similarity ───────────────────────────────────────
    if retail_title and amazon_title and not is_no_link_mode:
        similarity = _title_word_overlap(retail_title, amazon_title)
        if similarity < 0.25:
            issues.append(f"Title similarity too low ({similarity:.0%}) — likely wrong product")
            if strict:
                verified = False
                result["verdict"] = "SKIP"
                result["verdict_note"] = "Product mismatch — titles don't match"
        elif similarity < 0.50:
            warnings.append(f"Low title similarity ({similarity:.0%}) — verify match")

    # ── Check 11: Match confidence threshold ─────────────────────────────
    if match_confidence and match_confidence < 0.40 and not is_no_link_mode:
        issues.append(f"Match confidence too low: {match_confidence:.0%}")
        verified = False

    # ── Normalize source_url field ───────────────────────────────────────
    if source_url:
        result["source_url"] = source_url
    result["_verification"] = {
        "verified": verified and not issues,
        "issues": issues,
        "warnings": warnings,
    }

    return result


def verify_results(results: List[Dict[str, Any]], strict: bool = True) -> Dict[str, Any]:
    """Verify a list of sourcing results.

    Args:
        results: List of product result dicts from sourcing pipeline.
        strict: If True, unknown retailers and low similarity → reject.

    Returns:
        {
            "verified": [...],   # Passed all checks, safe to show
            "flagged": [...],    # Passed but with warnings (RESEARCH verdict)
            "rejected": [...],   # Failed checks, not shown
            "summary": { "total", "verified", "flagged", "rejected" }
        }
    """
    verified = []
    flagged = []
    rejected = []
    seen_asins = set()

    for r in results:
        result = verify_single(r, strict=strict)
        v = result.get("_verification", {})

        # Dedup by ASIN — keep first (usually best ROI from pipeline sort)
        asin = result.get("asin", "")
        if asin and asin in seen_asins:
            result["_verification"]["issues"].append("Duplicate ASIN — already in results")
            rejected.append(result)
            continue
        if asin:
            seen_asins.add(asin)

        if v.get("issues"):
            rejected.append(result)
        elif v.get("warnings"):
            flagged.append(result)
        else:
            verified.append(result)

    return {
        "verified": verified,
        "flagged": flagged,
        "rejected": rejected,
        "summary": {
            "total": len(results),
            "verified": len(verified),
            "flagged": len(flagged),
            "rejected": len(rejected),
        },
    }


# ── CLI for standalone testing ───────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python verify_sourcing_results.py <results.json>")
        print("  Reads a sourcing results JSON file and verifies each product.")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    # Handle both list and dict-with-results formats
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results", data.get("products", []))
    else:
        print("Error: JSON must be a list or dict with 'results' key")
        sys.exit(1)

    verification = verify_results(results)
    s = verification["summary"]
    print(f"\n{'='*60}")
    print(f"  VERIFICATION RESULTS")
    print(f"  Total: {s['total']} | Verified: {s['verified']} | "
          f"Flagged: {s['flagged']} | Rejected: {s['rejected']}")
    print(f"{'='*60}\n")

    if verification["verified"]:
        print("VERIFIED (safe to show):")
        for r in verification["verified"]:
            print(f"  [{r.get('verdict', '?')}] {r.get('asin', '?')} — {r.get('title', r.get('name', '?'))[:60]}")
            print(f"    Buy: {_get_source_url(r)} | Amazon: {_get_amazon_url(r)}")

    if verification["flagged"]:
        print("\nFLAGGED (warnings — show as RESEARCH):")
        for r in verification["flagged"]:
            w = r.get("_verification", {}).get("warnings", [])
            print(f"  [{r.get('verdict', '?')}] {r.get('asin', '?')} — {r.get('title', r.get('name', '?'))[:60]}")
            for warn in w:
                print(f"    ⚠ {warn}")

    if verification["rejected"]:
        print("\nREJECTED (not shown):")
        for r in verification["rejected"]:
            issues = r.get("_verification", {}).get("issues", [])
            print(f"  {r.get('asin', '?')} — {(r.get('title') or r.get('name') or '?')[:60]}")
            for issue in issues:
                print(f"    ✗ {issue}")
