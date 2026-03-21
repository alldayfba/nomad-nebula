#!/usr/bin/env python3
"""
Script: deal_feed_scanner.py
Purpose: Parse deal RSS feeds (SlickDeals, DealNews, TotallyTarget, Hip2Save)
         to find products with low prices, then match against Amazon for arbitrage.

Cost: $0 for RSS feeds (free, unlimited). Keepa tokens only for Amazon verification.

Usage:
  python execution/deal_feed_scanner.py --sources all --max 50
  python execution/deal_feed_scanner.py --sources slickdeals,dealnews --max 30
  python execution/deal_feed_scanner.py --sources totallytarget --max 20
"""

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))

# ── RSS Feed Configuration ──────────────────────────────────────────────────

FEED_SOURCES = {
    "slickdeals": {
        "url": "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1",
        "name": "SlickDeals",
        "type": "rss",
    },
    "dealnews": {
        "url": "https://www.dealnews.com/rss/",
        "name": "DealNews",
        "type": "rss",
    },
    "totallytarget": {
        "url": "https://totallytarget.com/feed/",
        "name": "TotallyTarget",
        "type": "rss",
    },
    "hip2save": {
        "url": "https://hip2save.com/feed/",
        "name": "Hip2Save",
        "type": "rss",
    },
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Retailers we care about for OA sourcing
OA_RETAILERS = {
    "walmart", "target", "walgreens", "cvs", "costco", "home depot",
    "kohl's", "kohls", "amazon", "best buy", "staples", "office depot",
    "kroger", "meijer", "rite aid", "dollar general", "dollar tree",
    "big lots", "sam's club", "bj's", "lowes", "lowe's", "menards",
    "bed bath", "ulta", "sephora", "dick's", "academy", "rei",
}


def _fetch_rss(url, timeout=15):
    """Fetch and parse an RSS feed. Returns list of item dicts."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            content = resp.read()
    except (URLError, Exception) as e:
        print(f"  [rss] Error fetching {url}: {e}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"  [rss] XML parse error for {url}: {e}", file=sys.stderr)
        return []

    items = []
    # Standard RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        if title:
            items.append({
                "title": title,
                "url": link,
                "description": description,
                "pub_date": pub_date,
            })

    # Atom format fallback
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = (entry.findtext("atom:summary", "", ns) or "").strip()

            if title:
                items.append({
                    "title": title,
                    "url": link,
                    "description": summary,
                    "pub_date": "",
                })

    return items


def _extract_price(text):
    """Extract the first dollar price from text."""
    if not text:
        return None
    m = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _extract_retailer(text):
    """Try to identify the retailer from deal title/description."""
    text_lower = (text or "").lower()
    for retailer in OA_RETAILERS:
        if retailer in text_lower:
            return retailer.title()
    return None


def _clean_deal_title(title):
    """Clean deal title for Keepa search — remove price, promo text, etc."""
    # Remove price references
    cleaned = re.sub(r"\$[\d,.]+", "", title)
    # Remove common deal prefixes
    cleaned = re.sub(r"^(deal|sale|clearance|coupon|promo|hot|wow|new)\s*:?\s*",
                     "", cleaned, flags=re.I)
    # Remove percentage discounts
    cleaned = re.sub(r"\d+%\s*(off|discount|savings?)", "", cleaned, flags=re.I)
    # Remove "free shipping", "BOGO", etc.
    cleaned = re.sub(r"(free shipping|bogo|buy one get one|limited time|today only)",
                     "", cleaned, flags=re.I)
    # Remove trailing/leading junk
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Keep first ~10 meaningful words for search
    words = cleaned.split()[:10]
    return " ".join(words)


def fetch_deals_from_feeds(sources=None, max_per_source=30):
    """Fetch deals from RSS feeds and extract structured data.

    Args:
        sources: list of source keys (e.g. ["slickdeals", "dealnews"]) or None for all
        max_per_source: max deals to extract per source

    Returns: list of deal dicts with title, url, price, retailer, source
    """
    if sources is None:
        sources = list(FEED_SOURCES.keys())

    all_deals = []

    for source_key in sources:
        config = FEED_SOURCES.get(source_key)
        if not config:
            print(f"  [rss] Unknown source: {source_key}", file=sys.stderr)
            continue

        print(f"  [rss] Fetching {config['name']}...", file=sys.stderr)
        items = _fetch_rss(config["url"])
        print(f"  [rss] {config['name']}: {len(items)} items in feed", file=sys.stderr)

        count = 0
        for item in items:
            if count >= max_per_source:
                break

            title = item["title"]
            combined_text = f"{title} {item.get('description', '')}"

            # Extract price from title or description
            price = _extract_price(title) or _extract_price(item.get("description", ""))

            # Identify retailer
            retailer = _extract_retailer(combined_text)

            # Clean title for Amazon search
            search_query = _clean_deal_title(title)
            if len(search_query) < 5:
                continue

            deal = {
                "title": title,
                "search_query": search_query,
                "url": item["url"],
                "price": price,
                "retailer": retailer or config["name"],
                "source": config["name"],
                "pub_date": item.get("pub_date", ""),
            }
            all_deals.append(deal)
            count += 1

    print(f"  [rss] Total: {len(all_deals)} deals extracted from {len(sources)} feeds",
          file=sys.stderr)
    return all_deals


def verify_deals_on_amazon(deals, max_verify=30, min_profit=1.50):
    """Take RSS deals, search each on Keepa, calculate arbitrage potential.

    Args:
        deals: list of deal dicts from fetch_deals_from_feeds()
        max_verify: max deals to verify on Keepa (1 token each)
        min_profit: minimum profit per unit to include

    Returns: list of verified profitable deals
    """
    from keepa_client import KeepaClient
    from calculate_fba_profitability import calculate_product_profitability

    try:
        from auto_ungated_brands import is_auto_ungated
    except ImportError:
        is_auto_ungated = lambda _: False

    keepa = KeepaClient(tier="pro")
    verified = []
    seen_asins = set()
    tokens_used = 0

    # Filter to deals that have a price (needed for arbitrage calc)
    priced_deals = [d for d in deals if d.get("price") and d["price"] > 0.50]
    # Sort by price ascending (cheapest = most likely to have margin)
    priced_deals.sort(key=lambda d: d["price"])

    print(f"\n[deals] Verifying {min(len(priced_deals), max_verify)} priced deals "
          f"on Amazon (1 token each)...", file=sys.stderr)

    for i, deal in enumerate(priced_deals[:max_verify]):
        query = deal["search_query"]
        price = deal["price"]

        print(f"  [{i+1}/{min(len(priced_deals), max_verify)}] "
              f"${price:.2f} | {query[:50]}", file=sys.stderr)

        # Search Keepa (1 token)
        product = keepa.search_product(query)
        tokens_used += 1

        if not product:
            print(f"    → No Amazon match", file=sys.stderr)
            time.sleep(3.0)
            continue

        asin = product.get("asin", "")
        if asin in seen_asins:
            print(f"    → Duplicate ASIN {asin}", file=sys.stderr)
            time.sleep(3.0)
            continue
        if asin:
            seen_asins.add(asin)

        sell_price = product.get("sell_price")
        if not sell_price:
            print(f"    → No Amazon price", file=sys.stderr)
            time.sleep(3.0)
            continue

        # Quick margin check
        est_fees = price * 0.15 + 3.50
        est_profit = sell_price - price - est_fees
        if est_profit < min_profit:
            print(f"    → Low margin: ~${est_profit:.2f}", file=sys.stderr)
            time.sleep(3.0)
            continue

        # Private label check
        pl = product.get("private_label", {})
        if isinstance(pl, dict) and pl.get("is_private_label"):
            print(f"    → Private label", file=sys.stderr)
            time.sleep(3.0)
            continue

        # Amazon on listing check
        if product.get("amazon_on_listing", False):
            print(f"    → Amazon on listing", file=sys.stderr)
            time.sleep(3.0)
            continue

        # FBA seller check
        fba_count = product.get("fba_seller_count")
        if fba_count is not None and fba_count < 2:
            print(f"    → Only {fba_count} FBA seller(s)", file=sys.stderr)
            time.sleep(3.0)
            continue

        # Full profitability calc
        product_data = {
            "name": deal["title"],
            "retail_price": price,
            "retailer": deal.get("retailer", ""),
            "amazon": {
                "asin": asin,
                "title": product.get("title", ""),
                "amazon_price": sell_price,
                "sales_rank": product.get("bsr"),
                "category": product.get("category", ""),
                "fba_seller_count": fba_count or 0,
                "amazon_on_listing": product.get("amazon_on_listing", False),
                "private_label": pl,
                "match_confidence": 0.6,  # RSS deals are approximate matches
                "review_count": product.get("review_count"),
            },
        }

        try:
            prof = calculate_product_profitability(product_data, auto_cashback=True)
        except Exception as e:
            print(f"    → Calc error: {e}", file=sys.stderr)
            time.sleep(3.0)
            continue

        verdict = prof.get("verdict", "SKIP")
        profit = prof.get("profit_per_unit", 0)
        roi = prof.get("roi_percent", 0)

        if verdict == "SKIP":
            print(f"    → SKIP: {prof.get('skip_reason', '')}", file=sys.stderr)
            time.sleep(3.0)
            continue

        brand = product.get("brand", "")
        ungated = is_auto_ungated(brand)
        print(f"    → {verdict}: ${profit:.2f} profit, {roi:.0f}% ROI", file=sys.stderr)

        verified.append({
            "name": deal["title"],
            "asin": asin,
            "retailer": deal.get("retailer", ""),
            "source": deal.get("source", ""),
            "retail_price": price,
            "amazon_price": sell_price,
            "buy_url": deal.get("url", ""),
            "amazon_url": f"https://www.amazon.com/dp/{asin}",
            "bsr": product.get("bsr"),
            "category": product.get("category", ""),
            "brand": brand,
            "auto_ungated": ungated,
            "profitability": prof,
        })

        time.sleep(3.0)

    print(f"\n[deals] Verification complete: {len(verified)} profitable deals "
          f"({tokens_used} tokens used)", file=sys.stderr)
    return verified


def main():
    parser = argparse.ArgumentParser(description="Scan deal RSS feeds for OA opportunities")
    parser.add_argument("--sources", "-s", default="all",
                        help="Comma-separated sources: slickdeals,dealnews,totallytarget,hip2save,all")
    parser.add_argument("--max", "-n", type=int, default=50,
                        help="Max deals to fetch per source (default: 50)")
    parser.add_argument("--verify", type=int, default=30,
                        help="Max deals to verify on Amazon (default: 30, 0=skip)")
    parser.add_argument("--min-profit", type=float, default=1.50,
                        help="Min profit per unit (default: $1.50)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON path (default: .tmp/sourcing/deals_rss.json)")
    args = parser.parse_args()

    sources = None if args.sources == "all" else [s.strip() for s in args.sources.split(",")]

    # Fetch deals
    deals = fetch_deals_from_feeds(sources=sources, max_per_source=args.max)

    if not deals:
        print("No deals found from RSS feeds.", file=sys.stderr)
        return

    # Verify on Amazon if requested
    if args.verify > 0:
        verified = verify_deals_on_amazon(deals, max_verify=args.verify,
                                           min_profit=args.min_profit)
    else:
        verified = deals  # Raw deals without verification

    # Output
    output_path = args.output
    if not output_path:
        out_dir = Path(__file__).parent.parent / ".tmp" / "sourcing"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = out_dir / f"{ts}_deals_rss.json"

    with open(output_path, "w") as f:
        json.dump({
            "deals": verified,
            "count": len(verified),
            "sources": sources or list(FEED_SOURCES.keys()),
            "scanned_at": datetime.now().isoformat(),
        }, f, indent=2, default=str)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Deal RSS Scanner Results", file=sys.stderr)
    print(f"  {len(verified)} actionable deals found", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    for i, d in enumerate(verified, 1):
        prof = d.get("profitability", {})
        profit = prof.get("profit_per_unit", "?")
        roi = prof.get("roi_percent", "?")
        print(f"  #{i} [{d.get('retailer', '?')}] {d.get('name', d.get('title', ''))[:50]}", file=sys.stderr)
        print(f"      ${d.get('retail_price', '?')} → ${d.get('amazon_price', '?')} "
              f"| Profit: ${profit} | ROI: {roi}%", file=sys.stderr)
        print(f"      BUY: {d.get('buy_url', 'N/A')}", file=sys.stderr)
        print(f"      AMZ: {d.get('amazon_url', 'N/A')}", file=sys.stderr)

    print(f"\n  Saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
