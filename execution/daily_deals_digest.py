#!/usr/bin/env python3
"""Daily Deals Digest — unified notification of sourceable discounts.

Pulls from:
  - price_tracker.db gift_card_latest (CardBear scraper output)
  - price_tracker.db coupons (RetailMeNot scraper output)
  - .tmp/sourcing/deals_rss.json (deal_feed_scanner.py output, if present)

Filters to FBA-relevant retailers (no restaurants / non-physical).
Posts a rich Discord embed showing:
  - Top gift card discounts for sourceable retailers
  - Discount INCREASES vs previous run (signal — something changed)
  - New coupons in the last 24h
  - Top RSS deal hits (if scanner ran)

CLI:
  python3 execution/daily_deals_digest.py            # send digest to Discord
  python3 execution/daily_deals_digest.py --dry-run  # print only, no send
  python3 execution/daily_deals_digest.py --top 20   # show top N retailers

Schedule (launchd): runs 8am daily after CardBear scrape at 7am.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("[deals-digest] Missing 'requests'. pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "price_tracker.db"
RSS_JSON = PROJECT_ROOT / ".tmp" / "sourcing" / "deals_rss.json"

# FBA-sourceable retailers (physical goods, available nationally or online).
# Restaurants, spas, gift experiences, and subscriptions are excluded.
FBA_RELEVANT = {
    # Big box / department
    "Target", "Walmart", "Kohl's", "Macy's", "JCPenney", "Nordstrom", "Nordstrom Rack",
    "Dillard's", "Belk", "Bloomingdale's", "Saks Fifth Avenue", "Saks OFF 5TH",
    # Drug / beauty
    "CVS", "Walgreens", "Rite Aid", "Ulta", "Sephora", "Bath & Body Works",
    "Sally Beauty", "Beauty Brands",
    # Electronics / home
    "Best Buy", "Home Depot", "Lowe's", "Menards", "Ace Hardware", "True Value",
    "Bed Bath & Beyond", "Bed Bath and Beyond", "Container Store", "HomeGoods",
    "At Home", "IKEA", "World Market",
    # Sporting / outdoor
    "Dick's Sporting Goods", "REI", "Academy Sports", "Bass Pro Shops", "Cabela's",
    "Scheels", "Modell's",
    # Apparel
    "Nike", "Adidas", "Under Armour", "Puma", "New Balance", "Reebok", "Lululemon",
    "Gap", "Old Navy", "Banana Republic", "Athleta", "J.Crew", "H&M", "Uniqlo",
    "American Eagle", "Aerie", "Hollister", "Abercrombie & Fitch", "PacSun",
    "Zumiez", "Vans", "Tillys", "Urban Outfitters", "Anthropologie", "Free People",
    "Ann Taylor", "LOFT", "Express", "Talbots", "Chico's", "White House Black Market",
    "Lucky Brand", "Levi's", "Guess", "Calvin Klein", "Tommy Hilfiger",
    # Off-price
    "TJ Maxx", "T.J.Maxx", "Marshalls", "Burlington", "Ross",
    # Discount / dollar
    "Dollar General", "Dollar Tree", "Five Below", "Big Lots", "Ollie's Bargain Outlet",
    # Warehouse
    "Costco", "Sam's Club", "BJ's Wholesale",
    # Specialty
    "GameStop", "Barnes & Noble", "Books-A-Million", "Michael's", "Michaels",
    "Hobby Lobby", "JOANN", "Joann", "A.C. Moore", "Party City", "Spirit Halloween",
    "Petco", "PetSmart", "Tractor Supply",
    # Toys / kids
    "Toys R Us", "Build-A-Bear", "Learning Express", "Lakeshore Learning",
    # Health / supplements
    "GNC", "Vitamin Shoppe", "The Vitamin Shoppe", "Puritan's Pride",
    # Baby
    "buybuy Baby", "Carter's", "OshKosh B'gosh", "Children's Place",
    # Pet / home improvement extras
    "Chewy", "Wayfair",
}

# Soft match — if the CardBear retailer name contains any of these tokens,
# treat as FBA-relevant even if not in the exact set above.
FBA_TOKENS = {"target", "walmart", "amazon", "ebay", "bestbuy", "homedepot", "lowes"}

EXCLUDE_TOKENS = {
    "restaurant", "pizza", "grill", "buffet", "cafe", "bistro",
    "spa", "salon", "massage", "nails",
    "airline", "hotel", "cruise", "vacation", "resort",
    "gas station", "shell", "exxon", "mobil", "chevron", "bp ",
    "netflix", "hulu", "spotify", "doordash", "uber eats", "grubhub",
    "movie", "cinema", "theater", "theatre", "amc ",
}


def is_fba_relevant(retailer: str) -> bool:
    r = retailer.strip()
    lower = r.lower()
    if any(tok in lower for tok in EXCLUDE_TOKENS):
        return False
    if r in FBA_RELEVANT:
        return True
    # Token match
    if any(tok in lower.replace(" ", "") for tok in FBA_TOKENS):
        return True
    return False


def load_gift_cards(min_discount: float = 4.0) -> tuple[list[dict], list[dict]]:
    """Returns (top_fba, increases_fba)."""
    if not DB_PATH.exists():
        return [], []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT retailer_name, discount_percent, previous_discount, last_updated "
            "FROM gift_card_latest WHERE discount_percent >= ? ORDER BY discount_percent DESC",
            (min_discount,),
        ).fetchall()
    finally:
        conn.close()

    fba = [dict(r) for r in rows if is_fba_relevant(r["retailer_name"])]
    increases = [
        r for r in fba
        if r["previous_discount"] is not None and r["discount_percent"] > r["previous_discount"] + 0.1
    ]
    return fba, increases


def load_recent_coupons(hours: int = 24, limit: int = 20) -> list[dict]:
    if not DB_PATH.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT retailer, code, description, discount_type, discount_value, scraped_at "
            "FROM coupons WHERE scraped_at >= ? ORDER BY scraped_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows if is_fba_relevant(r["retailer"])]


def load_rss_deals(limit: int = 10) -> list[dict]:
    if not RSS_JSON.exists():
        return []
    try:
        data = json.loads(RSS_JSON.read_text())
    except Exception:
        return []
    deals = data.get("deals") if isinstance(data, dict) else data
    if not isinstance(deals, list):
        return []
    # Sort by deal_score if present
    deals.sort(key=lambda d: d.get("deal_score", 0) or d.get("score", 0) or 0, reverse=True)
    return deals[:limit]


def build_embed(top_fba: list[dict], increases: list[dict], coupons: list[dict], rss: list[dict], top_n: int) -> dict:
    today = datetime.now().strftime("%a, %b %d")
    fields = []

    # Discount increases — most actionable signal
    if increases:
        lines = [
            f"**{r['retailer_name']}** — {r['previous_discount']:.1f}% → **{r['discount_percent']:.1f}%**"
            for r in sorted(increases, key=lambda x: x["discount_percent"] - (x["previous_discount"] or 0), reverse=True)[:10]
        ]
        fields.append({
            "name": f"📈 Discount Increases ({len(increases)})",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })

    # Top gift card discounts (sourceable retailers only)
    if top_fba:
        top_slice = top_fba[:top_n]
        lines = [f"**{r['retailer_name']}** — {r['discount_percent']:.1f}% off" for r in top_slice]
        fields.append({
            "name": f"🎁 Top Gift Card Discounts ({len(top_fba)} sourceable)",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })

    # New coupons
    if coupons:
        lines = []
        for c in coupons[:10]:
            val = ""
            if c.get("discount_type") == "percent":
                val = f" ({c['discount_value']:.0f}% off)"
            elif c.get("discount_type") == "fixed":
                val = f" (${c['discount_value']:.0f} off)"
            elif c.get("discount_type") == "free_shipping":
                val = " (free ship)"
            desc = (c.get("description") or "").strip()[:60]
            code = c.get("code") or ""
            line = f"**{c['retailer']}**{val}"
            if code:
                line += f" — `{code}`"
            if desc:
                line += f"\n  _{desc}_"
            lines.append(line)
        fields.append({
            "name": f"🏷️ New Coupons (last 24h, {len(coupons)})",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })

    # RSS deal hits
    if rss:
        lines = []
        for d in rss:
            title = (d.get("title") or d.get("product_name") or "Deal")[:80]
            retailer = d.get("retailer") or d.get("store") or ""
            price = d.get("price") or d.get("retail_price")
            price_str = f" — ${price}" if price else ""
            roi = d.get("roi") or d.get("estimated_roi")
            roi_str = f" · {roi:.0f}% ROI" if isinstance(roi, (int, float)) and roi else ""
            lines.append(f"**{title}**{price_str}{roi_str}" + (f" @ {retailer}" if retailer else ""))
        fields.append({
            "name": f"🔥 RSS Deal Hits ({len(rss)})",
            "value": "\n".join(lines)[:1024],
            "inline": False,
        })

    if not fields:
        fields.append({
            "name": "No new deals today",
            "value": "CardBear scrape ran but nothing flagged as sourceable. Check the full DB with `sqlite3 .tmp/sourcing/price_tracker.db`.",
            "inline": False,
        })

    return {
        "title": f"Daily Deals Digest — {today}",
        "description": "Stores with active discounts, gift card arbitrage, and fresh coupons. Pair with `--auto-giftcard` / `--auto-coupon` in sourcing.",
        "color": 0xBF5AF2,
        "fields": fields,
        "footer": {"text": f"nomad-nebula · daily_deals_digest · {datetime.now().strftime('%H:%M')}"},
    }


def post_to_discord(embed: dict) -> bool:
    webhook = os.environ.get("DISCORD_DEALS_WEBHOOK") or os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        print("[deals-digest] No DISCORD_DEALS_WEBHOOK or DISCORD_WEBHOOK_URL in env", file=sys.stderr)
        return False
    try:
        resp = requests.post(webhook, json={"embeds": [embed]}, timeout=15)
        if resp.status_code >= 300:
            print(f"[deals-digest] Discord {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[deals-digest] Discord post failed: {e}", file=sys.stderr)
        return False


def print_digest(top_fba, increases, coupons, rss, top_n):
    print(f"\n=== Daily Deals Digest — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    if increases:
        print(f"📈 Discount Increases ({len(increases)}):")
        for r in sorted(increases, key=lambda x: x["discount_percent"] - (x["previous_discount"] or 0), reverse=True)[:10]:
            print(f"  {r['retailer_name']}: {r['previous_discount']:.1f}% → {r['discount_percent']:.1f}%")
        print()
    if top_fba:
        print(f"🎁 Top {top_n} Gift Card Discounts (FBA-sourceable):")
        for r in top_fba[:top_n]:
            print(f"  {r['retailer_name']}: {r['discount_percent']:.1f}%")
        print()
    if coupons:
        print(f"🏷️ New Coupons ({len(coupons)}):")
        for c in coupons[:10]:
            print(f"  {c['retailer']}: {c.get('code') or '(no code)'} — {c.get('description', '')[:60]}")
        print()
    if rss:
        print(f"🔥 RSS Deals ({len(rss)}):")
        for d in rss:
            print(f"  {d.get('title', 'deal')[:80]}")
        print()
    if not any([top_fba, increases, coupons, rss]):
        print("No deals to report today.\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print digest only, do not post to Discord")
    parser.add_argument("--top", type=int, default=15, help="Top N gift card discounts to show")
    parser.add_argument("--min-discount", type=float, default=4.0, help="Minimum gift card discount %")
    args = parser.parse_args()

    top_fba, increases = load_gift_cards(args.min_discount)
    coupons = load_recent_coupons()
    rss = load_rss_deals()

    print_digest(top_fba, increases, coupons, rss, args.top)

    # Always write a markdown snapshot — survives missing webhook, useful for morning brief
    snapshot_path = PROJECT_ROOT / ".tmp" / "daily_deals_digest.md"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Daily Deals Digest — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    if increases:
        lines.append(f"## Discount Increases ({len(increases)})")
        for r in sorted(increases, key=lambda x: x["discount_percent"] - (x["previous_discount"] or 0), reverse=True):
            lines.append(f"- **{r['retailer_name']}**: {r['previous_discount']:.1f}% → **{r['discount_percent']:.1f}%**")
        lines.append("")
    if top_fba:
        lines.append(f"## Top {args.top} Gift Card Discounts (FBA-sourceable)")
        for r in top_fba[:args.top]:
            lines.append(f"- **{r['retailer_name']}**: {r['discount_percent']:.1f}%")
        lines.append("")
    if coupons:
        lines.append(f"## Recent Coupons ({len(coupons)})")
        for c in coupons[:10]:
            lines.append(f"- **{c['retailer']}** — `{c.get('code') or '(no code)'}` — {c.get('description', '')[:80]}")
        lines.append("")
    if rss:
        lines.append(f"## RSS Deal Hits ({len(rss)})")
        for d in rss:
            lines.append(f"- {d.get('title', 'deal')[:100]}")
        lines.append("")
    snapshot_path.write_text("\n".join(lines))
    print(f"[deals-digest] Wrote snapshot: {snapshot_path}")

    if args.dry_run:
        return 0

    embed = build_embed(top_fba, increases, coupons, rss, args.top)
    ok = post_to_discord(embed)
    if ok:
        print("[deals-digest] Posted to Discord.")
        return 0
    print("[deals-digest] Discord post skipped/failed — snapshot still saved.")
    return 0  # Non-fatal: snapshot was saved so the digest is still useful


if __name__ == "__main__":
    sys.exit(main())
