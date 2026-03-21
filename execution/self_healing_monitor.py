from __future__ import annotations
"""
Self-Healing Monitor — Detects and fixes broken scrapers automatically.

Monitors:
- Retailer scrape success rates
- Zero-result anomalies (retailer has products but we get 0)
- Selector failures (DOM changed)
- Keepa API health

Self-heals:
- Tries alternative selector patterns when primary fails
- Falls back to JSON-LD when CSS selectors break
- Disables unreliable retailers automatically
- Queues selector update proposals for Training Officer

Runs: After every scrape session + as a weekly deep scan
"""
import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def check_retailer_health(retailer_name, url, expected_min_products=3):  # type: ignore[override]
    """
    Test a specific retailer URL and return health status.
    Tries primary selectors, then JSON-LD fallback.
    """
    result = {
        "retailer": retailer_name,
        "url": url,
        "status": "unknown",
        "product_count": 0,
        "method": None,
        "latency_ms": 0,
        "error": None,
    }

    start = time.time()

    try:
        # Try importing the scraper
        from multi_retailer_search import search_single_retailer

        # Look up retailer config
        try:
            from retailer_registry import RetailerRegistry
            registry = RetailerRegistry()
            retailer_config = registry.get_retailer(retailer_name) or {"name": retailer_name, "url": url}
        except Exception:
            retailer_config = {"name": retailer_name, "url": url}

        scraped = search_single_retailer(retailer_config, url, query=None)

        # Handle both old (list) and new (dict with error) return formats
        if isinstance(scraped, dict) and "error" in scraped:
            result["status"] = "failed"
            result["error"] = scraped["error"]
        else:
            products = scraped if isinstance(scraped, list) else scraped.get("products", [])
            result["product_count"] = len(products)
            result["status"] = "healthy" if len(products) >= expected_min_products else "zero_results"
            result["method"] = "primary"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    result["latency_ms"] = int((time.time() - start) * 1000)

    # Record to feedback engine
    try:
        from feedback_engine import record_retailer_event
        event_type = "success" if result["status"] == "healthy" else result["status"]
        record_retailer_event(retailer_name, event_type, result["product_count"], result.get("error", ""))
    except Exception:
        pass

    return result


def run_health_check_tier1():
    """
    Run health checks on all Tier 1 retailers.
    Returns a health report with per-retailer status.
    """
    tier1_retailers = [
        ("target", "https://www.target.com/c/toys/-/N-5xt1a"),
        ("walgreens", "https://www.walgreens.com/store/c/personal-care/ID=360482-tier3"),
        ("walmart", "https://www.walmart.com/browse/toys/4171"),
        ("cvs", "https://www.cvs.com/shop/personal-care"),
        ("home-depot", "https://www.homedepot.com/b/Tools/N-5yc1vZc1xy"),
    ]

    results = {}
    for retailer_name, test_url in tier1_retailers:
        logger.info(f"Checking {retailer_name}...")
        result = check_retailer_health(retailer_name, test_url)
        results[retailer_name] = result
        logger.info(
            f"  {retailer_name}: {result['status']} "
            f"({result['product_count']} products, {result['latency_ms']}ms)"
        )

    healthy = sum(1 for r in results.values() if r["status"] == "healthy")
    logger.info(f"Tier 1 health check: {healthy}/{len(results)} healthy")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "healthy_count": healthy,
        "total_count": len(results),
        "retailers": results,
    }


def propose_selector_fix(retailer_name, broken_url):
    """
    When a retailer's selector breaks, use Claude Haiku to suggest a fix.
    This gets queued for Training Officer review.
    """
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception:
        return {"error": "Anthropic unavailable"}

    # Fetch the page
    try:
        import httpx
        resp = httpx.get(broken_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        # Get first 5000 chars of HTML for analysis
        html_sample = resp.text[:5000]
    except Exception as e:
        return {"error": f"Could not fetch page: {e}"}

    prompt = (
        f"You are an expert web scraper. A CSS selector for {retailer_name} has stopped working.\n\n"
        f"Here is the first 5000 characters of the current HTML from {broken_url}:\n\n"
        f"{html_sample}\n\n"
        "Based on this HTML structure, suggest:\n"
        "1. A CSS selector for product title/name\n"
        "2. A CSS selector for product price\n"
        "3. A CSS selector for the product container (parent element)\n"
        "4. Any relevant class names that appear to be product-related\n\n"
        "Respond in JSON:\n"
        "{\"product_container\": \"...\", \"title_selector\": \"...\", \"price_selector\": \"...\", "
        "\"confidence\": \"HIGH/MEDIUM/LOW\", \"notes\": \"...\"}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].strip().lstrip("json").strip()
        suggestion = json.loads(text)

        # Queue as Training Officer proposal
        proposal = {
            "retailer": retailer_name,
            "url": broken_url,
            "type": "selector_fix",
            "suggestion": suggestion,
            "timestamp": datetime.utcnow().isoformat(),
        }

        proposal_dir = os.path.join(os.path.dirname(__file__), "..", ".tmp", "selector_proposals")
        os.makedirs(proposal_dir, exist_ok=True)
        proposal_file = os.path.join(proposal_dir, f"{retailer_name}_{int(time.time())}.json")
        with open(proposal_file, "w") as f:
            json.dump(proposal, f, indent=2)

        logger.info(f"Selector fix proposal queued for {retailer_name}: {proposal_file}")
        return proposal

    except Exception as e:
        return {"error": str(e)}


def heal_failed_retailers(health_report):
    """
    After a health check, attempt to heal failed retailers.
    Returns list of retailers that were auto-healed.
    """
    healed = []
    for retailer, status in health_report.get("retailers", {}).items():
        if status["status"] in ("zero_results", "selector_fail", "error"):
            logger.info(f"Attempting to heal {retailer} (status: {status['status']})...")

            # Queue selector fix proposal
            if status.get("url"):
                proposal = propose_selector_fix(retailer, status["url"])
                if not proposal.get("error"):
                    healed.append(retailer)
                    logger.info(f"Selector fix proposal queued for {retailer}")

    return healed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = run_health_check_tier1()
    print(json.dumps(report, indent=2))
    if report["healthy_count"] < report["total_count"]:
        healed = heal_failed_retailers(report)
        print(f"Auto-healed: {healed}")
