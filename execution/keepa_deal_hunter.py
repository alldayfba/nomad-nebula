#!/usr/bin/env python3
"""
Script: keepa_deal_hunter.py
Purpose: Proactive deal discovery tool that polls Keepa API on a schedule to find
         profitable Amazon FBA opportunities autonomously. Surfaces deals via Telegram
         before any manual action is needed.

Cron (every 4 hours):
    0 */4 * * * .venv/bin/python execution/keepa_deal_hunter.py scan

CLI:
    python execution/keepa_deal_hunter.py watchlist add --asin B08XYZ1234 --name "Widget Pro"
    python execution/keepa_deal_hunter.py watchlist list
    python execution/keepa_deal_hunter.py watchlist remove --asin B08XYZ1234
    python execution/keepa_deal_hunter.py watchlist import --results .tmp/sourcing/results.json
    python execution/keepa_deal_hunter.py scan [--min-score 40] [--alert]
    python execution/keepa_deal_hunter.py deals [--days 7] [--min-score 50]
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "price_tracker.db"

KEEPA_ENDPOINT = "https://api.keepa.com/product"
KEEPA_RATE_LIMIT = 1.1  # seconds between requests (max 1/sec)
KEEPA_BATCH_SIZE = 20   # ASINs per request (conservative; API allows 100)

# Deal type labels
DEAL_PRICE_DROP = "price_drop"
DEAL_BSR_SPIKE = "bsr_spike"
DEAL_AMAZON_EXIT = "amazon_exit"
DEAL_SELLER_DROP = "seller_drop"

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deal_hunter_watchlist (
    asin TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    added_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS deal_hunter_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    name TEXT,
    deal_type TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    change_percent REAL,
    detected_at TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    deal_score REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_deals_detected ON deal_hunter_deals(detected_at);
CREATE INDEX IF NOT EXISTS idx_deals_score ON deal_hunter_deals(deal_score);
CREATE INDEX IF NOT EXISTS idx_deals_ack ON deal_hunter_deals(acknowledged);
"""


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    """Return a WAL-mode SQLite connection with deal hunter tables created."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Keepa API ─────────────────────────────────────────────────────────────────

def _last_valid(arr):
    """Return the last non-negative value from a flat Keepa CSV array (value at odd indices)."""
    if not arr:
        return None
    for i in range(len(arr) - 1, 0, -2):
        if arr[i] >= 0:
            return arr[i] / 100.0  # Keepa prices are in cents
    return None


def _average_valid(arr, n_pairs=60):
    """Average last n_pairs values (even=timestamp, odd=value) ignoring negatives."""
    if not arr:
        return None
    values = []
    pairs = list(zip(arr[::2], arr[1::2]))
    for _, val in pairs[-n_pairs:]:
        if val >= 0:
            values.append(val / 100.0)
    return sum(values) / len(values) if values else None


def _last_valid_raw(arr):
    """Like _last_valid but without /100 conversion (for BSR, counts)."""
    if not arr:
        return None
    for i in range(len(arr) - 1, 0, -2):
        if arr[i] >= 0:
            return arr[i]
    return None


def _average_valid_raw(arr, n_pairs=60):
    """Average last n_pairs values without /100 conversion."""
    if not arr:
        return None
    values = []
    pairs = list(zip(arr[::2], arr[1::2]))
    for _, val in pairs[-n_pairs:]:
        if val >= 0:
            values.append(val)
    return sum(values) / len(values) if values else None


def fetch_keepa_batch(asins):
    """Fetch Keepa data for up to KEEPA_BATCH_SIZE ASINs.

    Returns list of product dicts from Keepa, or [] on error.
    """
    if not KEEPA_API_KEY:
        print("[keepa] KEEPA_API_KEY not set in .env", file=sys.stderr)
        return []
    try:
        import requests
    except ImportError:
        print("[keepa] requests library not installed", file=sys.stderr)
        return []

    asin_str = ",".join(asins)
    params = {
        "key": KEEPA_API_KEY,
        "domain": "1",
        "asin": asin_str,
        "stats": "180",
        "history": "1",
    }
    try:
        resp = requests.get(KEEPA_ENDPOINT, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("products", [])
    except Exception as e:
        print(f"[keepa] API error: {e}", file=sys.stderr)
        return []


def parse_keepa_product(product):
    """Extract current metrics and 30-day averages from a Keepa product dict.

    v3.0: Uses correct CSV indices via keepa_client constants.
    Index 34 = FBA seller count (NOT 11 which is total new offers).
    Index 35 = FBM seller count.
    """
    csv = product.get("csv", [])
    stats = product.get("stats", {}) or {}

    def _csv(idx):
        return csv[idx] if csv and idx < len(csv) else None

    # Current values
    amazon_price_cur = _last_valid(_csv(0))         # index 0 = Amazon price
    new3p_price_cur = _last_valid(_csv(1))           # index 1 = new 3P price
    bsr_cur = _last_valid_raw(_csv(3))               # index 3 = sales rank
    new_offer_count_cur = _last_valid_raw(_csv(11))  # index 11 = total new offer count
    buy_box_price_cur = _last_valid(_csv(18))        # index 18 = buy box price

    # v3.0: Use correct FBA seller count index (34, not 11)
    fba_seller_count_cur = _last_valid_raw(_csv(34))  # index 34 = FBA sellers
    fbm_seller_count_cur = _last_valid_raw(_csv(35))  # index 35 = FBM sellers
    fba_seller_count_avg = _average_valid_raw(_csv(34), 60)

    # 30-day averages (use ~60 pairs for ~30 days of data at typical Keepa granularity)
    amazon_price_avg = _average_valid(_csv(0), 60)
    bsr_avg = _average_valid_raw(_csv(3), 60)
    new_offer_count_avg = _average_valid_raw(_csv(11), 60)

    # Amazon on listing: was it selling before? Is it selling now?
    amazon_was_selling = False
    amazon_now_selling = amazon_price_cur is not None and amazon_price_cur > 0
    if _csv(0):
        arr = _csv(0)
        pairs = list(zip(arr[::2], arr[1::2]))
        recent = pairs[-30:] if len(pairs) >= 30 else pairs
        amazon_was_selling = any(v >= 0 for _, v in recent[:-5]) if len(recent) > 5 else False

    return {
        "asin": product.get("asin", ""),
        "title": product.get("title", ""),
        "category": (product.get("categoryTree") or [{}])[-1].get("name", ""),
        "amazon_price_cur": amazon_price_cur,
        "amazon_price_avg": amazon_price_avg,
        "new3p_price_cur": new3p_price_cur,
        "buy_box_price_cur": buy_box_price_cur,
        "bsr_cur": bsr_cur,
        "bsr_avg": bsr_avg,
        "new_offer_count_cur": new_offer_count_cur,
        "new_offer_count_avg": new_offer_count_avg,
        # v3.0: FBA-specific seller counts
        "fba_seller_count_cur": fba_seller_count_cur,
        "fbm_seller_count_cur": fbm_seller_count_cur,
        "fba_seller_count_avg": fba_seller_count_avg,
        "amazon_was_selling": amazon_was_selling,
        "amazon_now_selling": amazon_now_selling,
    }


# ── Deal Detection ─────────────────────────────────────────────────────────────

def detect_deals(parsed, min_score=40):
    """Run all deal detectors against a parsed Keepa product.

    Returns list of deal dicts (may be empty). Each dict:
        asin, name, deal_type, old_value, new_value, change_percent, deal_score
    """
    deals = []
    asin = parsed["asin"]
    name = (parsed["title"] or "")[:80]

    # ── 1. Price drop >15% from 30-day average ────────────────────────────────
    price_cur = parsed["amazon_price_cur"] or parsed["buy_box_price_cur"]
    price_avg = parsed["amazon_price_avg"]
    if price_cur and price_avg and price_avg > 0:
        drop_pct = (price_avg - price_cur) / price_avg * 100
        if drop_pct >= 15:
            score = min(30, drop_pct)  # up to 30 pts for price drop
            # Bonus for BSR improvement (people actually buying at this price)
            bsr_bonus = _bsr_improvement_score(parsed)
            seller_bonus = _seller_reduction_score(parsed)
            amz_bonus = _amazon_exit_score(parsed)
            total = min(100, score + bsr_bonus + seller_bonus + amz_bonus)
            if total >= min_score:
                deals.append({
                    "asin": asin, "name": name,
                    "deal_type": DEAL_PRICE_DROP,
                    "old_value": round(price_avg, 2),
                    "new_value": round(price_cur, 2),
                    "change_percent": round(drop_pct, 1),
                    "deal_score": round(total, 1),
                })

    # ── 2. BSR drop >40% (sudden sales spike) ────────────────────────────────
    bsr_cur = parsed["bsr_cur"]
    bsr_avg = parsed["bsr_avg"]
    if bsr_cur and bsr_avg and bsr_avg > 0:
        bsr_improvement_pct = (bsr_avg - bsr_cur) / bsr_avg * 100
        if bsr_improvement_pct >= 40:
            score = min(30, bsr_improvement_pct * 0.5)
            price_bonus = min(15, _price_drop_score(parsed) * 0.5)
            seller_bonus = _seller_reduction_score(parsed)
            amz_bonus = _amazon_exit_score(parsed)
            total = min(100, score + price_bonus + seller_bonus + amz_bonus)
            if total >= min_score:
                deals.append({
                    "asin": asin, "name": name,
                    "deal_type": DEAL_BSR_SPIKE,
                    "old_value": round(bsr_avg, 0),
                    "new_value": round(bsr_cur, 0),
                    "change_percent": round(bsr_improvement_pct, 1),
                    "deal_score": round(total, 1),
                })

    # ── 3. Amazon leaving the listing ─────────────────────────────────────────
    if parsed["amazon_was_selling"] and not parsed["amazon_now_selling"]:
        score = 20  # Amazon exit bonus
        bsr_bonus = _bsr_improvement_score(parsed)
        price_bonus = _price_drop_score(parsed)
        seller_bonus = _seller_reduction_score(parsed)
        total = min(100, score + bsr_bonus + price_bonus + seller_bonus)
        if total >= min_score:
            deals.append({
                "asin": asin, "name": name,
                "deal_type": DEAL_AMAZON_EXIT,
                "old_value": 1.0, "new_value": 0.0,
                "change_percent": 100.0,
                "deal_score": round(total, 1),
            })

    # ── 4. FBA seller count drop (v3.0: prefer FBA-specific counts) ────────
    sellers_cur = parsed.get("fba_seller_count_cur") or parsed["new_offer_count_cur"]
    sellers_avg = parsed.get("fba_seller_count_avg") or parsed["new_offer_count_avg"]
    if sellers_cur is not None and sellers_avg and sellers_avg > 1:
        seller_drop_pct = (sellers_avg - sellers_cur) / sellers_avg * 100
        if seller_drop_pct >= 30:
            score = min(20, seller_drop_pct * 0.4)
            bsr_bonus = _bsr_improvement_score(parsed)
            price_bonus = _price_drop_score(parsed)
            amz_bonus = _amazon_exit_score(parsed)
            total = min(100, score + bsr_bonus + price_bonus + amz_bonus)
            if total >= min_score:
                deals.append({
                    "asin": asin, "name": name,
                    "deal_type": DEAL_SELLER_DROP,
                    "old_value": round(sellers_avg, 1),
                    "new_value": float(sellers_cur),
                    "change_percent": round(seller_drop_pct, 1),
                    "deal_score": round(total, 1),
                })

    # Deduplicate: keep highest-scoring deal per ASIN if same type appears twice
    seen = {}
    for d in deals:
        key = d["deal_type"]
        if key not in seen or d["deal_score"] > seen[key]["deal_score"]:
            seen[key] = d
    return list(seen.values())


def _price_drop_score(parsed):
    p_cur = parsed["amazon_price_cur"] or parsed["buy_box_price_cur"]
    p_avg = parsed["amazon_price_avg"]
    if p_cur and p_avg and p_avg > 0:
        return min(30, (p_avg - p_cur) / p_avg * 100)
    return 0


def _bsr_improvement_score(parsed):
    b_cur, b_avg = parsed["bsr_cur"], parsed["bsr_avg"]
    if b_cur and b_avg and b_avg > 0:
        return min(30, (b_avg - b_cur) / b_avg * 100 * 0.5)
    return 0


def _seller_reduction_score(parsed):
    s_cur = parsed.get("fba_seller_count_cur") or parsed["new_offer_count_cur"]
    s_avg = parsed.get("fba_seller_count_avg") or parsed["new_offer_count_avg"]
    if s_cur is not None and s_avg and s_avg > 1:
        return min(20, (s_avg - s_cur) / s_avg * 100 * 0.4)
    return 0


def _amazon_exit_score(parsed):
    if parsed["amazon_was_selling"] and not parsed["amazon_now_selling"]:
        return 20
    return 0


# ── Telegram Alert ────────────────────────────────────────────────────────────

def _send_telegram_alert(message):
    """Delegate to sourcing_alerts.send_telegram_alert."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from execution.sourcing_alerts import send_telegram_alert
        return send_telegram_alert(message)
    except Exception as e:
        print(f"[alert] Telegram send failed: {e}", file=sys.stderr)
        return False


def format_deal_alert(deals):
    """Format a list of deal dicts into a Telegram message string."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"DEAL HUNTER ALERT -- {now}", "=" * 34, ""]
    type_labels = {
        DEAL_PRICE_DROP: "Price Drop",
        DEAL_BSR_SPIKE: "Sales Spike (BSR Drop)",
        DEAL_AMAZON_EXIT: "Amazon Left Listing",
        DEAL_SELLER_DROP: "Seller Count Drop",
    }
    for d in sorted(deals, key=lambda x: x["deal_score"], reverse=True):
        label = type_labels.get(d["deal_type"], d["deal_type"])
        lines.append(f"[Score: {d['deal_score']:.0f}/100] {label}")
        lines.append(f"  {d['name'][:60]}")
        lines.append(f"  ASIN: {d['asin']}")
        lines.append(f"  Change: {d['change_percent']:+.1f}%  ({d['old_value']} -> {d['new_value']})")
        lines.append(f"  https://amazon.com/dp/{d['asin']}")
        lines.append("")
    lines.append(f"Total deals found: {len(deals)}")
    return "\n".join(lines)


# ── Subcommand: watchlist ─────────────────────────────────────────────────────

def cmd_watchlist(args):
    conn = get_db()
    now = datetime.utcnow().isoformat()

    if args.watchlist_cmd == "add":
        if not args.asin:
            print("ERROR: --asin required for watchlist add", file=sys.stderr)
            sys.exit(1)
        conn.execute(
            "INSERT OR REPLACE INTO deal_hunter_watchlist (asin, name, category, added_at, active) "
            "VALUES (?, ?, ?, ?, 1)",
            (args.asin.upper(), args.name or "", args.category or "", now),
        )
        conn.commit()
        print(json.dumps({"status": "added", "asin": args.asin.upper()}))

    elif args.watchlist_cmd == "remove":
        if not args.asin:
            print("ERROR: --asin required for watchlist remove", file=sys.stderr)
            sys.exit(1)
        conn.execute(
            "UPDATE deal_hunter_watchlist SET active=0 WHERE asin=?",
            (args.asin.upper(),),
        )
        conn.commit()
        print(json.dumps({"status": "removed", "asin": args.asin.upper()}))

    elif args.watchlist_cmd == "list":
        rows = conn.execute(
            "SELECT asin, name, category, added_at FROM deal_hunter_watchlist WHERE active=1 ORDER BY added_at DESC"
        ).fetchall()
        items = [dict(r) for r in rows]
        print(json.dumps({"watchlist": items, "count": len(items)}, indent=2))

    elif args.watchlist_cmd == "import":
        if not args.results:
            print("ERROR: --results required for watchlist import", file=sys.stderr)
            sys.exit(1)
        results_path = Path(args.results)
        if not results_path.exists():
            print(f"ERROR: File not found: {results_path}", file=sys.stderr)
            sys.exit(1)
        with open(results_path) as f:
            data = json.load(f)
        products = data.get("products", [])
        added = 0
        for p in products:
            verdict = (p.get("profitability") or {}).get("verdict", "")
            if verdict != "BUY":
                continue
            amz = p.get("amazon") or {}
            asin = amz.get("asin", "")
            if not asin:
                continue
            name = p.get("name", "")[:120]
            category = amz.get("category", "")
            conn.execute(
                "INSERT OR IGNORE INTO deal_hunter_watchlist (asin, name, category, added_at, active) "
                "VALUES (?, ?, ?, ?, 1)",
                (asin.upper(), name, category, now),
            )
            added += 1
        conn.commit()
        print(json.dumps({"status": "imported", "added": added}))

    else:
        print(f"ERROR: Unknown watchlist subcommand: {args.watchlist_cmd}", file=sys.stderr)
        sys.exit(1)

    conn.close()


# ── Subcommand: scan ──────────────────────────────────────────────────────────

def cmd_scan(args):
    if not KEEPA_API_KEY:
        print("[scan] ERROR: KEEPA_API_KEY not configured in .env", file=sys.stderr)
        sys.exit(1)

    min_score = args.min_score if args.min_score is not None else 40
    conn = get_db()
    now = datetime.utcnow().isoformat()

    # Load active watchlist
    rows = conn.execute(
        "SELECT asin, name FROM deal_hunter_watchlist WHERE active=1"
    ).fetchall()
    asins = [(r["asin"], r["name"]) for r in rows]

    if not asins:
        print("[scan] Watchlist is empty. Add ASINs with: watchlist add --asin ...", file=sys.stderr)
        print(json.dumps({"deals_found": 0, "asins_scanned": 0}))
        conn.close()
        return

    print(f"[scan] Scanning {len(asins)} ASINs from watchlist...", file=sys.stderr)

    # Batch ASINs
    batches = [asins[i:i + KEEPA_BATCH_SIZE] for i in range(0, len(asins), KEEPA_BATCH_SIZE)]
    all_deals = []
    total_scanned = 0

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            print(f"[scan] Rate limiting — sleeping {KEEPA_RATE_LIMIT}s...", file=sys.stderr)
            time.sleep(KEEPA_RATE_LIMIT)

        batch_asins = [a for a, _ in batch]
        watchlist_names = {a: n for a, n in batch}

        print(f"[scan] Batch {batch_idx + 1}/{len(batches)}: {batch_asins}", file=sys.stderr)
        products = fetch_keepa_batch(batch_asins)
        total_scanned += len(batch_asins)

        for product in products:
            parsed = parse_keepa_product(product)
            asin = parsed["asin"]
            if not parsed.get("title"):
                parsed["title"] = watchlist_names.get(asin, asin)

            deals = detect_deals(parsed, min_score=min_score)
            for deal in deals:
                deal["name"] = deal["name"] or watchlist_names.get(asin, asin)
                conn.execute(
                    "INSERT INTO deal_hunter_deals "
                    "(asin, name, deal_type, old_value, new_value, change_percent, detected_at, acknowledged, deal_score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (deal["asin"], deal["name"], deal["deal_type"],
                     deal["old_value"], deal["new_value"], deal["change_percent"],
                     now, deal["deal_score"]),
                )
                all_deals.append(deal)

    conn.commit()
    conn.close()

    print(f"[scan] Done. {len(all_deals)} deal(s) found across {total_scanned} ASINs.", file=sys.stderr)

    if all_deals and args.alert:
        msg = format_deal_alert(all_deals)
        sent = _send_telegram_alert(msg)
        print(f"[scan] Telegram alert {'sent' if sent else 'FAILED'}.", file=sys.stderr)

    result = {
        "deals_found": len(all_deals),
        "asins_scanned": total_scanned,
        "deals": all_deals,
    }
    print(json.dumps(result, indent=2))


# ── Subcommand: deals ─────────────────────────────────────────────────────────

def cmd_deals(args):
    conn = get_db()
    days = args.days if args.days is not None else 7
    min_score = args.min_score if args.min_score is not None else 0
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    rows = conn.execute(
        "SELECT id, asin, name, deal_type, old_value, new_value, change_percent, "
        "detected_at, acknowledged, deal_score "
        "FROM deal_hunter_deals "
        "WHERE detected_at >= ? AND deal_score >= ? "
        "ORDER BY deal_score DESC, detected_at DESC",
        (since, min_score),
    ).fetchall()

    deals = [dict(r) for r in rows]
    conn.close()
    print(json.dumps({"deals": deals, "count": len(deals), "days": days}, indent=2))


# ── CLI Parser ────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Keepa Deal Hunter — proactive FBA deal discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # watchlist
    wl = sub.add_parser("watchlist", help="Manage ASIN watchlist")
    wl_sub = wl.add_subparsers(dest="watchlist_cmd", required=True)

    wl_add = wl_sub.add_parser("add", help="Add ASIN to watchlist")
    wl_add.add_argument("--asin", required=True, help="Amazon ASIN (10 chars)")
    wl_add.add_argument("--name", default="", help="Product name (optional)")
    wl_add.add_argument("--category", default="", help="Category (optional)")

    wl_rm = wl_sub.add_parser("remove", help="Remove ASIN from watchlist")
    wl_rm.add_argument("--asin", required=True, help="Amazon ASIN to deactivate")

    wl_sub.add_parser("list", help="List active watchlist ASINs")

    wl_imp = wl_sub.add_parser("import", help="Import BUY products from results JSON")
    wl_imp.add_argument("--results", required=True, help="Path to sourcing results JSON")

    # scan
    sc = sub.add_parser("scan", help="Poll Keepa and detect deals")
    sc.add_argument("--min-score", type=float, default=40, help="Minimum deal score 0-100 (default: 40)")
    sc.add_argument("--alert", action="store_true", help="Send Telegram alert if deals found")

    # deals
    dv = sub.add_parser("deals", help="View recent deals from database")
    dv.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    dv.add_argument("--min-score", type=float, default=0, help="Filter by minimum deal score")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "watchlist":
        cmd_watchlist(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "deals":
        cmd_deals(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
