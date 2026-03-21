#!/usr/bin/env python3
"""
Script: sourcing_drop.py
Purpose: Weekly automated sourcing drops for Amazon FBA coaching students.
         Generates beginner-friendly product lists from the sourcing pipeline,
         posts to Discord group channels, and dispatches targeted products to
         students stuck on product-related milestones.

CLI:
    python execution/sourcing_drop.py weekly-drop --channel-id 1234567890 [--count 10] [--dry-run]
    python execution/sourcing_drop.py dispatch-stuck [--days 14] [--dry-run]
    python execution/sourcing_drop.py review-product --asin B0XXXXXXXX
    python execution/sourcing_drop.py status
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

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

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"
SOURCING_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing"
PRICE_TRACKER_DB = SOURCING_DIR / "price_tracker.db"
DROPS_LOG = SOURCING_DIR / "drops_log.json"

# ── Beginner-Friendly Filters ───────────────────────────────────────────────

MIN_ROI = 30
MAX_BSR = 100_000
MIN_PRICE = 15.0
MAX_PRICE = 75.0

# Categories commonly ungated for new sellers
UNGATED_FRIENDLY_CATEGORIES = {
    "toys", "home", "kitchen", "sports", "outdoors", "office",
    "tools", "garden", "pet", "baby", "arts", "crafts",
}

# Categories to avoid (gating, hazmat, oversized)
AVOID_CATEGORIES = {
    "hazmat", "dangerous goods", "grocery", "topicals",
    "beauty", "health", "personal care", "supplements",
}


# ── Database ─────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    """Connect to the coaching students database."""
    if not DB_PATH.exists():
        print(f"ERROR: Students database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_drops_table(conn: sqlite3.Connection) -> None:
    """Create sourcing_drops table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sourcing_drops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drop_type TEXT NOT NULL,
            channel_id TEXT,
            student_id INTEGER,
            product_count INTEGER DEFAULT 0,
            products_json TEXT,
            status TEXT DEFAULT 'sent',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


# ── Discord ──────────────────────────────────────────────────────────────────


def send_channel_message(channel_id: str, content: str) -> tuple[bool, str]:
    """Send a message to a Discord channel. Splits into chunks if >2000 chars."""
    if requests is None:
        print("ERROR: requests library not installed")
        return False, "no_requests"

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("WARNING: DISCORD_BOT_TOKEN not set in .env")
        return False, "no_token"

    headers = {
        "Authorization": "Bot " + token,
        "Content-Type": "application/json",
    }

    # Discord limit is 2000 chars per message — split if needed
    chunks = []
    if len(content) <= 2000:
        chunks = [content]
    else:
        lines = content.split("\n")
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 1990:
                chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)

    success = True
    last_status = "200"
    for chunk in chunks:
        resp = requests.post(
            "https://discord.com/api/v10/channels/{}/messages".format(channel_id),
            headers=headers,
            json={"content": chunk},
            timeout=15,
        )
        if resp.status_code != 200:
            success = False
            last_status = str(resp.status_code)
            print("Discord API error {}: {}".format(resp.status_code, resp.text[:200]))

    return success, last_status


# ── Product Gathering ────────────────────────────────────────────────────────


def is_beginner_friendly(product: dict) -> bool:
    """Check if a product meets beginner-friendly criteria."""
    # ROI check
    roi = None
    if isinstance(product.get("profitability"), dict):
        roi = product["profitability"].get("roi_percent")
    elif product.get("roi"):
        roi = product["roi"]
    elif product.get("estimated_roi"):
        roi = product["estimated_roi"]

    if roi is not None:
        try:
            roi = float(roi)
        except (ValueError, TypeError):
            roi = None

    if roi is not None and roi < MIN_ROI:
        return False

    # BSR check
    bsr = product.get("bsr")
    if bsr is not None:
        try:
            bsr = int(bsr)
        except (ValueError, TypeError):
            bsr = None
    if bsr is not None and bsr > 0 and bsr > MAX_BSR:
        return False

    # Price check — use sell price (amazon_price) for affordability range
    sell_price = product.get("amazon_price") or product.get("sell_price")
    if sell_price is not None:
        try:
            sell_price = float(sell_price)
        except (ValueError, TypeError):
            sell_price = None
    if sell_price is not None and (sell_price < MIN_PRICE or sell_price > MAX_PRICE):
        return False

    # Category check — skip known problem categories
    category = (product.get("category") or "").lower()
    for avoid in AVOID_CATEGORIES:
        if avoid in category:
            return False

    return True


def extract_product_fields(raw: dict) -> dict:
    """Normalize a raw sourcing result into a standard product dict."""
    # Handle nested profitability
    prof = raw.get("profitability", {}) if isinstance(raw.get("profitability"), dict) else {}

    roi = prof.get("roi_percent") or raw.get("roi") or raw.get("estimated_roi")
    profit = prof.get("profit_per_unit") or raw.get("profit")

    try:
        roi = round(float(roi), 1) if roi is not None else None
    except (ValueError, TypeError):
        roi = None
    try:
        profit = round(float(profit), 2) if profit is not None else None
    except (ValueError, TypeError):
        profit = None

    sell_price = raw.get("amazon_price") or raw.get("sell_price")
    buy_price = raw.get("retail_price") or raw.get("buy_price") or raw.get("source_price")
    bsr = raw.get("bsr")

    try:
        sell_price = round(float(sell_price), 2) if sell_price is not None else None
    except (ValueError, TypeError):
        sell_price = None
    try:
        buy_price = round(float(buy_price), 2) if buy_price is not None else None
    except (ValueError, TypeError):
        buy_price = None
    try:
        bsr = int(bsr) if bsr is not None else None
    except (ValueError, TypeError):
        bsr = None

    return {
        "title": raw.get("name") or raw.get("title") or "Unknown Product",
        "asin": raw.get("asin") or "",
        "retailer": raw.get("retailer") or "",
        "buy_price": buy_price,
        "sell_price": sell_price,
        "roi": roi,
        "profit": profit,
        "bsr": bsr,
        "category": raw.get("category") or "",
        "brand": raw.get("brand") or "",
        "buy_url": raw.get("buy_url") or "",
        "amazon_url": raw.get("amazon_url") or "",
        "auto_ungated": raw.get("auto_ungated", False),
        "verdict": prof.get("verdict") or raw.get("verdict") or "",
    }


def gather_products_from_json(limit: int = 30) -> list[dict]:
    """Gather recent sourcing results from JSON files in .tmp/sourcing/."""
    products = []
    seen_asins = set()

    # Collect all result JSON files sorted newest first
    json_files = []
    for pattern in ["*_source_results.json", "*-deals.json", "*-results.json", "*-multi-results.json"]:
        json_files.extend(SOURCING_DIR.glob(pattern))

    json_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    for jf in json_files:
        if len(products) >= limit:
            break
        try:
            with open(jf) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for item in items:
            if len(products) >= limit:
                break
            asin = item.get("asin", "")
            if asin and asin in seen_asins:
                continue
            if not is_beginner_friendly(item):
                continue
            product = extract_product_fields(item)
            if product["asin"]:
                seen_asins.add(product["asin"])
            products.append(product)

    return products


def gather_products_from_supplier_db(limit: int = 20) -> list[dict]:
    """Gather products from the price_tracker supplier_products table."""
    if not PRICE_TRACKER_DB.exists():
        return []

    products = []
    try:
        conn = sqlite3.connect(str(PRICE_TRACKER_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT sp.product_name, sp.asin, sp.wholesale_cost, sp.estimated_roi,
                   ws.name as supplier_name
            FROM supplier_products sp
            LEFT JOIN wholesale_suppliers ws ON ws.id = sp.supplier_id
            WHERE sp.estimated_roi >= ?
            ORDER BY sp.estimated_roi DESC
            LIMIT ?
        """, (MIN_ROI, limit)).fetchall()
        conn.close()

        for r in rows:
            product = {
                "title": r["product_name"] or "Unknown",
                "asin": r["asin"] or "",
                "retailer": r["supplier_name"] or "Wholesale",
                "buy_price": r["wholesale_cost"],
                "sell_price": None,
                "roi": round(float(r["estimated_roi"]), 1) if r["estimated_roi"] else None,
                "profit": None,
                "bsr": None,
                "category": "",
                "brand": "",
                "buy_url": "",
                "amazon_url": "https://www.amazon.com/dp/{}".format(r["asin"]) if r["asin"] else "",
                "auto_ungated": False,
                "verdict": "",
            }
            products.append(product)
    except Exception as e:
        print("Warning: Could not read supplier products: {}".format(e))

    return products


def run_sourcing_scan(count: int = 30) -> bool:
    """Attempt to run source.py scan to generate fresh results."""
    source_script = Path(__file__).parent / "source.py"
    if not source_script.exists():
        print("Warning: source.py not found, using existing data only")
        return False

    print("Running sourcing scan for fresh results...")
    try:
        result = subprocess.run(
            [sys.executable, str(source_script), "scan", "--mode", "clearance",
             "--count", str(count)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(Path(__file__).parent.parent),
        )
        if result.returncode == 0:
            print("Sourcing scan completed successfully")
            return True
        else:
            print("Sourcing scan returned code {}: {}".format(
                result.returncode, result.stderr[:200] if result.stderr else "no stderr"))
            return False
    except subprocess.TimeoutExpired:
        print("Sourcing scan timed out after 180s, using existing data")
        return False
    except Exception as e:
        print("Sourcing scan failed: {}".format(e))
        return False


def get_recent_products(limit: int = 10) -> list[dict]:
    """Get the best recent products from all available sources."""
    # Primary: JSON result files
    products = gather_products_from_json(limit=limit * 3)

    # Secondary: supplier_products table
    if len(products) < limit:
        supplier_products = gather_products_from_supplier_db(limit=limit)
        seen_asins = {p["asin"] for p in products if p["asin"]}
        for sp in supplier_products:
            if sp["asin"] and sp["asin"] in seen_asins:
                continue
            products.append(sp)

    # Sort by ROI descending, then by BSR ascending
    def sort_key(p: dict) -> tuple:
        roi = p.get("roi") or 0
        bsr = p.get("bsr") or 999_999
        return (-roi, bsr)

    products.sort(key=sort_key)
    return products[:limit]


# ── Formatting ───────────────────────────────────────────────────────────────


def format_bsr(bsr: int | None) -> str:
    """Format BSR with commas or 'N/A'."""
    if bsr is None or bsr == 0:
        return "N/A"
    return "{:,}".format(bsr)


def format_price(price: float | None) -> str:
    """Format price or 'N/A'."""
    if price is None:
        return "N/A"
    return "${:.2f}".format(price)


def format_weekly_drop(products: list[dict]) -> str:
    """Format products into a Discord-ready weekly drop message."""
    lines = [
        "**WEEKLY PRODUCT DROP -- Monday Deals**\n",
        "Here are this week's top finds. ALWAYS verify with SellerAmp before buying!\n",
    ]

    for i, p in enumerate(products, 1):
        title = p["title"][:60]
        asin = p["asin"]
        roi = p["roi"]
        bsr = p["bsr"]
        buy_price = p["buy_price"]
        sell_price = p["sell_price"]
        retailer = p["retailer"]
        verdict = p.get("verdict", "")

        lines.append("**{}. {}**".format(i, title))
        if asin:
            lines.append("   ASIN: `{}`".format(asin))
        if retailer:
            lines.append("   Source: {}".format(retailer))

        price_line = "   "
        if buy_price is not None:
            price_line += "Buy: {} -> ".format(format_price(buy_price))
        if sell_price is not None:
            price_line += "Sell: {} | ".format(format_price(sell_price))
        if roi is not None:
            price_line += "ROI: {}% | ".format(roi)
        price_line += "BSR: {}".format(format_bsr(bsr))
        if verdict:
            price_line += " | {}".format(verdict)
        lines.append(price_line)
        lines.append("")

    lines.append("---")
    lines.append("**How to use this list:**")
    lines.append("1. Check each ASIN in SellerAmp")
    lines.append("2. Verify you're ungated (Seller Central -> Add a Product)")
    lines.append("3. Check Keepa chart for consistent sales")
    lines.append("4. Post your pick in your private channel for review")
    lines.append("\nGood luck this week!")

    return "\n".join(lines)


def format_dispatch_message(name: str, milestone: str, products: list[dict]) -> str:
    """Personalized sourcing dispatch for a stuck student."""
    intros = {
        "niche_selected": (
            "Hey {}! I noticed you've been working on finding your niche. "
            "Here are some product ideas across different categories to help spark ideas:"
        ).format(name),
        "product_selected": (
            "Hey {}! Finding the right product can be tough. "
            "Here are some pre-vetted options I found that might work for you:"
        ).format(name),
        "supplier_contacted": (
            "Hey {}! While you're working on supplier outreach, "
            "here are some additional products to add to your pipeline:"
        ).format(name),
    }

    intro = intros.get(milestone, "Hey {}! Here are some product ideas for you:".format(name))
    lines = [intro, ""]

    for i, p in enumerate(products, 1):
        title = p["title"][:55]
        roi = p.get("roi")
        asin = p.get("asin")
        retailer = p.get("retailer")

        detail = "**{}. {}**".format(i, title)
        if roi is not None:
            detail += " -- ROI: {}%".format(roi)
        if retailer:
            detail += " ({})".format(retailer)
        lines.append(detail)

        if asin:
            lines.append("   ASIN: `{}`".format(asin))
        if p.get("buy_price") is not None and p.get("sell_price") is not None:
            lines.append("   Buy: {} -> Sell: {} | BSR: {}".format(
                format_price(p["buy_price"]),
                format_price(p["sell_price"]),
                format_bsr(p.get("bsr")),
            ))
        lines.append("")

    lines.append("Want me to dig deeper into any of these? "
                 "Drop the ASIN in this channel and tag your coach!")

    return "\n".join(lines)


def generate_tip_drop() -> list[dict]:
    """Fallback: generate a tips-based drop when no products are available."""
    # Return empty -- caller will handle the no-products case
    return []


# ── Commands ─────────────────────────────────────────────────────────────────


def cmd_weekly_drop(args: argparse.Namespace) -> None:
    """Generate and post weekly sourcing drop."""
    channel_id = args.channel_id
    count = args.count
    dry_run = args.dry_run

    print("=== Weekly Sourcing Drop ===")
    print("Channel: {} | Count: {} | Dry run: {}".format(channel_id, count, dry_run))
    print()

    # Step 1: Optionally run a fresh sourcing scan
    if not args.skip_scan:
        run_sourcing_scan(count=count * 3)

    # Step 2: Gather and filter products
    products = get_recent_products(limit=count)

    if not products:
        print("No beginner-friendly products found in sourcing data.")
        print("Try running: python execution/source.py scan --mode clearance")
        return

    print("Found {} beginner-friendly products".format(len(products)))

    # Step 3: Format the drop message
    message = format_weekly_drop(products)

    # Step 4: Post or preview
    if dry_run:
        print("\n[DRY RUN] Would post to channel {}:\n".format(channel_id))
        print(message)
    else:
        print("Posting to Discord channel {}...".format(channel_id))
        success, status = send_channel_message(channel_id, message)
        if success:
            print("Posted successfully!")
        else:
            print("Failed to post (status: {})".format(status))

    # Step 5: Log the drop
    conn = get_db()
    ensure_drops_table(conn)
    conn.execute("""
        INSERT INTO sourcing_drops (drop_type, channel_id, product_count, products_json, status)
        VALUES ('weekly', ?, ?, ?, ?)
    """, (
        channel_id,
        len(products),
        json.dumps([p["asin"] for p in products if p["asin"]]),
        "dry_run" if dry_run else "sent",
    ))
    conn.commit()

    # Also log as engagement signal (student_id=0 for broadcast)
    now = datetime.utcnow()
    conn.execute("""
        INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
        VALUES (0, 'sourcing_drop', 'discord', ?, ?, ?, ?)
    """, (
        str(len(products)),
        now.strftime("%Y-%m-%d"),
        "Weekly drop: {} products to channel {}".format(len(products), channel_id),
        now.isoformat(),
    ))
    conn.commit()
    conn.close()

    print("\nDrop logged. {} products.".format(len(products)))


def cmd_dispatch_stuck(args: argparse.Namespace) -> None:
    """Find students stuck on product milestones and send them targeted results."""
    days_threshold = args.days
    dry_run = args.dry_run

    print("=== Dispatch Stuck Students ===")
    print("Threshold: {} days | Dry run: {}".format(days_threshold, dry_run))
    print()

    conn = get_db()
    ensure_drops_table(conn)

    # Find students stuck on product-related milestones
    stuck_milestones = ("niche_selected", "product_selected", "supplier_contacted")
    stuck_students = conn.execute("""
        SELECT s.id, s.name, s.discord_user_id, s.discord_channel_id, s.current_milestone,
               m.started_date
        FROM students s
        JOIN milestones m ON m.student_id = s.id AND m.milestone = s.current_milestone
        WHERE s.status IN ('active', 'at_risk')
        AND s.current_milestone IN (?, ?, ?)
        AND m.status = 'in_progress'
        AND julianday('now') - julianday(m.started_date) > ?
    """, (*stuck_milestones, days_threshold)).fetchall()

    if not stuck_students:
        print("No students stuck for >{}d on product milestones.".format(days_threshold))
        conn.close()
        return

    print("Found {} stuck students".format(len(stuck_students)))

    # Gather products once for all dispatches
    products = get_recent_products(limit=20)
    if not products:
        print("No products available for dispatch. Run sourcing first.")
        conn.close()
        return

    dispatched = 0
    skipped = 0

    for student in stuck_students:
        sid = student["id"]
        name = student["name"]
        channel_id = student["discord_channel_id"]
        milestone = student["current_milestone"]
        started = student["started_date"]

        # Check if we already dispatched in the last 7 days
        recent = conn.execute("""
            SELECT COUNT(*) as cnt FROM engagement_signals
            WHERE student_id = ? AND signal_type = 'sourcing_dispatch'
            AND date >= date('now', '-7 days')
        """, (sid,)).fetchone()["cnt"]

        if recent > 0:
            print("  SKIP {} -- already dispatched within 7 days".format(name))
            skipped += 1
            continue

        # Pick top 5 products for this student
        student_products = products[:5]

        # Format personalized message
        message = format_dispatch_message(name, milestone, student_products)

        days_stuck = (datetime.utcnow() - datetime.strptime(started, "%Y-%m-%d")).days if started else "?"

        if dry_run:
            print("  [DRY RUN] {} -- stuck {}d on '{}' (channel: {})".format(
                name, days_stuck, milestone, channel_id or "NONE"))
            print("  Would send {} products".format(len(student_products)))
            dispatched += 1
            continue

        if not channel_id:
            print("  SKIP {} -- no discord_channel_id set".format(name))
            skipped += 1
            continue

        print("  Dispatching to {} ({} products)...".format(name, len(student_products)))
        success, status = send_channel_message(channel_id, message)

        if success:
            # Log the dispatch as engagement signal
            now_dt = datetime.utcnow()
            conn.execute("""
                INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
                VALUES (?, 'sourcing_dispatch', 'discord', ?, ?, ?, ?)
            """, (
                sid,
                str(len(student_products)),
                now_dt.strftime("%Y-%m-%d"),
                "Dispatched {} products (stuck {}d on {})".format(
                    len(student_products), days_stuck, milestone),
                now_dt.isoformat(),
            ))
            conn.commit()

            # Log in sourcing_drops table
            conn.execute("""
                INSERT INTO sourcing_drops (drop_type, channel_id, student_id, product_count, products_json)
                VALUES ('dispatch', ?, ?, ?, ?)
            """, (
                channel_id,
                sid,
                len(student_products),
                json.dumps([p["asin"] for p in student_products if p["asin"]]),
            ))
            conn.commit()

            dispatched += 1
            print("    Sent successfully!")
        else:
            print("    Failed (status: {})".format(status))
            skipped += 1

    conn.close()
    print("\nDone. Dispatched: {} | Skipped: {}".format(dispatched, skipped))


def cmd_review_product(args: argparse.Namespace) -> None:
    """Quick product viability check for a given ASIN."""
    asin = args.asin.strip().upper()

    print("\n=== Product Review: {} ===\n".format(asin))

    result = None

    # Check JSON result files
    for pattern in ["*_source_results.json", "*-deals.json", "*-results.json", "*-multi-results.json"]:
        for jf in sorted(SOURCING_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                with open(jf) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            for item in items:
                if (item.get("asin") or "").upper() == asin:
                    result = extract_product_fields(item)
                    break
            if result:
                break
        if result:
            break

    # Check supplier_products table
    if result is None and PRICE_TRACKER_DB.exists():
        try:
            sconn = sqlite3.connect(str(PRICE_TRACKER_DB))
            sconn.row_factory = sqlite3.Row
            row = sconn.execute(
                "SELECT * FROM supplier_products WHERE asin = ? LIMIT 1", (asin,)
            ).fetchone()
            sconn.close()
            if row:
                result = {
                    "title": row["product_name"] or "Unknown",
                    "asin": asin,
                    "retailer": "Wholesale",
                    "buy_price": row["wholesale_cost"],
                    "sell_price": None,
                    "roi": round(float(row["estimated_roi"]), 1) if row["estimated_roi"] else None,
                    "profit": None,
                    "bsr": None,
                    "category": "",
                    "brand": "",
                    "buy_url": "",
                    "amazon_url": "https://www.amazon.com/dp/{}".format(asin),
                    "auto_ungated": False,
                    "verdict": "",
                }
        except Exception:
            pass

    if result is None:
        print("  No data found for ASIN {} in sourcing history.".format(asin))
        print("  Run: python execution/source.py asin --asin {}".format(asin))
        return

    # Display
    print("  Title:    {}".format(result["title"][:70]))
    print("  ASIN:     {}".format(result["asin"]))
    if result["retailer"]:
        print("  Source:   {}".format(result["retailer"]))
    print("  Buy:      {}".format(format_price(result["buy_price"])))
    print("  Sell:     {}".format(format_price(result["sell_price"])))
    print("  ROI:      {}%".format(result["roi"]) if result["roi"] is not None else "  ROI:      N/A")
    if result["profit"] is not None:
        print("  Profit:   {}".format(format_price(result["profit"])))
    print("  BSR:      {}".format(format_bsr(result["bsr"])))
    if result["category"]:
        print("  Category: {}".format(result["category"]))
    if result["brand"]:
        print("  Brand:    {}".format(result["brand"]))
    if result["verdict"]:
        print("  Verdict:  {}".format(result["verdict"]))

    # Flags
    print()
    flags = []
    warnings = []

    if result["roi"] is not None:
        if result["roi"] < 20:
            flags.append("ROI below 20% -- likely not profitable after fees")
        elif result["roi"] < MIN_ROI:
            warnings.append("ROI below 30% -- thin margin for beginners")

    if result["bsr"] is not None and result["bsr"] > 0:
        if result["bsr"] > 200_000:
            flags.append("BSR above 200K -- very slow seller")
        elif result["bsr"] > MAX_BSR:
            warnings.append("BSR above 100K -- slower mover")

    if result["sell_price"] is not None:
        if result["sell_price"] > MAX_PRICE:
            warnings.append("Sell price above $75 -- higher capital needed")
        elif result["sell_price"] < MIN_PRICE:
            warnings.append("Sell price below $15 -- low margin after fees")

    category = (result.get("category") or "").lower()
    for avoid in AVOID_CATEGORIES:
        if avoid in category:
            flags.append("Category '{}' may have gating or restrictions".format(result["category"]))
            break

    if flags:
        for f in flags:
            print("  [ISSUE] {}".format(f))
        print("\n  VERDICT: PROCEED WITH CAUTION")
    elif warnings:
        for w in warnings:
            print("  [NOTE] {}".format(w))
        print("\n  VERDICT: DECENT -- verify gating and Keepa history")
    else:
        print("  VERDICT: LOOKS GOOD -- verify gating status in Seller Central")

    print("  Amazon: https://www.amazon.com/dp/{}".format(asin))


def cmd_status(args: argparse.Namespace) -> None:
    """Show recent sourcing drops and dispatches."""
    conn = get_db()
    ensure_drops_table(conn)

    print("=== Sourcing Drop Status ===\n")

    # Recent weekly drops
    weekly = conn.execute("""
        SELECT * FROM sourcing_drops
        WHERE drop_type = 'weekly'
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()

    print("Recent Weekly Drops:")
    if weekly:
        for row in weekly:
            print("  {} | {} products | channel {} | {}".format(
                row["created_at"], row["product_count"],
                row["channel_id"], row["status"]))
    else:
        print("  No weekly drops yet.")

    print()

    # Recent dispatches
    dispatches = conn.execute("""
        SELECT sd.*, s.name as student_name
        FROM sourcing_drops sd
        LEFT JOIN students s ON s.id = sd.student_id
        WHERE sd.drop_type = 'dispatch'
        ORDER BY sd.created_at DESC LIMIT 10
    """).fetchall()

    print("Recent Student Dispatches:")
    if dispatches:
        for row in dispatches:
            name = row["student_name"] or "ID:{}".format(row["student_id"])
            print("  {} | {} | {} products | {}".format(
                row["created_at"], name,
                row["product_count"], row["status"]))
    else:
        print("  No dispatches yet.")

    print()

    # Dispatch signals from engagement_signals
    signals = conn.execute("""
        SELECT es.date, es.notes, s.name
        FROM engagement_signals es
        LEFT JOIN students s ON s.id = es.student_id
        WHERE es.signal_type = 'sourcing_dispatch'
        ORDER BY es.date DESC LIMIT 5
    """).fetchall()

    print("Recent Dispatch Signals:")
    if signals:
        for row in signals:
            name = row["name"] or "broadcast"
            print("  {} | {} | {}".format(row["date"], name, row["notes"]))
    else:
        print("  No dispatch signals logged.")

    # Summary stats
    total_weekly = conn.execute(
        "SELECT COUNT(*) FROM sourcing_drops WHERE drop_type = 'weekly'"
    ).fetchone()[0]
    total_dispatch = conn.execute(
        "SELECT COUNT(*) FROM sourcing_drops WHERE drop_type = 'dispatch'"
    ).fetchone()[0]
    total_products = conn.execute(
        "SELECT COALESCE(SUM(product_count), 0) FROM sourcing_drops"
    ).fetchone()[0]

    print("\n--- Totals ---")
    print("  Weekly drops: {}".format(total_weekly))
    print("  Student dispatches: {}".format(total_dispatch))
    print("  Total products shared: {}".format(total_products))

    # Products available
    products = get_recent_products(limit=100)
    print("  Products in sourcing pipeline: {}".format(len(products)))

    conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sourcing_drop.py",
        description="Weekly sourcing drops and stuck-student dispatch for Amazon FBA coaching.",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # weekly-drop
    wd = sub.add_parser("weekly-drop", help="Generate and post weekly sourcing drop")
    wd.add_argument("--channel-id", required=True, help="Discord channel ID for the drop")
    wd.add_argument("--count", type=int, default=10, help="Number of products (default: 10)")
    wd.add_argument("--dry-run", action="store_true", help="Preview without posting")
    wd.add_argument("--skip-scan", action="store_true", help="Skip running source.py scan")

    # dispatch-stuck
    ds = sub.add_parser("dispatch-stuck", help="Send products to stuck students")
    ds.add_argument("--days", type=int, default=14, help="Days stuck threshold (default: 14)")
    ds.add_argument("--dry-run", action="store_true", help="Preview without sending")

    # review-product
    rp = sub.add_parser("review-product", help="Quick product viability check")
    rp.add_argument("--asin", required=True, help="Amazon ASIN to review")

    # status
    sub.add_parser("status", help="Show recent drops and dispatch history")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "weekly-drop": cmd_weekly_drop,
        "dispatch-stuck": cmd_dispatch_stuck,
        "review-product": cmd_review_product,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
