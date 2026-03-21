#!/usr/bin/env python3
"""
Script: inventory_tracker.py
Purpose: Purchase/inventory/P&L tracking system for FBA sourcing.
         After the sourcing pipeline identifies BUY products, track what was
         actually purchased, at what cost, how many units, when it sold, and
         realized profit vs. estimated profit.
Inputs:  CLI subcommands or imported functions
Outputs: Inventory lists, P&L reports, hit-rate analysis, dashboard (stdout JSON or return values)

CLI:
    python execution/inventory_tracker.py buy --asin B08XYZ --name "Widget" --cost 12.99 --qty 10 --retailer Walmart
    python execution/inventory_tracker.py ship --id 1
    python execution/inventory_tracker.py sold --id 1 --units 3 --price 29.99 --fees 8.50
    python execution/inventory_tracker.py inventory [--status purchased|shipped_to_fba|live]
    python execution/inventory_tracker.py pnl [--days 30]
    python execution/inventory_tracker.py hit-rate [--days 90]
    python execution/inventory_tracker.py import-buys --results path/to/results.json
    python execution/inventory_tracker.py dashboard
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "sourcing" / "price_tracker.db"

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    name TEXT,
    retailer TEXT,
    buy_cost REAL NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    total_investment REAL NOT NULL,
    estimated_sell_price REAL,
    estimated_roi REAL,
    estimated_profit_per_unit REAL,
    gift_card_discount REAL DEFAULT 0,
    cashback_percent REAL DEFAULT 0,
    purchase_date TEXT NOT NULL,
    shipped_to_fba_date TEXT,
    status TEXT DEFAULT 'purchased',
    notes TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL,
    asin TEXT NOT NULL,
    units_sold INTEGER NOT NULL DEFAULT 1,
    sell_price REAL NOT NULL,
    amazon_fees REAL,
    actual_profit REAL,
    sale_date TEXT NOT NULL,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id)
);

CREATE INDEX IF NOT EXISTS idx_purchases_asin ON purchases(asin);
CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status);
CREATE INDEX IF NOT EXISTS idx_sales_asin ON sales(asin);
"""

VALID_STATUSES = ("purchased", "shipped_to_fba", "live", "sold", "closed")


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Core Functions ───────────────────────────────────────────────────────────

def record_purchase(asin, name, retailer, buy_cost, quantity,
                    estimated_sell_price=None, estimated_roi=None,
                    estimated_profit_per_unit=None, gift_card_discount=0,
                    cashback_percent=0, notes=None, source_url=None,
                    purchase_date=None):
    """Insert a new purchase record.

    Returns the new purchase dict.
    """
    if purchase_date is None:
        purchase_date = datetime.utcnow().strftime("%Y-%m-%d")
    total_investment = round(buy_cost * quantity, 2)

    conn = get_db()
    try:
        cursor = conn.execute("""
            INSERT INTO purchases
                (asin, name, retailer, buy_cost, quantity, total_investment,
                 estimated_sell_price, estimated_roi, estimated_profit_per_unit,
                 gift_card_discount, cashback_percent, purchase_date, status,
                 notes, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'purchased', ?, ?)
        """, (asin, name, retailer, buy_cost, quantity, total_investment,
              estimated_sell_price, estimated_roi, estimated_profit_per_unit,
              gift_card_discount, cashback_percent, purchase_date,
              notes, source_url))
        purchase_id = cursor.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def mark_shipped(purchase_id):
    """Update status to shipped_to_fba and set shipped_to_fba_date.

    Returns the updated purchase dict or None if not found.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db()
    try:
        conn.execute("""
            UPDATE purchases
            SET status = 'shipped_to_fba', shipped_to_fba_date = ?
            WHERE id = ?
        """, (now, purchase_id))
        conn.commit()

        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def mark_live(purchase_id):
    """Update status to live (product is active on Amazon).

    Returns the updated purchase dict or None if not found.
    """
    conn = get_db()
    try:
        conn.execute("""
            UPDATE purchases SET status = 'live' WHERE id = ?
        """, (purchase_id,))
        conn.commit()

        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def record_sale(purchase_id, units_sold, sell_price, amazon_fees=None):
    """Record a sale against a purchase.

    Calculates actual_profit per unit, inserts into sales table.
    If all units are sold, updates purchase status to 'sold'.

    Returns the new sale dict.
    """
    conn = get_db()
    try:
        # Get the purchase to calculate profit
        purchase = conn.execute(
            "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
        ).fetchone()
        if purchase is None:
            raise ValueError(f"Purchase ID {purchase_id} not found")

        buy_cost = purchase["buy_cost"]
        fees = amazon_fees if amazon_fees is not None else 0.0
        actual_profit = round((sell_price - buy_cost - fees) * units_sold, 2)
        sale_date = datetime.utcnow().strftime("%Y-%m-%d")

        cursor = conn.execute("""
            INSERT INTO sales (purchase_id, asin, units_sold, sell_price,
                               amazon_fees, actual_profit, sale_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (purchase_id, purchase["asin"], units_sold, sell_price,
              fees, actual_profit, sale_date))
        sale_id = cursor.lastrowid

        # Check total units sold vs purchased
        total_sold_row = conn.execute("""
            SELECT COALESCE(SUM(units_sold), 0) AS total_sold
            FROM sales WHERE purchase_id = ?
        """, (purchase_id,)).fetchone()
        total_sold = total_sold_row["total_sold"]

        if total_sold >= purchase["quantity"]:
            conn.execute(
                "UPDATE purchases SET status = 'sold' WHERE id = ?",
                (purchase_id,)
            )

        conn.commit()

        row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_inventory(status=None):
    """List current inventory, optionally filtered by status.

    Returns list of purchase dicts with additional fields:
        units_sold, units_remaining, total_profit_so_far
    """
    conn = get_db()
    try:
        if status:
            rows = conn.execute("""
                SELECT p.*,
                    COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_sold,
                    p.quantity - COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_remaining,
                    COALESCE((SELECT SUM(s.actual_profit) FROM sales s WHERE s.purchase_id = p.id), 0) AS total_profit_so_far
                FROM purchases p
                WHERE p.status = ?
                ORDER BY p.purchase_date DESC
            """, (status,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT p.*,
                    COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_sold,
                    p.quantity - COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_remaining,
                    COALESCE((SELECT SUM(s.actual_profit) FROM sales s WHERE s.purchase_id = p.id), 0) AS total_profit_so_far
                FROM purchases p
                ORDER BY p.purchase_date DESC
            """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pnl_report(days=30):
    """Aggregate P&L report for a given period.

    Returns dict with totals, ROI, sell-through rate, top performers,
    slow movers, and estimated vs actual ROI comparison.
    """
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Total invested in period
        inv_row = conn.execute("""
            SELECT COALESCE(SUM(total_investment), 0) AS total_invested,
                   COALESCE(SUM(quantity), 0) AS units_purchased
            FROM purchases
            WHERE purchase_date >= ?
        """, (cutoff,)).fetchone()
        total_invested = inv_row["total_invested"]
        units_purchased = inv_row["units_purchased"]

        # Sales in period
        sales_row = conn.execute("""
            SELECT COALESCE(SUM(s.sell_price * s.units_sold), 0) AS total_revenue,
                   COALESCE(SUM(s.amazon_fees * s.units_sold), 0) AS total_amazon_fees,
                   COALESCE(SUM(s.actual_profit), 0) AS total_profit,
                   COALESCE(SUM(s.units_sold), 0) AS units_sold
            FROM sales s
            WHERE s.sale_date >= ?
        """, (cutoff,)).fetchone()
        total_revenue = round(sales_row["total_revenue"], 2)
        total_amazon_fees = round(sales_row["total_amazon_fees"], 2)
        total_profit = round(sales_row["total_profit"], 2)
        units_sold = sales_row["units_sold"]

        realized_roi = round((total_profit / total_invested) * 100, 1) if total_invested > 0 else 0.0
        sell_through_rate = round((units_sold / units_purchased) * 100, 1) if units_purchased > 0 else 0.0

        # Average days to sell (for purchases that have sales)
        avg_days_row = conn.execute("""
            SELECT AVG(julianday(s.sale_date) - julianday(p.purchase_date)) AS avg_days
            FROM sales s
            JOIN purchases p ON p.id = s.purchase_id
            WHERE s.sale_date >= ?
        """, (cutoff,)).fetchone()
        avg_days_to_sell = round(avg_days_row["avg_days"], 1) if avg_days_row["avg_days"] else 0.0

        # Top performers (by total profit)
        top_rows = conn.execute("""
            SELECT p.asin, p.name, p.retailer, p.buy_cost,
                   SUM(s.units_sold) AS units_sold,
                   SUM(s.actual_profit) AS total_profit,
                   ROUND(SUM(s.actual_profit) / (p.buy_cost * SUM(s.units_sold)) * 100, 1) AS roi
            FROM sales s
            JOIN purchases p ON p.id = s.purchase_id
            WHERE s.sale_date >= ?
            GROUP BY s.purchase_id
            ORDER BY total_profit DESC
            LIMIT 10
        """, (cutoff,)).fetchall()
        top_performers = [dict(r) for r in top_rows]

        # Slow movers (purchased > 60 days ago, still not fully sold)
        slow_cutoff = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")
        slow_rows = conn.execute("""
            SELECT p.*,
                p.quantity - COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_remaining,
                CAST(julianday('now') - julianday(p.purchase_date) AS INTEGER) AS days_held
            FROM purchases p
            WHERE p.purchase_date <= ?
              AND p.status NOT IN ('sold', 'closed')
            ORDER BY days_held DESC
            LIMIT 10
        """, (slow_cutoff,)).fetchall()
        slow_movers = [dict(r) for r in slow_rows]

        # Estimated vs actual ROI comparison
        est_vs_actual_row = conn.execute("""
            SELECT
                ROUND(AVG(p.estimated_roi), 1) AS avg_estimated_roi,
                ROUND(AVG(
                    CASE WHEN s_agg.total_profit IS NOT NULL
                         THEN (s_agg.total_profit / (p.buy_cost * s_agg.total_units)) * 100
                         ELSE NULL END
                ), 1) AS avg_actual_roi
            FROM purchases p
            LEFT JOIN (
                SELECT purchase_id,
                       SUM(actual_profit) AS total_profit,
                       SUM(units_sold) AS total_units
                FROM sales
                WHERE sale_date >= ?
                GROUP BY purchase_id
            ) s_agg ON s_agg.purchase_id = p.id
            WHERE p.purchase_date >= ?
              AND p.estimated_roi IS NOT NULL
              AND s_agg.total_profit IS NOT NULL
        """, (cutoff, cutoff)).fetchone()

        avg_estimated_roi = est_vs_actual_row["avg_estimated_roi"] or 0.0
        avg_actual_roi = est_vs_actual_row["avg_actual_roi"] or 0.0
        accuracy_gap = round(avg_actual_roi - avg_estimated_roi, 1)

        return {
            "period": f"Last {days} days",
            "total_invested": round(total_invested, 2),
            "total_revenue": total_revenue,
            "total_amazon_fees": total_amazon_fees,
            "total_profit": total_profit,
            "realized_roi": realized_roi,
            "units_purchased": units_purchased,
            "units_sold": units_sold,
            "sell_through_rate": sell_through_rate,
            "avg_days_to_sell": avg_days_to_sell,
            "top_performers": top_performers,
            "slow_movers": slow_movers,
            "estimated_vs_actual": {
                "avg_estimated_roi": avg_estimated_roi,
                "avg_actual_roi": avg_actual_roi,
                "accuracy_gap": accuracy_gap,
            },
        }
    finally:
        conn.close()


def get_hit_rate(days=90):
    """Of products purchased in the period, what % sold within 30/60/90 days?

    Returns dict with hit rates at each interval, plus unsold count.
    """
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        # All purchases in the period
        total_row = conn.execute("""
            SELECT COUNT(*) AS total FROM purchases WHERE purchase_date >= ?
        """, (cutoff,)).fetchone()
        total_purchased = total_row["total"]

        if total_purchased == 0:
            return {
                "period": f"Last {days} days",
                "total_purchased": 0,
                "sold_within_30_days": 0,
                "sold_within_60_days": 0,
                "sold_within_90_days": 0,
                "unsold": 0,
                "hit_rate_30d": 0.0,
                "hit_rate_60d": 0.0,
                "hit_rate_90d": 0.0,
            }

        # Purchases that had at least one sale within N days of purchase_date
        def _sold_within(interval_days):
            row = conn.execute("""
                SELECT COUNT(DISTINCT p.id) AS cnt
                FROM purchases p
                JOIN sales s ON s.purchase_id = p.id
                WHERE p.purchase_date >= ?
                  AND julianday(s.sale_date) - julianday(p.purchase_date) <= ?
            """, (cutoff, interval_days)).fetchone()
            return row["cnt"]

        sold_30 = _sold_within(30)
        sold_60 = _sold_within(60)
        sold_90 = _sold_within(90)

        # Unsold: purchases with no sales at all
        unsold_row = conn.execute("""
            SELECT COUNT(*) AS cnt
            FROM purchases p
            WHERE p.purchase_date >= ?
              AND p.id NOT IN (SELECT DISTINCT purchase_id FROM sales)
        """, (cutoff,)).fetchone()
        unsold = unsold_row["cnt"]

        return {
            "period": f"Last {days} days",
            "total_purchased": total_purchased,
            "sold_within_30_days": sold_30,
            "sold_within_60_days": sold_60,
            "sold_within_90_days": sold_90,
            "unsold": unsold,
            "hit_rate_30d": round((sold_30 / total_purchased) * 100, 1),
            "hit_rate_60d": round((sold_60 / total_purchased) * 100, 1),
            "hit_rate_90d": round((sold_90 / total_purchased) * 100, 1),
        }
    finally:
        conn.close()


def import_from_results(results_path, auto_confirm=False):
    """Read sourcing results JSON, create purchase records for BUY products.

    If auto_confirm is False (default), prints the list and returns without
    inserting. Pass auto_confirm=True to insert directly.

    Returns list of created purchase dicts.
    """
    path = Path(results_path)
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    products = data.get("products", [])
    buy_products = [
        p for p in products
        if p.get("profitability", {}).get("verdict") == "BUY"
    ]

    if not buy_products:
        print("No BUY products found in results.", file=sys.stderr)
        return []

    if not auto_confirm:
        print(f"Found {len(buy_products)} BUY products:", file=sys.stderr)
        for i, p in enumerate(buy_products, 1):
            prof = p.get("profitability", {})
            amz = p.get("amazon", {})
            print(f"  {i}. {p.get('name', 'Unknown')} | ASIN: {amz.get('asin', '?')} | "
                  f"Cost: ${prof.get('buy_cost', '?')} | ROI: {prof.get('roi_percent', '?')}%",
                  file=sys.stderr)
        print("\nRe-run with --confirm to import these purchases.", file=sys.stderr)
        return []

    created = []
    for p in buy_products:
        prof = p.get("profitability", {})
        amz = p.get("amazon", {})
        asin = amz.get("asin")
        if not asin:
            continue

        purchase = record_purchase(
            asin=asin,
            name=p.get("name", ""),
            retailer=p.get("retailer", data.get("retailer", "")),
            buy_cost=prof.get("buy_cost", 0),
            quantity=1,
            estimated_sell_price=prof.get("sell_price"),
            estimated_roi=prof.get("roi_percent"),
            estimated_profit_per_unit=prof.get("profit_per_unit"),
            gift_card_discount=prof.get("gift_card_discount_applied", 0),
            cashback_percent=prof.get("cashback_percent_applied", 0),
            source_url=p.get("retail_url", ""),
        )
        created.append(purchase)

    return created


def get_dashboard():
    """Summary dashboard: total invested, total sold, realized ROI, gaps,
    top performers, slow movers.

    Returns a dict suitable for JSON output.
    """
    conn = get_db()
    try:
        # Overall totals
        inv_row = conn.execute("""
            SELECT COALESCE(SUM(total_investment), 0) AS total_invested,
                   COALESCE(SUM(quantity), 0) AS total_units,
                   COUNT(*) AS total_purchases
            FROM purchases
        """).fetchone()

        sales_row = conn.execute("""
            SELECT COALESCE(SUM(actual_profit), 0) AS total_profit,
                   COALESCE(SUM(sell_price * units_sold), 0) AS total_revenue,
                   COALESCE(SUM(units_sold), 0) AS total_units_sold,
                   COALESCE(SUM(amazon_fees * units_sold), 0) AS total_fees
            FROM sales
        """).fetchone()

        total_invested = round(inv_row["total_invested"], 2)
        total_profit = round(sales_row["total_profit"], 2)
        total_revenue = round(sales_row["total_revenue"], 2)
        total_units_sold = sales_row["total_units_sold"]
        total_fees = round(sales_row["total_fees"], 2)
        realized_roi = round((total_profit / total_invested) * 100, 1) if total_invested > 0 else 0.0

        # Status breakdown
        status_rows = conn.execute("""
            SELECT status, COUNT(*) AS count, COALESCE(SUM(total_investment), 0) AS investment
            FROM purchases
            GROUP BY status
        """).fetchall()
        by_status = {r["status"]: {"count": r["count"], "investment": round(r["investment"], 2)}
                     for r in status_rows}

        # Estimated vs actual ROI (for purchases with sales)
        est_row = conn.execute("""
            SELECT
                ROUND(AVG(p.estimated_roi), 1) AS avg_estimated_roi,
                ROUND(AVG(
                    (s_agg.total_profit / (p.buy_cost * s_agg.total_units)) * 100
                ), 1) AS avg_actual_roi
            FROM purchases p
            JOIN (
                SELECT purchase_id,
                       SUM(actual_profit) AS total_profit,
                       SUM(units_sold) AS total_units
                FROM sales
                GROUP BY purchase_id
            ) s_agg ON s_agg.purchase_id = p.id
            WHERE p.estimated_roi IS NOT NULL
        """).fetchone()
        avg_estimated_roi = est_row["avg_estimated_roi"] or 0.0
        avg_actual_roi = est_row["avg_actual_roi"] or 0.0

        # Top 5 performers by profit
        top_rows = conn.execute("""
            SELECT p.asin, p.name, p.retailer, p.buy_cost,
                   SUM(s.units_sold) AS units_sold,
                   SUM(s.actual_profit) AS total_profit,
                   ROUND(SUM(s.actual_profit) / (p.buy_cost * SUM(s.units_sold)) * 100, 1) AS roi
            FROM sales s
            JOIN purchases p ON p.id = s.purchase_id
            GROUP BY s.purchase_id
            ORDER BY total_profit DESC
            LIMIT 5
        """).fetchall()
        top_performers = [dict(r) for r in top_rows]

        # Slow movers (>60 days, not fully sold)
        slow_cutoff = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")
        slow_rows = conn.execute("""
            SELECT p.asin, p.name, p.retailer, p.buy_cost, p.quantity,
                p.quantity - COALESCE((SELECT SUM(s.units_sold) FROM sales s WHERE s.purchase_id = p.id), 0) AS units_remaining,
                CAST(julianday('now') - julianday(p.purchase_date) AS INTEGER) AS days_held,
                p.total_investment
            FROM purchases p
            WHERE p.purchase_date <= ?
              AND p.status NOT IN ('sold', 'closed')
            ORDER BY days_held DESC
            LIMIT 10
        """, (slow_cutoff,)).fetchall()
        slow_movers = [dict(r) for r in slow_rows]

        return {
            "total_invested": total_invested,
            "total_revenue": total_revenue,
            "total_amazon_fees": total_fees,
            "total_profit": total_profit,
            "realized_roi": realized_roi,
            "total_purchases": inv_row["total_purchases"],
            "total_units_purchased": inv_row["total_units"],
            "total_units_sold": total_units_sold,
            "by_status": by_status,
            "estimated_vs_actual": {
                "avg_estimated_roi": avg_estimated_roi,
                "avg_actual_roi": avg_actual_roi,
                "accuracy_gap": round(avg_actual_roi - avg_estimated_roi, 1),
            },
            "top_performers": top_performers,
            "slow_movers": slow_movers,
        }
    finally:
        conn.close()


def update_status(purchase_id, new_status):
    """Update a purchase to an arbitrary valid status.

    Returns the updated purchase dict or None if not found.
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of: {VALID_STATUSES}")
    conn = get_db()
    try:
        conn.execute("UPDATE purchases SET status = ? WHERE id = ?", (new_status, purchase_id))
        conn.commit()
        row = conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_float(val):
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val):
    """Safely convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_buy(args):
    """CLI handler: record a purchase."""
    purchase = record_purchase(
        asin=args.asin,
        name=args.name,
        retailer=args.retailer,
        buy_cost=args.cost,
        quantity=args.qty,
        estimated_sell_price=_to_float(args.sell_price) if args.sell_price else None,
        estimated_roi=_to_float(args.est_roi) if args.est_roi else None,
        estimated_profit_per_unit=_to_float(args.est_profit) if args.est_profit else None,
        gift_card_discount=args.gc_discount,
        cashback_percent=args.cashback,
        notes=args.notes,
        source_url=args.source_url,
        purchase_date=args.date,
    )
    print(json.dumps(purchase, indent=2))


def cli_ship(args):
    """CLI handler: mark a purchase as shipped to FBA."""
    result = mark_shipped(args.id)
    if result is None:
        print(f"Error: purchase ID {args.id} not found.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


def cli_live(args):
    """CLI handler: mark a purchase as live on Amazon."""
    result = mark_live(args.id)
    if result is None:
        print(f"Error: purchase ID {args.id} not found.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


def cli_sold(args):
    """CLI handler: record a sale."""
    try:
        sale = record_sale(
            purchase_id=args.id,
            units_sold=args.units,
            sell_price=args.price,
            amazon_fees=args.fees,
        )
        print(json.dumps(sale, indent=2))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_inventory(args):
    """CLI handler: list inventory."""
    inventory = get_inventory(status=args.status)
    if not inventory:
        label = f" with status '{args.status}'" if args.status else ""
        print(f"No inventory found{label}.", file=sys.stderr)
        sys.exit(0)
    print(json.dumps(inventory, indent=2))


def cli_pnl(args):
    """CLI handler: P&L report."""
    report = get_pnl_report(days=args.days)
    print(json.dumps(report, indent=2))


def cli_hit_rate(args):
    """CLI handler: hit rate analysis."""
    report = get_hit_rate(days=args.days)
    print(json.dumps(report, indent=2))


def cli_import_buys(args):
    """CLI handler: import BUY products from sourcing results."""
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"Error: file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    try:
        created = import_from_results(str(results_path), auto_confirm=args.confirm)
        if created:
            print(json.dumps({
                "imported": True,
                "source": str(results_path),
                "purchases_created": len(created),
                "purchases": created,
            }, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_dashboard(args):
    """CLI handler: dashboard summary."""
    dashboard = get_dashboard()
    print(json.dumps(dashboard, indent=2))


def cli_status(args):
    """CLI handler: update purchase status."""
    try:
        result = update_status(args.id, args.to)
        if result is None:
            print(f"Error: purchase ID {args.id} not found.", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FBA Inventory Tracker — purchase, ship, sell, P&L, hit-rate analysis"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # buy
    p_buy = subparsers.add_parser("buy", help="Record a new purchase")
    p_buy.add_argument("--asin", required=True, help="Amazon ASIN")
    p_buy.add_argument("--name", default="", help="Product name")
    p_buy.add_argument("--cost", type=float, required=True, help="Buy cost per unit ($)")
    p_buy.add_argument("--qty", type=int, default=1, help="Quantity purchased (default: 1)")
    p_buy.add_argument("--retailer", default="", help="Retailer name")
    p_buy.add_argument("--sell-price", default=None, help="Estimated sell price on Amazon ($)")
    p_buy.add_argument("--est-roi", default=None, help="Estimated ROI (%%)")
    p_buy.add_argument("--est-profit", default=None, help="Estimated profit per unit ($)")
    p_buy.add_argument("--gc-discount", type=float, default=0, help="Gift card discount (%%, default: 0)")
    p_buy.add_argument("--cashback", type=float, default=0, help="Cashback (%%, default: 0)")
    p_buy.add_argument("--notes", default=None, help="Optional notes")
    p_buy.add_argument("--source-url", default=None, help="Source/retail URL")
    p_buy.add_argument("--date", default=None, help="Purchase date (YYYY-MM-DD, default: today)")
    p_buy.set_defaults(func=cli_buy)

    # ship
    p_ship = subparsers.add_parser("ship", help="Mark a purchase as shipped to FBA")
    p_ship.add_argument("--id", type=int, required=True, help="Purchase ID")
    p_ship.set_defaults(func=cli_ship)

    # live
    p_live = subparsers.add_parser("live", help="Mark a purchase as live on Amazon")
    p_live.add_argument("--id", type=int, required=True, help="Purchase ID")
    p_live.set_defaults(func=cli_live)

    # sold
    p_sold = subparsers.add_parser("sold", help="Record a sale against a purchase")
    p_sold.add_argument("--id", type=int, required=True, help="Purchase ID")
    p_sold.add_argument("--units", type=int, default=1, help="Units sold (default: 1)")
    p_sold.add_argument("--price", type=float, required=True, help="Sell price per unit ($)")
    p_sold.add_argument("--fees", type=float, default=None, help="Amazon fees per unit ($)")
    p_sold.set_defaults(func=cli_sold)

    # inventory
    p_inv = subparsers.add_parser("inventory", help="View current inventory")
    p_inv.add_argument("--status", choices=VALID_STATUSES, default=None,
                       help="Filter by status")
    p_inv.set_defaults(func=cli_inventory)

    # pnl
    p_pnl = subparsers.add_parser("pnl", help="P&L report")
    p_pnl.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    p_pnl.set_defaults(func=cli_pnl)

    # hit-rate
    p_hit = subparsers.add_parser("hit-rate", help="Hit rate analysis")
    p_hit.add_argument("--days", type=int, default=90, help="Look back N days (default: 90)")
    p_hit.set_defaults(func=cli_hit_rate)

    # import-buys
    p_import = subparsers.add_parser("import-buys", help="Import BUY products from sourcing results")
    p_import.add_argument("--results", required=True, help="Path to sourcing results JSON")
    p_import.add_argument("--confirm", action="store_true",
                          help="Actually import (without this flag, just previews)")
    p_import.set_defaults(func=cli_import_buys)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Dashboard summary")
    p_dash.set_defaults(func=cli_dashboard)

    # status (generic status update)
    p_status = subparsers.add_parser("status", help="Update purchase status")
    p_status.add_argument("--id", type=int, required=True, help="Purchase ID")
    p_status.add_argument("--to", required=True, choices=VALID_STATUSES,
                          help="New status")
    p_status.set_defaults(func=cli_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
