#!/usr/bin/env python3
"""
Script: coupon_scraper.py
Purpose: Coupon discovery and stacking layer for the Amazon FBA sourcing pipeline.
         Scrapes RetailMeNot for active coupon codes, stores in SQLite, and provides
         a lookup function for the profitability calculator.

         This is the THIRD financial layer in the stacking order:
           1. Gift card discount  (scrape_cardbear.py)
           2. Cashback            (Rakuten rates)
           3. Coupon              (this script)
           Math: final = (raw * (1-giftcard) * (1-cashback)) - coupon_amount

Inputs:  CLI subcommands: scrape, lookup, list, stats, mark
Outputs: SQLite records, stdout JSON, best-coupon lookups

CLI:
    python execution/coupon_scraper.py scrape
    python execution/coupon_scraper.py scrape --retailer walmart
    python execution/coupon_scraper.py lookup --retailer walmart --amount 50
    python execution/coupon_scraper.py list --retailer walmart
    python execution/coupon_scraper.py stats
    python execution/coupon_scraper.py mark --id 123 --worked
    python execution/coupon_scraper.py mark --id 123 --failed
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "price_tracker.db"

REQUEST_DELAY = 3  # seconds between requests
MAX_RETRIES = 3
BACKOFF_FACTOR = 2

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

RETAILER_SLUGS = {
    "walmart": "walmart.com",
    "target": "target.com",
    "home depot": "homedepot.com",
    "cvs": "cvs.com",
    "walgreens": "walgreens.com",
    "costco": "costco.com",
}

RETAILMENOT_BASE = "https://www.retailmenot.com/view"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("coupon_scraper")

# ─── SQLite Schema ────────────────────────────────────────────────────────────

COUPON_SCHEMA = """
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer TEXT NOT NULL,
    code TEXT,
    description TEXT,
    discount_type TEXT CHECK(discount_type IN ('percent', 'fixed', 'bogo', 'free_shipping')),
    discount_value REAL DEFAULT 0,
    min_purchase REAL DEFAULT 0,
    expiry_date TEXT,
    verified INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0,
    source TEXT,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coupon_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER NOT NULL,
    used_at TEXT NOT NULL,
    worked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
);

CREATE INDEX IF NOT EXISTS idx_coupons_retailer ON coupons(retailer);
CREATE INDEX IF NOT EXISTS idx_coupons_expiry ON coupons(expiry_date);
CREATE INDEX IF NOT EXISTS idx_coupon_usage_coupon_id ON coupon_usage(coupon_id);
"""


def init_db():
    """Initialize SQLite database and create tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(COUPON_SCHEMA)
    conn.commit()
    return conn


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def _fetch_page(url):
    """Fetch a page with retries and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (403, 429):
                wait = REQUEST_DELAY * (BACKOFF_FACTOR ** attempt)
                log.warning(
                    "HTTP %d from %s — backing off %.1fs (attempt %d/%d)",
                    resp.status_code, url, wait, attempt + 1, MAX_RETRIES,
                )
                time.sleep(wait)
            else:
                log.error("HTTP %d from %s", resp.status_code, url)
                return None
        except requests.RequestException as e:
            wait = REQUEST_DELAY * (BACKOFF_FACTOR ** attempt)
            log.warning("Request error: %s — retrying in %.1fs", e, wait)
            time.sleep(wait)
    log.error("Failed to fetch %s after %d retries", url, MAX_RETRIES)
    return None


# ─── Discount Parsing ─────────────────────────────────────────────────────────

def _parse_discount(description):
    """
    Extract discount type and value from coupon description text.

    Returns:
        (discount_type, discount_value, min_purchase) tuple

    Examples:
        "20% off"            -> ("percent", 20.0, 0)
        "$10 off $50+"       -> ("fixed", 10.0, 50.0)
        "$5 off orders $25+" -> ("fixed", 5.0, 25.0)
        "Free shipping"      -> ("free_shipping", 0.0, 0)
        "Buy 1, Get 1 Free"  -> ("bogo", 0.0, 0)
        "BOGO 50% off"       -> ("bogo", 50.0, 0)
    """
    if not description:
        return ("percent", 0.0, 0.0)

    text = description.lower().strip()

    # Free shipping
    if "free shipping" in text or "free delivery" in text:
        return ("free_shipping", 0.0, 0.0)

    # BOGO variants
    if "buy" in text and "get" in text:
        pct = re.search(r'(\d+)%', text)
        val = float(pct.group(1)) if pct else 0.0
        return ("bogo", val, 0.0)
    if "bogo" in text:
        pct = re.search(r'(\d+)%', text)
        val = float(pct.group(1)) if pct else 0.0
        return ("bogo", val, 0.0)

    # Percentage off
    pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*off', text)
    if pct_match:
        min_purchase = 0.0
        min_match = re.search(r'\$(\d+(?:\.\d+)?)\+?', text)
        if min_match:
            # If the dollar amount comes after "off" or with "order/purchase"
            after_pct = text[pct_match.end():]
            min_in_rest = re.search(r'\$(\d+(?:\.\d+)?)', after_pct)
            if min_in_rest:
                min_purchase = float(min_in_rest.group(1))
        return ("percent", float(pct_match.group(1)), min_purchase)

    # Fixed dollar off
    fixed_match = re.search(r'\$(\d+(?:\.\d+)?)\s*off', text)
    if fixed_match:
        discount_val = float(fixed_match.group(1))
        min_purchase = 0.0
        # Look for min purchase like "$50+" or "orders $25+"
        rest = text[fixed_match.end():]
        min_match = re.search(r'\$(\d+(?:\.\d+)?)\+?', rest)
        if min_match:
            min_purchase = float(min_match.group(1))
        return ("fixed", discount_val, min_purchase)

    # Bare percentage (e.g., "20% savings")
    bare_pct = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if bare_pct:
        return ("percent", float(bare_pct.group(1)), 0.0)

    # Bare dollar amount
    bare_dollar = re.search(r'\$(\d+(?:\.\d+)?)', text)
    if bare_dollar:
        return ("fixed", float(bare_dollar.group(1)), 0.0)

    return ("percent", 0.0, 0.0)


# ─── Scraping ─────────────────────────────────────────────────────────────────

def scrape_retailmenot(retailer_slug, conn=None):
    """
    Scrape RetailMeNot for coupon codes for a single retailer.

    Args:
        retailer_slug: Key from RETAILER_SLUGS (e.g. "walmart")
        conn: Optional SQLite connection (creates one if not provided)

    Returns:
        list of coupon dicts inserted into the database
    """
    if retailer_slug not in RETAILER_SLUGS:
        log.error("Unknown retailer: %s. Supported: %s", retailer_slug, list(RETAILER_SLUGS.keys()))
        return []

    domain = RETAILER_SLUGS[retailer_slug]
    url = f"{RETAILMENOT_BASE}/{domain}"
    log.info("Scraping coupons for %s from %s", retailer_slug, url)

    html = _fetch_page(url)
    if not html:
        return []

    own_conn = conn is None
    if own_conn:
        conn = init_db()

    soup = BeautifulSoup(html, "html.parser")
    coupons = []
    now = datetime.utcnow().isoformat()

    # RetailMeNot uses various container patterns for offers
    offer_cards = soup.select(
        'div[data-offer], '
        'div.offer, '
        'div[class*="coupon"], '
        'div[class*="Offer"], '
        'section[class*="offer"], '
        'a[data-offer-id]'
    )

    # Fallback: look for any elements containing coupon codes
    if not offer_cards:
        offer_cards = soup.find_all("div", class_=re.compile(r"(offer|coupon|deal|promo)", re.I))

    log.info("Found %d potential offer elements for %s", len(offer_cards), retailer_slug)

    for card in offer_cards:
        try:
            coupon = _parse_offer_card(card, retailer_slug, url, now)
            if coupon and coupon.get("description"):
                coupons.append(coupon)
        except Exception as e:
            log.debug("Error parsing offer card: %s", e)
            continue

    # Deduplicate by (retailer, code, description) before inserting
    seen = set()
    unique_coupons = []
    for c in coupons:
        key = (c["retailer"], c.get("code", ""), c["description"][:80])
        if key not in seen:
            seen.add(key)
            unique_coupons.append(c)

    # Insert into database
    inserted = []
    for c in unique_coupons:
        try:
            cursor = conn.execute(
                """INSERT INTO coupons
                   (retailer, code, description, discount_type, discount_value,
                    min_purchase, expiry_date, verified, success_rate, source, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c["retailer"], c.get("code"), c["description"],
                    c["discount_type"], c["discount_value"], c["min_purchase"],
                    c.get("expiry_date"), c.get("verified", 0), 0.0,
                    c["source"], c["scraped_at"],
                ),
            )
            c["id"] = cursor.lastrowid
            inserted.append(c)
        except sqlite3.IntegrityError:
            log.debug("Duplicate coupon skipped: %s", c.get("code", c["description"][:40]))

    conn.commit()
    log.info("Inserted %d coupons for %s", len(inserted), retailer_slug)

    if own_conn:
        conn.close()

    return inserted


def _parse_offer_card(card, retailer_slug, source_url, scraped_at):
    """Parse a single offer card element into a coupon dict."""
    # Extract coupon code
    code = None
    code_el = card.select_one(
        'span[class*="code"], '
        'span[class*="Code"], '
        'div[class*="code"], '
        'button[class*="code"], '
        '[data-code], '
        'input[value]'
    )
    if code_el:
        code = code_el.get("data-code") or code_el.get("value") or code_el.get_text(strip=True)
        if code and len(code) > 30:
            code = None  # Probably not a real code

    # Extract description
    desc_el = card.select_one(
        'h3, h4, '
        'span[class*="title"], '
        'span[class*="Title"], '
        'div[class*="title"], '
        'p[class*="description"], '
        'span[class*="offer"], '
        'a[class*="offer"]'
    )
    description = ""
    if desc_el:
        description = desc_el.get_text(strip=True)
    if not description:
        description = card.get_text(strip=True)[:200]

    if not description or len(description) < 3:
        return None

    # Parse discount from description
    discount_type, discount_value, min_purchase = _parse_discount(description)

    # Extract expiry date
    expiry_date = None
    expiry_el = card.select_one(
        'span[class*="expire"], '
        'span[class*="Expire"], '
        'div[class*="expire"], '
        'time, '
        'span[class*="date"]'
    )
    if expiry_el:
        expiry_text = expiry_el.get("datetime") or expiry_el.get_text(strip=True)
        expiry_date = _parse_expiry(expiry_text)

    # Check if verified
    verified = 0
    if card.select_one('[class*="verified"], [class*="Verified"], [data-verified]'):
        verified = 1
    verified_text = card.get_text(strip=True).lower()
    if "verified" in verified_text or "staff pick" in verified_text:
        verified = 1

    return {
        "retailer": retailer_slug,
        "code": code,
        "description": description,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "min_purchase": min_purchase,
        "expiry_date": expiry_date,
        "verified": verified,
        "source": source_url,
        "scraped_at": scraped_at,
    }


def _parse_expiry(text):
    """Try to parse an expiry date string into ISO format."""
    if not text:
        return None

    # Try ISO format first
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Look for date-like patterns in the text
    date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if date_match:
        m, d, y = date_match.groups()
        if len(y) == 2:
            y = "20" + y
        try:
            return datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def scrape_all_supported():
    """
    Scrape coupons for all supported retailers.

    Returns:
        dict mapping retailer -> list of coupon dicts
    """
    conn = init_db()
    results = {}

    for i, retailer in enumerate(RETAILER_SLUGS):
        if i > 0:
            log.info("Waiting %ds before next retailer...", REQUEST_DELAY)
            time.sleep(REQUEST_DELAY)

        coupons = scrape_retailmenot(retailer, conn=conn)
        results[retailer] = coupons

    conn.close()
    log.info(
        "Scrape complete: %d total coupons across %d retailers",
        sum(len(v) for v in results.values()),
        len(results),
    )
    return results


# ─── Lookup Functions ─────────────────────────────────────────────────────────

def get_best_coupon(retailer_name, purchase_amount=None):
    """
    Return the best available coupon for a retailer and optional purchase amount.

    This is the integration point for the profitability calculator.
    Selects the coupon that yields the highest effective discount.

    Args:
        retailer_name: Retailer name (e.g. "walmart", "Home Depot")
        purchase_amount: Optional purchase total to filter by min_purchase

    Returns:
        dict with coupon details, or None if no coupons found
    """
    retailer_key = retailer_name.lower().strip()

    conn = init_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    query = """
        SELECT * FROM coupons
        WHERE LOWER(retailer) = ?
          AND (expiry_date IS NULL OR expiry_date >= ?)
    """
    params = [retailer_key, today]

    if purchase_amount is not None:
        query += " AND (min_purchase = 0 OR min_purchase <= ?)"
        params.append(purchase_amount)

    query += " ORDER BY verified DESC, success_rate DESC, discount_value DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return None

    # Score each coupon by effective discount amount
    best = None
    best_score = -1

    for row in rows:
        row_dict = dict(row)
        score = _calculate_coupon_score(row_dict, purchase_amount)
        if score > best_score:
            best_score = score
            best = row_dict

    if best:
        best["effective_discount"] = best_score

    return best


def _calculate_coupon_score(coupon, purchase_amount=None):
    """
    Calculate an effective discount score for ranking coupons.

    For a $50 purchase:
      - "20% off"   -> score = 10.0
      - "$10 off"   -> score = 10.0
      - "free ship"  -> score = 5.0 (estimated shipping value)
      - "BOGO"       -> score = 0.5 (context-dependent, low default)
    """
    dtype = coupon.get("discount_type", "percent")
    value = coupon.get("discount_value", 0)
    amount = purchase_amount or 50.0  # Default assumption

    if dtype == "percent":
        return (value / 100.0) * amount
    elif dtype == "fixed":
        return value
    elif dtype == "free_shipping":
        return 5.0  # Conservative estimated shipping value
    elif dtype == "bogo":
        if value > 0:
            return (value / 100.0) * (amount / 2)  # BOGO X% off second item
        return amount / 2  # BOGO free = half price
    return 0.0


def get_all_coupons(retailer_name, active_only=True):
    """
    Get all coupons for a retailer.

    Args:
        retailer_name: Retailer name (e.g. "walmart")
        active_only: If True, exclude expired coupons

    Returns:
        list of coupon dicts
    """
    retailer_key = retailer_name.lower().strip()
    conn = init_db()

    query = "SELECT * FROM coupons WHERE LOWER(retailer) = ?"
    params = [retailer_key]

    if active_only:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        query += " AND (expiry_date IS NULL OR expiry_date >= ?)"
        params.append(today)

    query += " ORDER BY verified DESC, discount_value DESC, scraped_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def mark_coupon_used(coupon_id, worked: bool):
    """
    Record whether a coupon worked when used.

    Updates the coupon's success_rate based on all usage records.

    Args:
        coupon_id: The coupon ID from the database
        worked: True if the coupon was accepted, False otherwise
    """
    conn = init_db()
    now = datetime.utcnow().isoformat()

    conn.execute(
        "INSERT INTO coupon_usage (coupon_id, used_at, worked) VALUES (?, ?, ?)",
        (coupon_id, now, int(worked)),
    )

    # Recalculate success rate
    stats = conn.execute(
        """SELECT COUNT(*) as total, SUM(worked) as successes
           FROM coupon_usage WHERE coupon_id = ?""",
        (coupon_id,),
    ).fetchone()

    if stats and stats["total"] > 0:
        rate = (stats["successes"] / stats["total"]) * 100.0
        conn.execute(
            "UPDATE coupons SET success_rate = ? WHERE id = ?",
            (rate, coupon_id),
        )

    conn.commit()
    conn.close()

    status = "WORKED" if worked else "FAILED"
    log.info("Coupon #%d marked as %s", coupon_id, status)


# ─── Stats ────────────────────────────────────────────────────────────────────

def get_stats():
    """Get coupon counts and success rates per retailer."""
    conn = init_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    rows = conn.execute(
        """SELECT
            retailer,
            COUNT(*) as total,
            SUM(CASE WHEN (expiry_date IS NULL OR expiry_date >= ?) THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN code IS NOT NULL THEN 1 ELSE 0 END) as with_code,
            AVG(CASE WHEN success_rate > 0 THEN success_rate ELSE NULL END) as avg_success_rate,
            MAX(scraped_at) as last_scraped
           FROM coupons
           GROUP BY retailer
           ORDER BY retailer""",
        (today,),
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli_scrape(args):
    """Handle the 'scrape' subcommand."""
    if args.retailer:
        retailer = args.retailer.lower().strip()
        if retailer not in RETAILER_SLUGS:
            log.error("Unknown retailer: %s. Supported: %s", retailer, list(RETAILER_SLUGS.keys()))
            sys.exit(1)
        coupons = scrape_retailmenot(retailer)
        print(json.dumps(coupons, indent=2, default=str))
    else:
        results = scrape_all_supported()
        summary = {k: len(v) for k, v in results.items()}
        print(json.dumps({"summary": summary, "total": sum(summary.values())}, indent=2))


def _cli_lookup(args):
    """Handle the 'lookup' subcommand."""
    retailer = args.retailer.lower().strip()
    amount = args.amount

    coupon = get_best_coupon(retailer, purchase_amount=amount)
    if coupon:
        print(json.dumps(coupon, indent=2, default=str))
    else:
        print(json.dumps({"result": None, "message": f"No active coupons found for {retailer}"}))


def _cli_list(args):
    """Handle the 'list' subcommand."""
    retailer = args.retailer.lower().strip()
    coupons = get_all_coupons(retailer, active_only=not args.all)

    if coupons:
        for c in coupons:
            code_str = f"[{c['code']}]" if c.get("code") else "[no code]"
            verified_str = " (verified)" if c.get("verified") else ""
            rate_str = f" | {c['success_rate']:.0f}% success" if c.get("success_rate", 0) > 0 else ""
            expiry_str = f" | expires {c['expiry_date']}" if c.get("expiry_date") else ""
            print(f"  #{c['id']} {code_str} {c['description'][:60]}{verified_str}{rate_str}{expiry_str}")
        print(f"\n  Total: {len(coupons)} coupons")
    else:
        print(f"  No coupons found for {retailer}")


def _cli_stats(args):
    """Handle the 'stats' subcommand."""
    stats = get_stats()
    if not stats:
        print("  No coupons in database. Run 'scrape' first.")
        return

    print("\n  Coupon Stats by Retailer")
    print("  " + "-" * 70)
    print(f"  {'Retailer':<15} {'Total':>6} {'Active':>7} {'W/Code':>7} {'Avg Rate':>9} {'Last Scraped':>20}")
    print("  " + "-" * 70)

    for s in stats:
        rate = f"{s['avg_success_rate']:.0f}%" if s.get("avg_success_rate") else "n/a"
        last = s.get("last_scraped", "never")
        if last and len(last) > 19:
            last = last[:19]
        print(
            f"  {s['retailer']:<15} {s['total']:>6} {s['active']:>7} "
            f"{s['with_code']:>7} {rate:>9} {last:>20}"
        )

    total = sum(s["total"] for s in stats)
    active = sum(s["active"] for s in stats)
    print("  " + "-" * 70)
    print(f"  {'TOTAL':<15} {total:>6} {active:>7}")
    print()


def _cli_mark(args):
    """Handle the 'mark' subcommand."""
    if not args.worked and not args.failed:
        log.error("Specify --worked or --failed")
        sys.exit(1)

    worked = args.worked
    mark_coupon_used(args.id, worked)
    status = "worked" if worked else "failed"
    print(json.dumps({"coupon_id": args.id, "status": status}))


def main():
    parser = argparse.ArgumentParser(
        description="Coupon scraper for FBA sourcing pipeline (Layer 3: Coupons)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    sp_scrape = subparsers.add_parser("scrape", help="Scrape coupons from RetailMeNot")
    sp_scrape.add_argument("--retailer", type=str, default=None, help="Scrape single retailer")

    # lookup
    sp_lookup = subparsers.add_parser("lookup", help="Find best coupon for a purchase")
    sp_lookup.add_argument("--retailer", type=str, required=True, help="Retailer name")
    sp_lookup.add_argument("--amount", type=float, default=None, help="Purchase amount in dollars")

    # list
    sp_list = subparsers.add_parser("list", help="List all coupons for a retailer")
    sp_list.add_argument("--retailer", type=str, required=True, help="Retailer name")
    sp_list.add_argument("--all", action="store_true", help="Include expired coupons")

    # stats
    subparsers.add_parser("stats", help="Show coupon statistics")

    # mark
    sp_mark = subparsers.add_parser("mark", help="Mark coupon as worked or failed")
    sp_mark.add_argument("--id", type=int, required=True, help="Coupon ID")
    sp_mark.add_argument("--worked", action="store_true", help="Mark as worked")
    sp_mark.add_argument("--failed", action="store_true", help="Mark as failed")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "scrape": _cli_scrape,
        "lookup": _cli_lookup,
        "list": _cli_list,
        "stats": _cli_stats,
        "mark": _cli_mark,
    }

    handlers[args.command](args)


if __name__ == "__main__":
    main()
