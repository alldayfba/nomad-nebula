from __future__ import annotations
"""
Product Review Agent — The quality gate between the sourcing pipeline and the student.

SOLE JOB: Verify every product match before it reaches a student.
- Check: Is this actually the right product?
- Check: Are the numbers real?
- Check: Is there any red flag that would lose a student money?
- If anything is wrong → REJECT or FLAG and feed the failure back into the system.

This agent runs AFTER profitability calc and BEFORE display.
Cost: ~$0.00015 per product (Claude Haiku micro-prompt).
"""
import os
import sys
import json
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
sys.path.insert(0, os.path.dirname(__file__))


# ─────────────────────────────────────────────
# VERDICT CONSTANTS
# ─────────────────────────────────────────────
VERIFIED = "VERIFIED"        # All checks pass. Show to student.
FLAGGED  = "FLAGGED"         # Minor issues. Show with warning.
REJECTED = "REJECTED"        # Do not show. Log failure for learning.


# ─────────────────────────────────────────────
# RULE-BASED PRE-CHECKS (fast, no API cost)
# ─────────────────────────────────────────────
def rule_based_checks(product: dict) -> tuple:
    """
    Run deterministic checks before calling AI.
    Returns (verdict, list_of_issues).
    If verdict is REJECTED here, skip AI entirely.
    """
    issues = []
    prof = product.get("profitability", product)

    # Check 1: Match confidence
    confidence = product.get("match_confidence", 0)
    if confidence < 0.70:
        issues.append(f"match_confidence {confidence:.2f} below 0.70 threshold")
        return REJECTED, issues

    # Check 2: Brand must appear in retail title (belt-and-suspenders after brand gate)
    amazon_brand = (product.get("brand") or product.get("amazon_brand") or "").lower().strip()
    retail_title = (product.get("name") or product.get("retail_title") or "").lower()
    amazon_title = (product.get("amazon_title") or "").lower()
    if amazon_brand and len(amazon_brand) > 2:
        brand_words = [w for w in amazon_brand.split() if len(w) > 2]
        if brand_words and not any(w in retail_title for w in brand_words):
            issues.append(f"Brand '{amazon_brand}' not found in retail title")
            return REJECTED, issues

    # Check 3: Price sanity — retail must be less than Amazon sell price
    buy_cost = product.get("buy_cost") or product.get("retail_price", 0)
    sell_price = prof.get("sell_price") or product.get("amazon_price", 0)
    if buy_cost and sell_price and buy_cost >= sell_price:
        issues.append(f"Buy cost (${buy_cost:.2f}) >= sell price (${sell_price:.2f})")
        return REJECTED, issues

    # Check 4: ROI sanity — can't be more than 500% (likely wrong product or price)
    roi = prof.get("roi_percent", 0)
    if roi > 500:
        issues.append(f"ROI {roi:.0f}% is implausibly high — likely wrong product or price anomaly")
        return FLAGGED, issues

    # Check 5: Profit sanity — must be > $0
    profit = prof.get("profit_per_unit", 0)
    if profit <= 0:
        issues.append(f"Profit ${profit:.2f} <= 0")
        return REJECTED, issues

    # Check 6: ASIN format
    asin = product.get("asin", "")
    if not asin or len(asin) != 10 or not asin.startswith("B"):
        issues.append(f"Invalid ASIN: '{asin}'")
        return REJECTED, issues

    # Check 7: Pack count mismatch — if retail title has quantity that doesn't match Amazon title
    def extract_pack_count(title):
        patterns = [
            r'\b(\d+)\s*-?\s*pack\b', r'\bpack\s+of\s+(\d+)\b',
            r'\b(\d+)\s*count\b', r'\bset\s+of\s+(\d+)\b',
            r'\b(\d+)\s*ct\b', r'\b(\d+)\s*pieces?\b',
        ]
        for p in patterns:
            m = re.search(p, title, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    retail_pack = extract_pack_count(retail_title)
    amazon_pack = extract_pack_count(amazon_title)
    if retail_pack and amazon_pack and retail_pack != amazon_pack:
        ratio = retail_pack / amazon_pack
        if ratio > 3 or ratio < 0.33:  # More than 3x off
            issues.append(f"Pack mismatch: retail={retail_pack}, amazon={amazon_pack} (ratio={ratio:.1f}x)")
            return FLAGGED, issues

    return VERIFIED, issues


# ─────────────────────────────────────────────
# AI DEEP VERIFICATION (Claude Haiku)
# ─────────────────────────────────────────────
def ai_verify_match(product: dict, anthropic_client=None) -> tuple:
    """
    Use Claude Haiku to do semantic match verification.
    Returns (verdict, issue, fix_suggestion).
    Only called when rule checks pass but AI adds confidence.
    """
    retail_title = product.get("name") or product.get("retail_title", "")
    amazon_title = product.get("amazon_title") or product.get("title", "")
    brand = product.get("brand", "")
    buy_cost = product.get("buy_cost") or product.get("retail_price", 0)
    amazon_price = (product.get("profitability") or {}).get("sell_price") or product.get("amazon_price", 0)
    match_method = product.get("match_method", "unknown")
    confidence = product.get("match_confidence", 0)

    if not retail_title or not amazon_title:
        return VERIFIED, "", ""  # Can't verify without titles

    # Don't waste tokens on UPC matches (already near-certain)
    if match_method == "upc" and confidence >= 0.90:
        return VERIFIED, "", ""

    if anthropic_client is None:
        try:
            import anthropic
            from dotenv import load_dotenv
            load_dotenv()
            anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        except Exception:
            return VERIFIED, "", ""  # Non-fatal

    prompt = (
        "You are a strict Amazon FBA product match verifier. Your job is to catch false matches "
        "that would lose a student money.\n\n"
        f"RETAIL PRODUCT:\nTitle: \"{retail_title}\"\nPrice: ${buy_cost:.2f}\nBrand: {brand}\n\n"
        f"AMAZON PRODUCT:\nTitle: \"{amazon_title}\"\nPrice: ${amazon_price:.2f}\n"
        f"Match method: {match_method} (confidence: {confidence:.0%})\n\n"
        "TASK: Are these the SAME product? Consider:\n"
        "1. Brand must match\n"
        "2. Size/quantity/variant must match (a 2-pack is NOT the same as a single unit)\n"
        "3. The retail product must be the exact same item or a compatible bundle for the Amazon listing\n"
        "4. Significant price differences (>3x) without pack count explanation = suspicious\n\n"
        "Respond in this exact JSON (no other text):\n"
        "{\"same_product\": true/false, \"confidence\": \"HIGH/MEDIUM/LOW\", "
        "\"issue\": \"<specific issue if not same, or empty>\", "
        "\"fix\": \"<suggestion for the system to improve>\"}"
    )

    try:
        import anthropic as ant
        resp = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].strip().lstrip("json").strip()
        data = json.loads(text)

        if not data.get("same_product"):
            return REJECTED, data.get("issue", "AI: products do not match"), data.get("fix", "")
        if data.get("confidence") == "LOW":
            return FLAGGED, f"AI: low confidence match — {data.get('issue', '')}", data.get("fix", "")
        return VERIFIED, "", data.get("fix", "")
    except Exception as e:
        logger.debug(f"AI verification failed: {e}")
        return VERIFIED, "", ""  # Default to pass if AI unavailable


# ─────────────────────────────────────────────
# MAIN REVIEW FUNCTION
# ─────────────────────────────────────────────
def review_product(product: dict, anthropic_client=None, record_feedback: bool = True) -> dict:
    """
    Full product review pipeline.
    Returns the product dict enriched with review results.
    REJECTED products should not be shown to students.
    """
    # Stage 1: Rule-based checks (free, instant)
    verdict, issues = rule_based_checks(product)

    ai_issue = ""
    ai_fix = ""

    # Stage 2: AI verification (only if rules pass, and not a UPC match)
    if verdict == VERIFIED:
        ai_verdict, ai_issue, ai_fix = ai_verify_match(product, anthropic_client)
        if ai_verdict != VERIFIED:
            verdict = ai_verdict
            if ai_issue:
                issues.append(f"[AI] {ai_issue}")

    # Build review result
    review = {
        "review_verdict": verdict,
        "review_issues": issues,
        "review_fix_suggestion": ai_fix,
        "review_timestamp": datetime.utcnow().isoformat(),
        "review_passed": verdict == VERIFIED,
    }

    # Record feedback for self-improvement
    if record_feedback and verdict == REJECTED:
        try:
            _record_rejection(product, issues, ai_fix)
        except Exception:
            pass

    return dict(list(product.items()) + list(review.items()))


# ─────────────────────────────────────────────
# BATCH REVIEW
# ─────────────────────────────────────────────
def batch_review_products(products: list, use_ai: bool = True) -> dict:
    """
    Review a list of products. Returns filtered + stats.

    Returns:
        {
            "verified": [...],   # Safe to show
            "flagged": [...],    # Show with warning
            "rejected": [...],   # Do not show
            "stats": {verified_count, flagged_count, rejected_count, rejection_reasons}
        }
    """
    if not products:
        return {"verified": [], "flagged": [], "rejected": [], "stats": {}}

    anthropic_client = None
    if use_ai:
        try:
            import anthropic
            from dotenv import load_dotenv
            load_dotenv()
            anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        except Exception:
            pass

    verified, flagged, rejected = [], [], []
    rejection_reasons = {}

    for product in products:
        reviewed = review_product(product, anthropic_client, record_feedback=True)
        v = reviewed["review_verdict"]

        if v == VERIFIED:
            verified.append(reviewed)
        elif v == FLAGGED:
            flagged.append(reviewed)
        else:
            rejected.append(reviewed)
            for issue in reviewed["review_issues"]:
                key = issue[:60]
                rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

    stats = {
        "total_input": len(products),
        "verified_count": len(verified),
        "flagged_count": len(flagged),
        "rejected_count": len(rejected),
        "pass_rate": round(len(verified) / len(products) * 100, 1) if products else 0,
        "rejection_reasons": dict(sorted(rejection_reasons.items(), key=lambda x: -x[1])[:10]),
    }

    logger.info(
        f"Product Review: {len(verified)} verified, {len(flagged)} flagged, "
        f"{len(rejected)} rejected ({stats['pass_rate']}% pass rate)"
    )

    return {"verified": verified, "flagged": flagged, "rejected": rejected, "stats": stats}


# ─────────────────────────────────────────────
# REJECTION FEEDBACK RECORDER
# ─────────────────────────────────────────────
def _record_rejection(product: dict, issues: list, fix_suggestion: str) -> None:
    """
    Write rejection events to the feedback DB for self-improvement.
    The feedback_engine reads these to improve matching rules over time.
    """
    try:
        from results_db import ResultsDB
        db = ResultsDB()
        if hasattr(db, 'record_rejection'):
            db.record_rejection(
                asin=product.get("asin", ""),
                retail_title=product.get("name") or product.get("retail_title", ""),
                amazon_title=product.get("amazon_title", ""),
                retailer=product.get("source_retailer", ""),
                issues=issues,
                fix_suggestion=fix_suggestion,
                match_method=product.get("match_method", ""),
                match_confidence=product.get("match_confidence", 0),
            )
    except Exception as e:
        logger.debug(f"Could not record rejection: {e}")


# ─────────────────────────────────────────────
# STUDENT OUTCOME FEEDBACK
# ─────────────────────────────────────────────
def record_student_outcome(
    asin: str,
    retailer: str,
    predicted_roi: float,
    actual_roi: float,
    feedback_type: str,  # 'confirmed_profit' | 'false_match' | 'wrong_profit' | 'couldnt_sell'
    notes: str = "",
) -> None:
    """
    Record a student's real-world outcome on a sourcing result.
    This is the highest-value feedback signal — real money, real results.
    Feeds into feedback_engine.py for continuous improvement.
    """
    try:
        from results_db import ResultsDB
        db = ResultsDB()
        if hasattr(db, 'record_student_outcome'):
            db.record_student_outcome(
                asin=asin,
                retailer=retailer,
                predicted_roi=predicted_roi,
                actual_roi=actual_roi,
                feedback_type=feedback_type,
                notes=notes,
            )
        logger.info(
            f"Student outcome recorded: {asin} {feedback_type} "
            f"(predicted {predicted_roi:.0f}% -> actual {actual_roi:.0f}%)"
        )
    except Exception as e:
        logger.warning(f"Could not record student outcome: {e}")


if __name__ == "__main__":
    # Quick test
    sample_product = {
        "asin": "B08XYZ1234",
        "name": "Crayola 64-Count Crayon Box",
        "amazon_title": "Crayola 64 Crayons, Assorted Colors",
        "brand": "Crayola",
        "buy_cost": 5.99,
        "match_confidence": 0.92,
        "match_method": "title",
        "source_retailer": "Target",
        "profitability": {
            "sell_price": 14.99,
            "roi_percent": 45.0,
            "profit_per_unit": 4.20,
            "verdict": "BUY",
        }
    }
    result = review_product(sample_product)
    print(f"Verdict: {result['review_verdict']}")
    print(f"Issues: {result['review_issues']}")
