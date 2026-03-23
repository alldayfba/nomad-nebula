#!/usr/bin/env python3
"""
Script: sourcing_review_queue.py
Purpose: QA gate between overnight sourcing scans and Discord delivery.
         Products land here from cron jobs, Sabbo reviews in the morning,
         approves/rejects, then approved items get formatted and sent to Discord.

Flow:
  [Overnight crons] → queue → [Morning review] → approve → [Discord send]

CLI:
  python execution/sourcing_review_queue.py ingest --file .tmp/sourcing/results.json [--source deal_scanner]
  python execution/sourcing_review_queue.py ingest-dir                      # Ingest all new .json files from .tmp/sourcing/
  python execution/sourcing_review_queue.py review                          # Show pending products
  python execution/sourcing_review_queue.py approve --all                   # Approve all pending
  python execution/sourcing_review_queue.py approve --ids 1,3,5             # Cherry-pick by queue ID
  python execution/sourcing_review_queue.py reject --ids 2,4 --reason "Low ROI"
  python execution/sourcing_review_queue.py send --channel-id 1250966307021656115  # Send approved to Discord
  python execution/sourcing_review_queue.py status                          # Queue stats
  python execution/sourcing_review_queue.py clear --status sent             # Purge sent items
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
QUEUE_DB = TMP_DIR / "review_queue.db"
INGESTED_LOG = TMP_DIR / "review_queue_ingested.json"

# ── Database ─────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    """Connect to the review queue database."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(QUEUE_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            asin TEXT,
            amazon_url TEXT,
            amazon_price REAL,
            source_price REAL,
            source_url TEXT,
            bsr INTEGER,
            category TEXT,
            roi_percent REAL,
            profit REAL,
            fba_seller_count INTEGER,
            amazon_on_listing INTEGER DEFAULT 0,
            verdict TEXT,
            source_scanner TEXT,
            source_file TEXT,
            raw_json TEXT,
            status TEXT DEFAULT 'pending',
            rejection_reason TEXT,
            queued_at TEXT DEFAULT (datetime('now','localtime')),
            reviewed_at TEXT,
            sent_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);
        CREATE INDEX IF NOT EXISTS idx_rq_asin ON review_queue(asin);
    """)
    # Add image_url column if missing (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE review_queue ADD COLUMN image_url TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.commit()


# ── Ingest ───────────────────────────────────────────────────────────────────


def _load_ingested_log() -> set:
    """Track which files have already been ingested to avoid duplicates."""
    if INGESTED_LOG.exists():
        data = json.loads(INGESTED_LOG.read_text())
        return set(data.get("files", []))
    return set()


def _save_ingested_log(files: set) -> None:
    INGESTED_LOG.write_text(json.dumps({"files": sorted(files)}, indent=2))


def ingest_file(conn: sqlite3.Connection, filepath: str, source: str = "unknown") -> int:
    """Ingest products from a JSON results file into the review queue."""
    p = Path(filepath)
    if not p.exists():
        print(f"  [SKIP] File not found: {filepath}")
        return 0

    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        print(f"  [SKIP] Invalid JSON: {filepath}")
        return 0

    if not isinstance(data, list):
        data = [data]

    ingested = 0
    for product in data:
        asin = product.get("asin", "")
        if not asin:
            continue

        # Skip if already in queue (any status)
        existing = conn.execute(
            "SELECT id FROM review_queue WHERE asin = ? AND status IN ('pending', 'approved')",
            (asin,)
        ).fetchone()
        if existing:
            continue

        # Extract profitability fields
        prof = product.get("profitability", {})
        roi = prof.get("roi_percent") or product.get("roi_percent")
        profit = prof.get("profit") or product.get("profit")
        source_price = prof.get("source_price") or product.get("source_price")
        source_url = prof.get("buy_url") or product.get("buy_url") or product.get("source_url", "")

        # Extract image URL from scan data
        image_url = (
            product.get("image_url") or product.get("image")
            or prof.get("image") or product.get("img_url") or ""
        )
        if isinstance(image_url, list):
            image_url = image_url[0] if image_url else ""

        conn.execute("""
            INSERT INTO review_queue
                (name, asin, amazon_url, amazon_price, source_price, source_url,
                 bsr, category, roi_percent, profit, fba_seller_count,
                 amazon_on_listing, verdict, source_scanner, source_file, raw_json, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product.get("name", "Unknown"),
            asin,
            product.get("amazon_url", f"https://www.amazon.com/dp/{asin}"),
            product.get("amazon_price"),
            source_price,
            source_url,
            product.get("bsr"),
            product.get("category", ""),
            roi,
            profit,
            product.get("fba_seller_count"),
            1 if product.get("amazon_on_listing") else 0,
            product.get("verdict", ""),
            source,
            str(p.name),
            json.dumps(product),
            image_url,
        ))
        ingested += 1

    conn.commit()
    return ingested


def ingest_dir(conn: sqlite3.Connection) -> int:
    """Ingest all new JSON result files from .tmp/sourcing/."""
    ingested_files = _load_ingested_log()
    total = 0

    for f in sorted(TMP_DIR.glob("*_source_results.json")):
        if str(f.name) in ingested_files:
            continue
        count = ingest_file(conn, str(f), source="source.py")
        if count > 0:
            print(f"  [INGESTED] {f.name}: {count} products")
        ingested_files.add(str(f.name))
        total += count

    for f in sorted(TMP_DIR.glob("*-multi-results.json")):
        if str(f.name) in ingested_files:
            continue
        count = ingest_file(conn, str(f), source="multi_retailer")
        if count > 0:
            print(f"  [INGESTED] {f.name}: {count} products")
        ingested_files.add(str(f.name))
        total += count

    for f in sorted(TMP_DIR.glob("deal_scanner_*.json")):
        if str(f.name) in ingested_files:
            continue
        count = ingest_file(conn, str(f), source="deal_scanner")
        if count > 0:
            print(f"  [INGESTED] {f.name}: {count} products")
        ingested_files.add(str(f.name))
        total += count

    for f in sorted(TMP_DIR.glob("abs_*.json")):
        if str(f.name) in ingested_files:
            continue
        if f.name == "abs_brand_watchlist.json":
            continue
        count = ingest_file(conn, str(f), source="always_be_scanning")
        if count > 0:
            print(f"  [INGESTED] {f.name}: {count} products")
        ingested_files.add(str(f.name))
        total += count

    _save_ingested_log(ingested_files)
    return total


# ── Review ───────────────────────────────────────────────────────────────────


def review_pending(conn: sqlite3.Connection) -> list[dict]:
    """Show all pending products for review."""
    rows = conn.execute("""
        SELECT id, name, asin, amazon_price, source_price, source_url,
               bsr, category, roi_percent, profit, fba_seller_count,
               amazon_on_listing, verdict, source_scanner, queued_at
        FROM review_queue
        WHERE status = 'pending'
        ORDER BY roi_percent DESC NULLS LAST, bsr ASC NULLS LAST
    """).fetchall()
    return [dict(r) for r in rows]


def format_review_table(products: list[dict]) -> str:
    """Format products into a readable review table."""
    if not products:
        return "No pending products to review."

    lines = [
        f"\n{'='*80}",
        f"  SOURCING REVIEW QUEUE — {len(products)} products pending",
        f"{'='*80}\n",
    ]

    for p in products:
        roi_str = f"{p['roi_percent']:.0f}%" if p.get('roi_percent') else "N/A"
        profit_str = f"${p['profit']:.2f}" if p.get('profit') else "N/A"
        amz = f"${p['amazon_price']:.2f}" if p.get('amazon_price') else "?"
        src = f"${p['source_price']:.2f}" if p.get('source_price') else "?"
        bsr_str = f"{p['bsr']:,}" if p.get('bsr') else "N/A"
        sellers = p.get('fba_seller_count', '?')
        amz_on = "YES" if p.get('amazon_on_listing') else "no"
        verdict = p.get('verdict', '?')

        lines.append(f"  #{p['id']}  {p['name'][:60]}")
        lines.append(f"      ASIN: {p['asin']}  |  BSR: {bsr_str}  |  Category: {p.get('category', '?')}")
        lines.append(f"      Source: {src} → Amazon: {amz}  |  Profit: {profit_str}  |  ROI: {roi_str}")
        lines.append(f"      Sellers: {sellers}  |  Amazon on listing: {amz_on}  |  Verdict: {verdict}")
        lines.append(f"      Scanner: {p.get('source_scanner', '?')}  |  Queued: {p.get('queued_at', '?')}")
        if p.get('source_url'):
            lines.append(f"      Buy: {p['source_url']}")
        lines.append(f"      Amazon: https://www.amazon.com/dp/{p['asin']}")
        lines.append("")

    lines.append(f"{'─'*80}")
    lines.append(f"  Commands:")
    lines.append(f"    approve --all                    Approve all {len(products)} products")
    lines.append(f"    approve --ids 1,3,5              Cherry-pick by ID")
    lines.append(f"    reject --ids 2,4 --reason 'why'  Reject specific products")
    lines.append(f"    send --channel-id <ID>           Send approved to Discord")
    lines.append(f"{'─'*80}")

    return "\n".join(lines)


# ── Approve / Reject ─────────────────────────────────────────────────────────


def approve_products(conn: sqlite3.Connection, ids: list[int] | None = None) -> int:
    """Approve products for Discord delivery."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE review_queue SET status = 'approved', reviewed_at = ? WHERE id IN ({placeholders}) AND status = 'pending'",
            [now] + ids,
        )
    else:
        conn.execute(
            "UPDATE review_queue SET status = 'approved', reviewed_at = ? WHERE status = 'pending'",
            (now,),
        )
    conn.commit()
    return conn.total_changes


def reject_products(conn: sqlite3.Connection, ids: list[int], reason: str = "") -> int:
    """Reject products with optional reason."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE review_queue SET status = 'rejected', reviewed_at = ?, rejection_reason = ? WHERE id IN ({placeholders}) AND status = 'pending'",
        [now, reason] + ids,
    )
    conn.commit()
    return conn.total_changes


# ── Discord Send ─────────────────────────────────────────────────────────────


def _get_gift_card_discount(retailer_name: str) -> str:
    """Look up current gift card discount for a retailer from CardBear DB."""
    try:
        gc_db = TMP_DIR / "price_tracker.db"
        if not gc_db.exists():
            return "None"
        conn = sqlite3.connect(str(gc_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT discount_percent, cardbear_url FROM gift_card_latest WHERE LOWER(retailer_name) = LOWER(?) AND discount_percent > 0",
            (retailer_name,)
        ).fetchone()
        conn.close()
        if row and row["discount_percent"] > 0:
            url_part = f" — [CardBear]({row['cardbear_url']})" if row.get("cardbear_url") else ""
            return f"{row['discount_percent']:.1f}% off gift cards{url_part}"
    except Exception:
        pass
    return "None"


def _extract_retailer_from_url(url: str) -> str:
    """Extract retailer name from a source URL."""
    if not url:
        return ""
    url_lower = url.lower()
    retailers = {
        "walmart": "Walmart", "target": "Target", "cvs": "CVS",
        "walgreens": "Walgreens", "costco": "Costco", "homedepot": "Home Depot",
        "lowes": "Lowe's", "bestbuy": "Best Buy", "kohls": "Kohl's",
        "macys": "Macy's", "nordstrom": "Nordstrom", "sephora": "Sephora",
        "ulta": "Ulta", "staples": "Staples", "gamestop": "GameStop",
        "nike": "Nike", "adidas": "Adidas", "amazon": "Amazon",
    }
    for key, name in retailers.items():
        if key in url_lower:
            return name
    return ""


def _get_product_image(product: dict) -> str | None:
    """Get a product image URL from scan data."""
    # Check top-level product dict first
    for key in ("image_url", "image", "img_url", "thumbnail", "amazon_image"):
        val = product.get(key)
        if val:
            if isinstance(val, list):
                return val[0] if val else None
            return val

    # Check raw_json (full scan result stored as JSON string)
    raw = product.get("raw_json")
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            # Check top level
            for key in ("image_url", "image", "img_url", "thumbnail", "amazon_image"):
                val = data.get(key)
                if val:
                    if isinstance(val, list):
                        return val[0] if val else None
                    return val
            # Check nested profitability dict (Keepa results)
            prof = data.get("profitability", {})
            if prof.get("image"):
                return prof["image"]
        except Exception:
            pass

    # Keepa image format — if we have a keepa image ID
    # Format: https://m.media-amazon.com/images/I/{imageId}._SL200_.jpg
    return None


def format_discord_embed(product: dict) -> dict:
    """Format a single product as a Discord embed."""
    roi_str = f"{product['roi_percent']:.0f}%" if product.get('roi_percent') else "N/A"
    profit_str = f"${product['profit']:.2f}" if product.get('profit') else "N/A"
    amz = f"${product['amazon_price']:.2f}" if product.get('amazon_price') else "?"
    src = f"${product['source_price']:.2f}" if product.get('source_price') else "?"
    bsr_str = f"{product['bsr']:,}" if product.get('bsr') else "N/A"
    asin = product.get('asin', '?')

    # Calculate margin
    margin = "N/A"
    if product.get('profit') and product.get('amazon_price') and product['amazon_price'] > 0:
        margin = f"{(product['profit'] / product['amazon_price'] * 100):.1f}%"

    sellers = product.get('fba_seller_count', '?')
    amz_on = "Yes" if product.get('amazon_on_listing') else "No"

    # Auto-lookup gift card discount from CardBear
    retailer = _extract_retailer_from_url(product.get('source_url', ''))
    coupon_str = product.get('coupon') or ""
    gc_discount_pct = 0.0
    if retailer:
        gc_info = _get_gift_card_discount(retailer)
        if gc_info != "None":
            coupon_str = gc_info
            # Extract the discount % for ROI calculation
            import re as _re
            m = _re.search(r'([\d.]+)%', gc_info)
            if m:
                gc_discount_pct = float(m.group(1))
    if not coupon_str:
        coupon_str = "None"

    # Calculate ROI with gift card discount applied
    roi_with_gc = "N/A"
    if gc_discount_pct > 0 and product.get('source_price') and product.get('amazon_price'):
        discounted_cost = product['source_price'] * (1 - gc_discount_pct / 100)
        gc_profit = product.get('profit', 0) + (product['source_price'] - discounted_cost)
        if discounted_cost > 0:
            roi_with_gc = f"{(gc_profit / discounted_cost * 100):.0f}%"

    # Build ROI display — show both if gift card discount exists
    if gc_discount_pct > 0 and roi_with_gc != "N/A":
        roi_display = f"{roi_str} → **{roi_with_gc}** w/ GC"
    else:
        roi_display = roi_str

    notes_parts = []
    notes_parts.append(f"FBA Sellers: {sellers} | Amazon on listing: {amz_on}")
    if retailer:
        notes_parts.append(f"Source: {retailer}")
    if product.get('source_url'):
        notes_parts.append(f"[Buy Link]({product['source_url']})")

    embed = {
        "title": "🤖 AI Powered Product Find",
        "color": 0xBF5AF2,
        "fields": [
            {"name": "🏷 Product", "value": product.get('name', 'Unknown')[:100], "inline": False},
            {"name": "🛒 Buy Price", "value": src, "inline": True},
            {"name": "💰 Sell Price", "value": amz, "inline": True},
            {"name": "📈 Profit", "value": profit_str, "inline": True},
            {"name": "🧮 Profit Margin", "value": margin, "inline": True},
            {"name": "📊 ROI", "value": roi_display, "inline": True},
            {"name": "📦 ASIN", "value": f"[{asin}](https://www.amazon.com/dp/{asin})", "inline": True},
            {"name": "📉 BSR", "value": f"{bsr_str} in {product.get('category', 'Unknown')}", "inline": True},
            {"name": "🎟️ Coupons / Gift Cards", "value": coupon_str, "inline": True},
            {"name": "📝 Notes", "value": "\n".join(notes_parts) if notes_parts else "—", "inline": False},
        ],
        "footer": {"text": "24/7 Profits AI Sourcing"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Try to get a real product image — check DB column first, then raw_json
    img_url = product.get("image_url") or _get_product_image(product)
    if img_url and isinstance(img_url, str) and img_url.startswith("http"):
        embed["thumbnail"] = {"url": img_url}

    return embed


def send_to_discord(conn: sqlite3.Connection, channel_id: str, dry_run: bool = False) -> int:
    """Send all approved products to Discord channel as embeds."""
    if not requests:
        print("[ERROR] requests package not installed")
        return 0

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token and not dry_run:
        print("[ERROR] DISCORD_BOT_TOKEN not set in .env")
        return 0

    rows = conn.execute("""
        SELECT * FROM review_queue WHERE status = 'approved' ORDER BY roi_percent DESC NULLS LAST
    """).fetchall()

    if not rows:
        print("[review-queue] No approved products to send.")
        return 0

    products = [dict(r) for r in rows]

    if dry_run:
        print(f"\n[DRY RUN] Would send {len(products)} products to channel {channel_id}")
        for p in products:
            embed = format_discord_embed(p)
            print(f"\n  {embed['fields'][0]['value']} — ROI: {embed['fields'][4]['value']}")
        return len(products)

    headers_dict = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    sent = 0
    import time

    for p in products:
        embed = format_discord_embed(p)
        resp = requests.post(url, headers=headers_dict, json={"embeds": [embed]}, timeout=15)
        if resp.status_code in (200, 201):
            conn.execute(
                "UPDATE review_queue SET status = 'sent', sent_at = ? WHERE id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), p["id"]),
            )
            sent += 1
        else:
            print(f"  [ERROR] Failed to send #{p['id']}: {resp.status_code}")

        time.sleep(1)  # Rate limit

    conn.commit()
    print(f"[review-queue] Sent {sent}/{len(products)} products to Discord.")
    return sent


# ── Status ───────────────────────────────────────────────────────────────────


def get_status(conn: sqlite3.Connection) -> dict:
    """Get queue statistics."""
    stats = {}
    for status_val in ("pending", "approved", "rejected", "sent"):
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_queue WHERE status = ?", (status_val,)
        ).fetchone()
        stats[status_val] = row["cnt"]
    stats["total"] = sum(stats.values())

    # Top sources
    sources = conn.execute("""
        SELECT source_scanner, COUNT(*) as cnt
        FROM review_queue WHERE status = 'pending'
        GROUP BY source_scanner ORDER BY cnt DESC
    """).fetchall()
    stats["pending_by_source"] = {r["source_scanner"]: r["cnt"] for r in sources}

    return stats


# ── Clear ────────────────────────────────────────────────────────────────────


def clear_by_status(conn: sqlite3.Connection, status_val: str) -> int:
    """Delete items with given status."""
    conn.execute("DELETE FROM review_queue WHERE status = ?", (status_val,))
    conn.commit()
    return conn.total_changes


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Sourcing Review Queue — QA gate for Discord drops")
    sub = parser.add_subparsers(dest="command")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest products from a JSON file")
    p_ingest.add_argument("--file", type=str, help="JSON file to ingest")
    p_ingest.add_argument("--source", type=str, default="manual", help="Scanner name")

    # ingest-dir
    sub.add_parser("ingest-dir", help="Ingest all new JSON files from .tmp/sourcing/")

    # review
    sub.add_parser("review", help="Show pending products for review")

    # approve
    p_approve = sub.add_parser("approve", help="Approve products for Discord delivery")
    p_approve.add_argument("--all", action="store_true", help="Approve all pending")
    p_approve.add_argument("--ids", type=str, help="Comma-separated IDs to approve")

    # reject
    p_reject = sub.add_parser("reject", help="Reject products")
    p_reject.add_argument("--ids", type=str, required=True, help="Comma-separated IDs")
    p_reject.add_argument("--reason", type=str, default="", help="Rejection reason")

    # send
    p_send = sub.add_parser("send", help="Send approved products to Discord")
    p_send.add_argument("--channel-id", type=str, required=True, help="Discord channel ID")
    p_send.add_argument("--dry-run", action="store_true", help="Preview without sending")

    # status
    sub.add_parser("status", help="Queue statistics")

    # clear
    p_clear = sub.add_parser("clear", help="Clear items by status")
    p_clear.add_argument("--status", type=str, required=True,
                         choices=["sent", "rejected", "pending", "approved"])

    args = parser.parse_args()
    conn = get_db()

    if args.command == "ingest":
        if not args.file:
            print("[review-queue] --file required for ingest")
            sys.exit(1)
        count = ingest_file(conn, args.file, args.source)
        print(f"[review-queue] Ingested {count} products from {args.file}")

    elif args.command == "ingest-dir":
        count = ingest_dir(conn)
        print(f"[review-queue] Ingested {count} total new products")

    elif args.command == "review":
        products = review_pending(conn)
        print(format_review_table(products))

    elif args.command == "approve":
        if args.ids:
            ids = [int(x.strip()) for x in args.ids.split(",")]
            count = approve_products(conn, ids)
        elif args.all:
            count = approve_products(conn)
        else:
            print("[review-queue] Use --all or --ids")
            sys.exit(1)
        print(f"[review-queue] Approved {count} products")

    elif args.command == "reject":
        ids = [int(x.strip()) for x in args.ids.split(",")]
        count = reject_products(conn, ids, args.reason)
        print(f"[review-queue] Rejected {count} products: {args.reason}")

    elif args.command == "send":
        sent = send_to_discord(conn, args.channel_id, dry_run=args.dry_run)
        print(f"[review-queue] {sent} products {'would be sent' if args.dry_run else 'sent'}")

    elif args.command == "status":
        stats = get_status(conn)
        print(f"\n[review-queue] Queue Status:")
        print(f"  Pending:   {stats['pending']}")
        print(f"  Approved:  {stats['approved']}")
        print(f"  Sent:      {stats['sent']}")
        print(f"  Rejected:  {stats['rejected']}")
        print(f"  Total:     {stats['total']}")
        if stats.get("pending_by_source"):
            print(f"\n  Pending by source:")
            for src, cnt in stats["pending_by_source"].items():
                print(f"    {src}: {cnt}")
        print()

    elif args.command == "clear":
        count = clear_by_status(conn, args.status)
        print(f"[review-queue] Cleared {count} '{args.status}' items")

    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
