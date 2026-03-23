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

        conn.execute("""
            INSERT INTO review_queue
                (name, asin, amazon_url, amazon_price, source_price, source_url,
                 bsr, category, roi_percent, profit, fba_seller_count,
                 amazon_on_listing, verdict, source_scanner, source_file, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def format_discord_message(product: dict) -> str:
    """Format a single product as a Discord message."""
    roi_str = f"{product['roi_percent']:.0f}%" if product.get('roi_percent') else "N/A"
    profit_str = f"${product['profit']:.2f}" if product.get('profit') else "N/A"
    amz = f"${product['amazon_price']:.2f}" if product.get('amazon_price') else "?"
    src = f"${product['source_price']:.2f}" if product.get('source_price') else "?"
    bsr_str = f"{product['bsr']:,}" if product.get('bsr') else "N/A"

    msg = f"""🤖 **AI Powered Product Find**

**{product['name'][:100]}**

**ASIN:** `{product.get('asin', '?')}`
**BSR:** {bsr_str} in {product.get('category', 'Unknown')}
**Source Price:** {src} → **Amazon Price:** {amz}
**Profit:** {profit_str} | **ROI:** {roi_str}
**FBA Sellers:** {product.get('fba_seller_count', '?')} | **Amazon on listing:** {'Yes' if product.get('amazon_on_listing') else 'No'}

**Amazon:** <https://www.amazon.com/dp/{product.get('asin', '')}>"""

    if product.get('source_url'):
        msg += f"\n**Buy Link:** <{product['source_url']}>"

    return msg


def send_to_discord(conn: sqlite3.Connection, channel_id: str, dry_run: bool = False) -> int:
    """Send all approved products to Discord channel."""
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

    # Send header
    header = f"🤖 **AI Powered Product Find** — {len(products)} products | {datetime.now().strftime('%B %d, %Y')}\n{'─' * 40}"

    if dry_run:
        print(f"\n[DRY RUN] Would send to channel {channel_id}:\n")
        print(header)
        for p in products:
            print(f"\n{format_discord_message(p)}")
            print("─" * 40)
        return len(products)

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    sent = 0

    # Send header
    resp = requests.post(url, headers=headers, json={"content": header}, timeout=15)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to send header: {resp.status_code} {resp.text[:200]}")
        return 0

    import time
    for p in products:
        msg = format_discord_message(p)

        # Discord 2000 char limit
        if len(msg) > 1990:
            msg = msg[:1990] + "..."

        resp = requests.post(url, headers=headers, json={"content": msg}, timeout=15)
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
