#!/usr/bin/env python3
"""
Seller Storefront Scanner

Given an ASIN, finds all sellers on that listing with <N reviews,
scrapes their full Amazon storefronts, and checks each product for
profitability via Keepa.

Usage:
    python execution/seller_storefront_scan.py B084VCLBSG --max-reviews 100
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ── Playwright context (reused) ──────────────────────────────────────────────

_pw_context = None

def _get_pw_context():
    global _pw_context
    if _pw_context is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _pw_context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
    return _pw_context


def get_sellers_from_keepa(asin, max_reviews=100):
    """Get all sellers on a listing via Keepa offers data.

    Returns list of seller dicts with seller_id, seller_name, is_fba, price.
    Costs 21 tokens (1 product + 20 offers).
    """
    from keepa_client import KeepaClient
    keepa = KeepaClient()

    print(f"\n[keepa] Fetching offers for {asin} (21 tokens)...", file=sys.stderr)
    product = keepa.get_product(asin, offers=20, stats=180)

    if not product:
        print(f"  [keepa] No product data for {asin}", file=sys.stderr)
        return [], None

    offers = product.get("offers_data", [])
    print(f"  [keepa] Found {len(offers)} seller(s) on listing", file=sys.stderr)

    for s in offers:
        print(f"    {'[FBA]' if s['is_fba'] else '[FBM]'} "
              f"{'[AMZ]' if s['is_amazon'] else '     '} "
              f"${s['price']:.2f} — {s['seller_name']} ({s['seller_id']})",
              file=sys.stderr)

    return offers, product


def get_seller_review_count(seller_id):
    """Scrape the seller's feedback page to get their review count.

    Returns (review_count, seller_name, storefront_url) or (None, None, None).
    """
    from bs4 import BeautifulSoup

    feedback_url = f"https://www.amazon.com/sp?seller={seller_id}"
    ctx = _get_pw_context()
    page = ctx.new_page()

    try:
        page.goto(feedback_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

        soup = BeautifulSoup(page.content(), "html.parser")
        html_text = soup.get_text(" ", strip=True)

        # Look for rating count patterns
        # "123 ratings" or "1,234 ratings" or "12 ratings in the last 12 months"
        rating_match = re.search(r"([\d,]+)\s+ratings?\b", html_text)
        review_count = 0
        if rating_match:
            review_count = int(rating_match.group(1).replace(",", ""))

        # Get seller display name
        seller_name_el = soup.select_one("#sellerName, #seller-name, h1")
        seller_name = seller_name_el.get_text(strip=True) if seller_name_el else ""

        # Get storefront link
        storefront_link = soup.select_one('a[href*="storefront"]')
        storefront_url = None
        if storefront_link:
            href = storefront_link.get("href", "")
            if href.startswith("/"):
                storefront_url = f"https://www.amazon.com{href}"
            elif href.startswith("http"):
                storefront_url = href

        # Alternative: construct storefront URL from seller ID
        if not storefront_url:
            storefront_url = f"https://www.amazon.com/s?me={seller_id}"

        print(f"  [seller] {seller_name or seller_id}: {review_count} ratings", file=sys.stderr)
        return review_count, seller_name, storefront_url

    except Exception as e:
        print(f"  [seller] Error checking {seller_id}: {e}", file=sys.stderr)
        return None, None, None
    finally:
        page.close()


def scrape_storefront(seller_id, seller_name="", max_pages=5):
    """Scrape all products from an Amazon seller's storefront.

    Returns list of dicts with: asin, title, price, url.
    """
    from bs4 import BeautifulSoup

    ctx = _get_pw_context()
    all_products = []

    for page_num in range(1, max_pages + 1):
        storefront_url = f"https://www.amazon.com/s?me={seller_id}&page={page_num}"
        page = ctx.new_page()

        try:
            print(f"  [storefront] {seller_name or seller_id} — page {page_num}...", file=sys.stderr)
            page.goto(storefront_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(4000)

            # Scroll to load lazy images/content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            soup = BeautifulSoup(page.content(), "html.parser")

            # Amazon search result cards
            results = soup.select('[data-asin]')
            page_products = []

            for result in results:
                asin = result.get("data-asin", "").strip()
                if not asin or len(asin) != 10:
                    continue

                # Product title
                title_el = (result.select_one("h2 a span") or
                           result.select_one("h2 span") or
                           result.select_one(".a-text-normal"))
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                # Product URL
                link_el = result.select_one("h2 a")
                url = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href.startswith("/"):
                        url = f"https://www.amazon.com{href}"
                    elif href.startswith("http"):
                        url = href

                # Price
                price = None
                price_whole = result.select_one(".a-price-whole")
                price_frac = result.select_one(".a-price-fraction")
                if price_whole:
                    try:
                        whole = price_whole.get_text(strip=True).replace(",", "").replace(".", "")
                        frac = price_frac.get_text(strip=True) if price_frac else "00"
                        price = float(f"{whole}.{frac}")
                    except ValueError:
                        pass

                page_products.append({
                    "asin": asin,
                    "title": title,
                    "price": price,
                    "url": url or f"https://www.amazon.com/dp/{asin}",
                })

            all_products.extend(page_products)

            # If we got fewer results than a full page, we're done
            if len(page_products) < 10:
                break

        except Exception as e:
            print(f"  [storefront] Error on page {page_num}: {e}", file=sys.stderr)
            break
        finally:
            page.close()

        time.sleep(2)  # Be nice to Amazon

    # Deduplicate by ASIN
    seen = set()
    unique = []
    for p in all_products:
        if p["asin"] not in seen:
            seen.add(p["asin"])
            unique.append(p)

    print(f"  [storefront] {seller_name}: {len(unique)} unique products found", file=sys.stderr)
    return unique


def check_profitability_batch(products, min_profit=2.0, max_check=50):
    """Check a batch of storefront products for profitability via Keepa.

    Two-pass approach:
      1. Keepa batch check: filter by BSR, PL, Amazon on listing, FBA sellers
      2. Retail search: try to find matching retail source (Target, Walgreens, H Mart)
         - If found → include retail price + buy link
         - If NOT found → still include product with "Check retailers" note
           (product is worth sourcing, just need to find the retail source manually)

    Returns list of products that pass quality filters, with or without retail match.
    """
    from keepa_client import KeepaClient
    keepa = KeepaClient()

    results = []
    tokens_used = 0
    skipped = {"no_price": 0, "bsr": 0, "pl": 0, "amazon": 0, "fba": 0}
    skipped_no_link = 0

    asins = [p["asin"] for p in products[:max_check]]
    # Map ASIN to storefront data (title from listing, price seen)
    storefront_map = {p["asin"]: p for p in products[:max_check]}

    print(f"\n[verify] Checking {len(asins)} storefront products via Keepa...", file=sys.stderr)

    # Batch fetch in groups of 20
    for batch_start in range(0, len(asins), 20):
        batch = asins[batch_start:batch_start + 20]
        print(f"  [keepa] Batch {batch_start//20 + 1}: {len(batch)} ASINs ({len(batch)} tokens)...", file=sys.stderr)

        batch_results = keepa.get_products_batch(batch, stats=180)
        tokens_used += len(batch)

        for parsed in batch_results:
            asin = parsed.get("asin", "")
            title = parsed.get("title", "")
            sell_price = parsed.get("sell_price")
            bsr = parsed.get("bsr")
            brand = parsed.get("brand", "")
            fba_count = parsed.get("fba_seller_count")
            category = parsed.get("category", "")

            if not sell_price or sell_price < 5:
                skipped["no_price"] += 1
                continue

            if bsr and bsr > 500000:
                skipped["bsr"] += 1
                print(f"    [SKIP] {title[:40]} — BSR {(bsr or 0):,} too high", file=sys.stderr)
                continue

            pl = parsed.get("private_label", {})
            if isinstance(pl, dict) and pl.get("is_private_label"):
                skipped["pl"] += 1
                print(f"    [SKIP] {title[:40]} — Private label", file=sys.stderr)
                continue

            if parsed.get("amazon_on_listing"):
                amz_price = parsed.get("amazon_price")
                bb_price = parsed.get("buy_box_price") or sell_price
                if not (amz_price and bb_price and amz_price > bb_price * 1.15):
                    skipped["amazon"] += 1
                    print(f"    [SKIP] {title[:40]} — Amazon on listing", file=sys.stderr)
                    continue

            if fba_count is not None and fba_count < 2:
                skipped["fba"] += 1
                print(f"    [SKIP] {title[:40]} — Only {fba_count} FBA seller(s)", file=sys.stderr)
                continue

            # Product passed all quality filters!
            print(f"    [PASS] {title[:50]} — ${sell_price:.2f} | BSR {(bsr or 0):,} | {fba_count or '?'} FBA",
                  file=sys.stderr)

            # Try to find retail source
            retail_hits = _search_retailers_for_product(title, sell_price, min_profit)

            storefront_info = storefront_map.get(asin, {})

            if retail_hits:
                # Found retail source — calculate profit
                hit = retail_hits[0]  # Best match
                estimated_fees = hit["retail_price"] * 0.15 + 4.0
                profit = sell_price - hit["retail_price"] - estimated_fees
                roi = (profit / hit["retail_price"] * 100) if hit["retail_price"] > 0 else 0

                results.append({
                    "asin": asin,
                    "title": title,
                    "brand": brand,
                    "amazon_price": sell_price,
                    "retail_price": hit["retail_price"],
                    "retailer": hit["retailer"],
                    "retail_title": hit.get("retail_title", ""),
                    "buy_url": hit["buy_url"],
                    "amazon_url": f"https://www.amazon.com/dp/{asin}",
                    "est_profit": round(profit, 2),
                    "est_roi": round(roi, 1),
                    "bsr": bsr,
                    "fba_sellers": fba_count,
                    "category": category,
                    "source_seller": storefront_info.get("source_seller", ""),
                    "has_retail_match": True,
                })
                print(f"      ✓ Retail match: {hit['retailer']} — ${hit['retail_price']:.2f} "
                      f"(${profit:.2f} profit, {roi:.0f}% ROI)", file=sys.stderr)
            else:
                # No retail source found — SKIP entirely.
                # Standing directive: no buy link = no output. Period.
                skipped_no_link += 1
                print(f"      ✗ No retail buy link found — EXCLUDED from output", file=sys.stderr)

        time.sleep(3)  # Keepa rate limit

    print(f"\n[verify] Done. {len(results)} products with verified retail buy links ({tokens_used} tokens used).",
          file=sys.stderr)
    print(f"  Skipped: {skipped} | No retail link: {skipped_no_link}", file=sys.stderr)
    return results, tokens_used


def _search_retailers_for_product(title, amazon_price, min_profit=2.0):
    """Search Target, Walgreens, and H Mart for a product.

    Uses Playwright to render each retailer's search page, then extracts
    ALL links with their text to find matching products. Matches by keyword
    overlap between the Amazon title and each result's link text.

    Returns list of {retailer, retail_price, buy_url, retail_title}.
    """
    from bs4 import BeautifulSoup

    max_retail = amazon_price - min_profit - (amazon_price * 0.15 + 4.0)
    if max_retail < 1:
        return []

    hits = []
    short_title = _shorten_title(title)
    title_keywords = _extract_keywords(title)

    ctx = _get_pw_context()

    retailers = [
        {
            "name": "Target",
            "url": f"https://www.target.com/s?searchTerm={quote_plus(short_title)}",
            "base": "https://www.target.com",
            "link_pattern": r"/p/",  # Target product pages have /p/ in URL
        },
        {
            "name": "Walgreens",
            "url": f"https://www.walgreens.com/search/results.jsp?Ntt={quote_plus(short_title)}",
            "base": "https://www.walgreens.com",
            "link_pattern": r"/store/|/product/",
        },
        {
            "name": "H Mart",
            "url": f"https://www.hmart.com/search?q={quote_plus(short_title)}",
            "base": "https://www.hmart.com",
            "link_pattern": r"/p$|/p/",
        },
    ]

    for retailer in retailers:
        page = ctx.new_page()
        try:
            page.goto(retailer["url"], wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(4000)
            soup = BeautifulSoup(page.content(), "html.parser")

            # Universal approach: find ALL links on the page that look like
            # product links (matching the retailer's URL pattern)
            all_links = soup.find_all("a", href=True)
            product_links = []
            for link in all_links:
                href = link.get("href", "")
                if re.search(retailer["link_pattern"], href):
                    link_text = link.get_text(" ", strip=True)
                    if link_text and len(link_text) > 5:
                        product_links.append((link_text, href))

            # Try to match each product link against the Amazon title
            best_match = None
            best_score = 0
            for link_text, href in product_links[:15]:  # Check top 15
                retail_keywords = _extract_keywords(link_text)
                if not retail_keywords:
                    continue

                overlap = title_keywords & retail_keywords
                smaller = min(len(title_keywords), len(retail_keywords))
                if smaller == 0:
                    continue
                score = len(overlap) / smaller

                if score > best_score and score >= 0.30:
                    # Extract price from the link text or nearby
                    price = _extract_price_from_text(link_text)
                    if not price:
                        # Try to get price from parent element
                        parent = link.parent
                        if parent:
                            price = _extract_price_from_text(parent.get_text(" ", strip=True))
                    if not price:
                        # Try grandparent
                        grandparent = link.parent.parent if link.parent else None
                        if grandparent:
                            price = _extract_price_from_text(grandparent.get_text(" ", strip=True))

                    if price and price >= 1.0 and price <= max_retail:
                        # Build full URL
                        if href.startswith("/"):
                            buy_url = f"{retailer['base']}{href}"
                        elif href.startswith("http"):
                            buy_url = href
                        else:
                            buy_url = f"{retailer['base']}/{href}"

                        best_match = {
                            "retailer": retailer["name"],
                            "retail_price": price,
                            "buy_url": buy_url,
                            "retail_title": link_text[:100],
                        }
                        best_score = score

            if best_match:
                hits.append(best_match)
                print(f"    [{retailer['name'].lower()}] ✓ Matched: {best_match['retail_title'][:50]} "
                      f"— ${best_match['retail_price']:.2f} (score: {best_score:.0%})",
                      file=sys.stderr)

        except Exception as e:
            print(f"    [{retailer['name'].lower()}] Error: {e}", file=sys.stderr)
        finally:
            page.close()

        time.sleep(1.5)

    return hits


def _shorten_title(title):
    """Shorten a product title for retail search."""
    # Remove pack count suffixes
    title = re.sub(r"\b\d+\s*(pack|count|ct|pk|ea)\b.*$", "", title, flags=re.I)
    # Remove parenthetical details
    title = re.sub(r"\(.*?\)", "", title)
    # Remove size/weight info that clutters search
    title = re.sub(r"\b\d+(\.\d+)?\s*(oz|fl\.?\s*oz|lb|g|kg|ml|l)\b", "", title, flags=re.I)
    # Keep first 8 words
    words = title.split()[:8]
    return " ".join(words).strip()


def _extract_keywords(title):
    """Extract meaningful keywords from a product title for matching."""
    # Lowercase, strip punctuation
    title_clean = re.sub(r"[^\w\s]", " ", title.lower())
    # Remove common filler words
    stop_words = {"the", "a", "an", "and", "or", "for", "with", "in", "of", "to",
                  "by", "from", "pack", "count", "ct", "pk", "ea", "set", "oz",
                  "fl", "lb", "g", "kg", "ml", "l", "inch", "in", "mm", "cm"}
    words = [w for w in title_clean.split() if w and w not in stop_words and len(w) > 1]
    return set(words)


def _titles_match(amazon_keywords, retail_title, min_overlap=0.35):
    """Check if a retail product title matches the Amazon product.

    Requires at least 35% keyword overlap between the two titles.
    This prevents matching "Arm & Hammer Baking Soda" when searching
    for "SpectraFix Degas Spray Fixative".
    """
    if not amazon_keywords or not retail_title:
        return False

    retail_clean = re.sub(r"[^\w\s]", " ", retail_title.lower())
    retail_words = {w for w in retail_clean.split() if len(w) > 1}

    if not retail_words:
        return False

    overlap = amazon_keywords & retail_words
    # Check overlap as fraction of the smaller set (more forgiving)
    smaller = min(len(amazon_keywords), len(retail_words))
    if smaller == 0:
        return False

    score = len(overlap) / smaller
    return score >= min_overlap


def _extract_price_from_text(text):
    """Extract the first product price from card text."""
    prices = re.findall(r"\$(\d+\.\d{2})", text)
    for p in prices:
        val = float(p)
        if 0.50 <= val <= 500:
            return val
    return None


def _export_markdown(profitable, sellers, asin, tokens_used):
    """Export results as a clean markdown file with summary table + details."""
    lines = []
    date_str = datetime.now().strftime("%B %d, %Y")
    lines.append(f"# Seller Storefront Scan — {date_str}")
    lines.append("")
    lines.append(f"> Source ASIN: [{asin}](https://www.amazon.com/dp/{asin})")
    lines.append(f"> Sellers scanned: {len(sellers)} (all with <100 reviews)")
    lines.append(f"> Profitable products found: {len(profitable)}")
    lines.append(f"> Keepa tokens used: ~{tokens_used}")
    lines.append("")
    lines.append("**IMPORTANT:** Verify pack sizes and prices with Amazon Seller App before buying. Retail prices may vary by location.")
    lines.append("")

    if not profitable:
        lines.append("No profitable products found.")
        return "\n".join(lines)

    # Summary table — ALL products have verified buy links
    lines.append("---")
    lines.append("")
    lines.append("## Sourced Products")
    lines.append("")
    lines.append("| # | Product | ASIN | Retail | Amazon | Profit | ROI | Buy Link |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, p in enumerate(profitable, 1):
        short = p['title'][:45] + ("..." if len(p['title']) > 45 else "")
        buy_link = f"[{p['retailer']}]({p['buy_url']})"
        amz_link = f"[{p['asin']}](https://www.amazon.com/dp/{p['asin']})"
        lines.append(
            f"| {i} | {short} | {amz_link} | ${p.get('retail_price', 0):.2f} | "
            f"${p['amazon_price']:.2f} | ${p.get('est_profit', 0):.2f} | {p.get('est_roi', 0)}% | {buy_link} |"
        )
    lines.append("")

    # Detailed cards
    lines.append("---")
    lines.append("")
    lines.append("## Product Details")

    for i, p in enumerate(profitable, 1):
        lines.append("")
        lines.append(f"### {i}. {p['title']}")
        lines.append("")
        lines.append(f"- **ASIN:** [{p['asin']}](https://www.amazon.com/dp/{p['asin']})")
        lines.append(f"- **Brand:** {p.get('brand', 'Unknown')}")
        lines.append(f"- **BUY AT:** [{p['retailer']}]({p['buy_url']}) — **${p.get('retail_price', 0):.2f}**")
        if p.get('retail_title'):
            lines.append(f"- **Retail listing:** {p['retail_title']}")
        lines.append(f"- **Amazon price:** ${p['amazon_price']:.2f}")
        lines.append(f"- **Est. profit:** ${p.get('est_profit', 0):.2f}/unit")
        lines.append(f"- **Est. ROI:** {p.get('est_roi', 0)}%")
        if p.get('bsr'):
            lines.append(f"- **BSR:** {(p.get('bsr') or 0):,}")
        if p.get('fba_sellers'):
            lines.append(f"- **FBA sellers:** {p['fba_sellers']}")
        if p.get('source_seller'):
            lines.append(f"- **Found on:** {p['source_seller']}'s storefront")
        lines.append(f"- **Amazon:** https://www.amazon.com/dp/{p['asin']}")

    # Sellers scanned
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Sellers Scanned")
    lines.append("")
    lines.append("| Seller | Reviews | Storefront |")
    lines.append("|---|---|---|")
    seen_sellers = set()
    for s in sellers:
        name = s.get("display_name", s.get("seller_id", ""))
        if name in seen_sellers:
            continue
        seen_sellers.add(name)
        sid = s.get("seller_id", "")
        lines.append(f"| {name} | {s.get('review_count', '?')} | [View](https://www.amazon.com/s?me={sid}) |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Source: Keepa API + Playwright*")

    return "\n".join(lines)


def format_results(profitable, sellers_checked, asin):
    """Format results for display."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  SELLER STOREFRONT SCAN — ASIN: {asin}")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  Sellers checked: {sellers_checked}")
    lines.append(f"  Profitable products found: {len(profitable)}")
    lines.append("=" * 70)

    if not profitable:
        lines.append("\n  No profitable products found across checked storefronts.")
        lines.append("=" * 70)
        return "\n".join(lines)

    for i, p in enumerate(profitable, 1):
        lines.append("")
        lines.append("─" * 60)
        lines.append(f"  #{i}  {p['title'][:65]}")
        lines.append(f"  ASIN: {p['asin']}")
        lines.append(f"  Brand: {p.get('brand', 'Unknown')}")
        lines.append(f"  BUY AT: {p['retailer']} — ${p.get('retail_price', 0):.2f}")
        lines.append(f"  BUY LINK: {p['buy_url']}")
        if p.get('retail_title'):
            lines.append(f"  Retail product: {p['retail_title'][:70]}")
        lines.append(f"  Amazon price: ${p['amazon_price']:.2f}")
        lines.append(f"  Est. profit: ${p.get('est_profit', 0):.2f}/unit | ROI: {p.get('est_roi', 0)}%")
        if p.get('bsr'):
            lines.append(f"  BSR: {(p.get('bsr') or 0):,}")
        if p.get('fba_sellers'):
            lines.append(f"  FBA sellers: {p['fba_sellers']}")
        if p.get('source_seller'):
            lines.append(f"  Found on: {p['source_seller']}'s storefront")
        lines.append(f"  AMZ: {p['amazon_url']}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("  Verify all products in Amazon Seller App before purchasing.")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scan seller storefronts for profitable products")
    parser.add_argument("asin", help="ASIN to pull sellers from")
    parser.add_argument("--max-reviews", type=int, default=100,
                       help="Max seller review count to include (default: 100)")
    parser.add_argument("--max-products", type=int, default=50,
                       help="Max products per storefront to check (default: 50)")
    parser.add_argument("--min-profit", type=float, default=2.0,
                       help="Min profit per unit (default: $2.00)")
    parser.add_argument("--max-pages", type=int, default=5,
                       help="Max storefront pages to scrape (default: 5)")
    parser.add_argument("--output-asins", type=str, default="",
                       help="Discovery mode: output ASINs to this file (skip Keepa verify). "
                            "Pipe into source.py batch for retail matching.")

    args = parser.parse_args()

    # Step 1: Get sellers from Keepa
    sellers, product = get_sellers_from_keepa(args.asin)
    if not sellers:
        print("No sellers found on listing.", file=sys.stderr)
        return

    # Filter out Amazon itself
    third_party = [s for s in sellers if not s.get("is_amazon")]
    print(f"\n[scan] {len(third_party)} third-party sellers (excluding Amazon)", file=sys.stderr)

    # Step 2: Check review counts and filter
    qualified_sellers = []
    for s in third_party:
        seller_id = s.get("seller_id", "")
        if not seller_id:
            continue

        review_count, display_name, storefront_url = get_seller_review_count(seller_id)

        if review_count is None:
            print(f"  [skip] Could not check reviews for {seller_id}", file=sys.stderr)
            continue

        if review_count <= args.max_reviews:
            qualified_sellers.append({
                **s,
                "review_count": review_count,
                "display_name": display_name or s.get("seller_name", ""),
                "storefront_url": storefront_url,
            })
            print(f"  ✓ {display_name or seller_id}: {review_count} reviews — QUALIFIED", file=sys.stderr)
        else:
            print(f"  ✗ {display_name or seller_id}: {review_count} reviews — too many", file=sys.stderr)

        time.sleep(2)

    if not qualified_sellers:
        print(f"\nNo sellers with <{args.max_reviews} reviews found.", file=sys.stderr)
        return

    print(f"\n[scan] {len(qualified_sellers)} sellers qualify (<{args.max_reviews} reviews)", file=sys.stderr)

    # Step 3: Scrape each seller's storefront
    all_storefront_products = []
    for seller in qualified_sellers:
        print(f"\n[storefront] Scanning: {seller['display_name']} ({seller['review_count']} reviews)...",
              file=sys.stderr)
        products = scrape_storefront(
            seller["seller_id"],
            seller["display_name"],
            max_pages=args.max_pages,
        )
        for p in products:
            p["source_seller"] = seller["display_name"]
            p["source_seller_id"] = seller["seller_id"]
        all_storefront_products.extend(products)
        time.sleep(2)

    # Deduplicate across sellers
    seen_asins = set()
    unique_products = []
    for p in all_storefront_products:
        if p["asin"] not in seen_asins:
            seen_asins.add(p["asin"])
            unique_products.append(p)

    print(f"\n[scan] {len(unique_products)} unique products across all storefronts", file=sys.stderr)

    if not unique_products:
        print("No products found in storefronts.", file=sys.stderr)
        return

    # Discovery mode: output ASINs only (skip expensive Keepa verify)
    if args.output_asins:
        asin_list = [p["asin"] for p in unique_products if p.get("asin")]
        outpath = Path(args.output_asins)
        outpath.parent.mkdir(parents=True, exist_ok=True)
        with open(outpath, "w") as f:
            for a in asin_list:
                f.write(f"{a}\n")
        print(f"\n[discovery] {len(asin_list)} ASINs written to {outpath}", file=sys.stderr)
        print(f"  Next step: python execution/source.py batch --input {outpath} --retailers target,walgreens,hmart",
              file=sys.stderr)
        return

    # Step 4: Check profitability
    profitable, tokens = check_profitability_batch(
        unique_products,
        min_profit=args.min_profit,
        max_check=args.max_products,
    )

    # Output
    output = format_results(profitable, len(qualified_sellers), args.asin)
    print(output)

    # Save to files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = TMP_DIR / f"{timestamp}_storefront_scan.json"
    txt_path = TMP_DIR / f"{timestamp}_storefront_scan.txt"
    md_path = TMP_DIR / f"{timestamp}_storefront_leads.md"

    with open(json_path, "w") as f:
        json.dump({
            "asin": args.asin,
            "sellers_checked": [
                {"name": s["display_name"], "id": s["seller_id"], "reviews": s["review_count"]}
                for s in qualified_sellers
            ],
            "profitable_products": profitable,
            "tokens_used": tokens + 21,  # +21 for initial offers call
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)

    with open(txt_path, "w") as f:
        f.write(output)

    # Export markdown with table + detail sections
    md = _export_markdown(profitable, qualified_sellers, args.asin, tokens + 21)
    with open(md_path, "w") as f:
        f.write(md)

    print(f"\nSaved: {json_path}", file=sys.stderr)
    print(f"Saved: {txt_path}", file=sys.stderr)
    print(f"Saved: {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
