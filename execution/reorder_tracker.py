#!/usr/bin/env python3
from __future__ import annotations
"""
Script: reorder_tracker.py
Purpose: Track profitable products for reorder alerts.

         When a product was profitable once, track the source URL and alert
         when it's back in stock or on sale again. Replenishables are the
         highest-LTV products in OA — finding them once means recurring profit.

         Also includes:
         - Seasonal pattern detection from BSR history
         - Cashback stacking calculator

Usage:
    python execution/reorder_tracker.py add --asin B0XXXXXXXX --source-url https://...
    python execution/reorder_tracker.py check                    # Check all tracked URLs
    python execution/reorder_tracker.py seasonal --asin B0XX     # Seasonal analysis
    python execution/reorder_tracker.py cashback --price 29.99   # Stacking calculator
"""

import argparse
import json
import os
import sys
import time
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

DB_PATH = Path(__file__).parent.parent / ".tmp" / "sourcing" / "reorder_tracker.db"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ── Database ────────────────────────────────────────────────────────────────


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS tracked_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_retailer TEXT,
        last_buy_price REAL,
        last_sell_price REAL,
        last_profit REAL,
        last_roi REAL,
        times_purchased INTEGER DEFAULT 0,
        total_profit REAL DEFAULT 0,
        status TEXT DEFAULT 'active',  -- active, paused, retired
        last_checked_at TEXT,
        last_in_stock_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(asin, source_url)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reorder_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracked_id INTEGER,
        check_time TEXT DEFAULT (datetime('now')),
        in_stock INTEGER,
        current_price REAL,
        price_change_pct REAL,
        FOREIGN KEY(tracked_id) REFERENCES tracked_products(id)
    )""")
    conn.commit()
    return conn


def add_tracked_product(asin: str, source_url: str, retailer: str = "",
                        buy_price: float = 0, sell_price: float = 0,
                        profit: float = 0, roi: float = 0):
    """Add a product to reorder tracking."""
    db = _get_db()
    try:
        db.execute("""INSERT OR REPLACE INTO tracked_products
            (asin, source_url, source_retailer, last_buy_price, last_sell_price,
             last_profit, last_roi, times_purchased, total_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT times_purchased + 1 FROM tracked_products WHERE asin=? AND source_url=?), 1),
                    COALESCE((SELECT total_profit FROM tracked_products WHERE asin=? AND source_url=?), 0) + ?)
        """, (asin, source_url, retailer, buy_price, sell_price, profit, roi,
              asin, source_url, asin, source_url, profit))
        db.commit()
        print(f"[reorder] Tracking {asin} from {source_url}", file=sys.stderr)
    finally:
        db.close()


def check_tracked_products() -> list[dict]:
    """Check all tracked product URLs for stock/price changes.

    Returns list of products that are back in stock or have price drops.
    """
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM tracked_products WHERE status='active'"
        ).fetchall()

        alerts = []
        headers = {"User-Agent": USER_AGENT}

        for row in rows:
            tracked_id = row["id"]
            url = row["source_url"]
            last_price = row["last_buy_price"] or 0

            try:
                r = requests.get(url, headers=headers, timeout=15)
                in_stock = r.status_code == 200 and not any(
                    s in r.text.lower() for s in ["out of stock", "sold out", "unavailable"]
                )

                # Try to extract current price
                import re
                price_match = re.search(r'"price"\s*:\s*"?(\d+\.?\d*)"?', r.text)
                current_price = float(price_match.group(1)) if price_match else None

                price_change = None
                if current_price and last_price > 0:
                    price_change = round(((current_price - last_price) / last_price) * 100, 1)

                db.execute("""INSERT INTO reorder_checks
                    (tracked_id, in_stock, current_price, price_change_pct)
                    VALUES (?, ?, ?, ?)
                """, (tracked_id, 1 if in_stock else 0, current_price, price_change))

                db.execute("""UPDATE tracked_products SET last_checked_at=datetime('now')
                    WHERE id=?""", (tracked_id,))
                if in_stock:
                    db.execute("""UPDATE tracked_products SET last_in_stock_at=datetime('now')
                        WHERE id=?""", (tracked_id,))

                if in_stock:
                    alert = {
                        "asin": row["asin"],
                        "source_url": url,
                        "retailer": row["source_retailer"],
                        "in_stock": True,
                        "current_price": current_price,
                        "last_price": last_price,
                        "price_change_pct": price_change,
                        "times_purchased": row["times_purchased"],
                        "total_profit": row["total_profit"],
                    }
                    if price_change and price_change < -10:
                        alert["price_dropped"] = True
                    alerts.append(alert)

            except Exception as e:
                print(f"[reorder] Error checking {url}: {e}", file=sys.stderr)

            time.sleep(1)

        db.commit()
        return alerts
    finally:
        db.close()


# ── Seasonal Pattern Detection ──────────────────────────────────────────────


def detect_seasonal_pattern(bsr_csv: list) -> dict:
    """Analyze BSR history for seasonal demand patterns.

    Looks for recurring BSR drops (= sales spikes) at similar times of year.

    Args:
        bsr_csv: Keepa CSV array for BSR (index 3). Format: [ts, rank, ts, rank, ...]

    Returns:
        dict with seasonal_pattern (bool), peak_months, demand_trend
    """
    if not bsr_csv or len(bsr_csv) < 20:
        return {"seasonal_pattern": False, "reason": "insufficient_data"}

    from execution.velocity_analyzer import keepa_ts_to_unix

    # Parse into monthly buckets
    monthly_bsr = {}  # month_num -> [bsr values]
    for i in range(0, len(bsr_csv) - 1, 2):
        ts = bsr_csv[i]
        rank = bsr_csv[i + 1]
        if ts < 0 or rank < 0:
            continue
        unix_ts = keepa_ts_to_unix(ts)
        dt = datetime.fromtimestamp(unix_ts)
        month = dt.month
        if month not in monthly_bsr:
            monthly_bsr[month] = []
        monthly_bsr[month].append(rank)

    if len(monthly_bsr) < 6:
        return {"seasonal_pattern": False, "reason": "not_enough_months"}

    # Calculate average BSR per month
    monthly_avg = {}
    for month, ranks in monthly_bsr.items():
        monthly_avg[month] = sum(ranks) / len(ranks)

    overall_avg = sum(monthly_avg.values()) / len(monthly_avg)

    # Find peak months (BSR significantly below average = more sales)
    peak_months = []
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for month, avg_bsr in monthly_avg.items():
        if avg_bsr < overall_avg * 0.7:  # 30%+ better than average
            peak_months.append({
                "month": month,
                "name": month_names[month],
                "avg_bsr": round(avg_bsr),
                "improvement_vs_avg": round((1 - avg_bsr / overall_avg) * 100, 1),
            })

    peak_months.sort(key=lambda x: x["avg_bsr"])

    # Determine current demand trend
    current_month = datetime.now().month
    current_avg = monthly_avg.get(current_month, overall_avg)
    next_month = (current_month % 12) + 1
    next_avg = monthly_avg.get(next_month, overall_avg)

    if next_avg < current_avg * 0.8:
        demand_trend = "approaching_peak"
    elif next_avg > current_avg * 1.2:
        demand_trend = "declining"
    else:
        demand_trend = "stable"

    return {
        "seasonal_pattern": len(peak_months) > 0,
        "peak_months": peak_months,
        "demand_trend": demand_trend,
        "overall_avg_bsr": round(overall_avg),
        "current_month_avg_bsr": round(current_avg),
    }


# ── Cashback Stacking Calculator ────────────────────────────────────────────


def calculate_stacked_cost(
    retail_price: float,
    gift_card_discount_pct: float = 0,
    cashback_pct: float = 0,
    credit_card_bonus_pct: float = 0,
    coupon_pct: float = 0,
    coupon_flat: float = 0,
) -> dict:
    """Calculate effective buy cost after stacking all discounts.

    Common stacks:
    - Buy discounted gift cards (5-7% off)
    - Rakuten/TopCashback (2-10%)
    - Credit card category bonus (3-5%)
    - Store coupon (10-30%)
    - Manufacturer coupon (flat $)

    Args:
        retail_price: Listed retail price.
        gift_card_discount_pct: Gift card discount (e.g., 5 = 5% off).
        cashback_pct: Cashback portal rate (e.g., 4 = 4%).
        credit_card_bonus_pct: CC category bonus (e.g., 5 = 5%).
        coupon_pct: Store coupon percentage (e.g., 20 = 20% off).
        coupon_flat: Flat coupon amount (e.g., 10 = $10 off).

    Returns:
        dict with effective_cost, total_savings, savings_breakdown
    """
    breakdown = []
    cost = retail_price

    # Apply coupon first (reduces base price)
    if coupon_pct > 0:
        savings = cost * (coupon_pct / 100)
        cost -= savings
        breakdown.append({"source": f"Store coupon ({coupon_pct}%)", "savings": round(savings, 2)})

    if coupon_flat > 0:
        cost -= coupon_flat
        breakdown.append({"source": f"Flat coupon (-${coupon_flat})", "savings": coupon_flat})

    # Gift card discount (buy GC at discount, pay face value)
    if gift_card_discount_pct > 0:
        savings = cost * (gift_card_discount_pct / 100)
        cost -= savings
        breakdown.append({"source": f"Gift card ({gift_card_discount_pct}%)", "savings": round(savings, 2)})

    # Cashback (earned back after purchase)
    cashback_amount = 0
    if cashback_pct > 0:
        cashback_amount = cost * (cashback_pct / 100)
        cost -= cashback_amount
        breakdown.append({"source": f"Cashback ({cashback_pct}%)", "savings": round(cashback_amount, 2)})

    # CC bonus (earned back as statement credit/points)
    cc_amount = 0
    if credit_card_bonus_pct > 0:
        cc_amount = cost * (credit_card_bonus_pct / 100)
        cost -= cc_amount
        breakdown.append({"source": f"CC bonus ({credit_card_bonus_pct}%)", "savings": round(cc_amount, 2)})

    cost = max(0.01, cost)
    total_savings = retail_price - cost
    total_savings_pct = (total_savings / retail_price) * 100 if retail_price > 0 else 0

    return {
        "retail_price": retail_price,
        "effective_cost": round(cost, 2),
        "total_savings": round(total_savings, 2),
        "total_savings_pct": round(total_savings_pct, 1),
        "breakdown": breakdown,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Reorder tracking + seasonal detection + cashback calc")
    sub = parser.add_subparsers(dest="command")

    # Add tracked product
    p_add = sub.add_parser("add", help="Add product to reorder tracking")
    p_add.add_argument("--asin", required=True)
    p_add.add_argument("--source-url", required=True)
    p_add.add_argument("--retailer", default="")
    p_add.add_argument("--buy-price", type=float, default=0)
    p_add.add_argument("--sell-price", type=float, default=0)
    p_add.add_argument("--profit", type=float, default=0)
    p_add.add_argument("--roi", type=float, default=0)

    # Check all tracked products
    sub.add_parser("check", help="Check all tracked URLs for stock/price changes")

    # Seasonal analysis
    p_seasonal = sub.add_parser("seasonal", help="Analyze BSR for seasonal patterns")
    p_seasonal.add_argument("--asin", required=True)

    # Cashback calculator
    p_cash = sub.add_parser("cashback", help="Calculate stacked discount savings")
    p_cash.add_argument("--price", type=float, required=True)
    p_cash.add_argument("--gift-card", type=float, default=0, help="Gift card discount %")
    p_cash.add_argument("--cashback", type=float, default=0, help="Cashback portal %")
    p_cash.add_argument("--cc-bonus", type=float, default=0, help="Credit card bonus %")
    p_cash.add_argument("--coupon-pct", type=float, default=0, help="Coupon %")
    p_cash.add_argument("--coupon-flat", type=float, default=0, help="Flat coupon $")

    args = parser.parse_args()

    if args.command == "add":
        add_tracked_product(
            asin=args.asin, source_url=args.source_url,
            retailer=args.retailer, buy_price=args.buy_price,
            sell_price=args.sell_price, profit=args.profit, roi=args.roi,
        )

    elif args.command == "check":
        alerts = check_tracked_products()
        print(f"\n{len(alerts)} products in stock:")
        for a in alerts:
            price_info = f"${a['current_price']:.2f}" if a.get("current_price") else "price unknown"
            drop = f" ({a['price_change_pct']:+.1f}%)" if a.get("price_change_pct") else ""
            print(f"  {a['asin']} — {price_info}{drop} — {a['retailer']} — bought {a['times_purchased']}x (${a['total_profit']:.2f} total profit)")

    elif args.command == "cashback":
        result = calculate_stacked_cost(
            retail_price=args.price,
            gift_card_discount_pct=args.gift_card,
            cashback_pct=args.cashback,
            credit_card_bonus_pct=args.cc_bonus,
            coupon_pct=args.coupon_pct,
            coupon_flat=args.coupon_flat,
        )
        print(f"\nRetail: ${result['retail_price']:.2f}")
        for b in result["breakdown"]:
            print(f"  - {b['source']}: -${b['savings']:.2f}")
        print(f"Effective cost: ${result['effective_cost']:.2f} ({result['total_savings_pct']:.1f}% saved)")

    elif args.command == "seasonal":
        # Need Keepa data for this
        try:
            from execution.keepa_client import KeepaClient
            client = KeepaClient()
            product = client.get_product(args.asin)
            if product:
                csv_data = product.get("csv", [])
                bsr_csv = csv_data[3] if csv_data and len(csv_data) > 3 else []
                result = detect_seasonal_pattern(bsr_csv)
                print(json.dumps(result, indent=2))
            else:
                print("Product not found on Keepa")
        except Exception as e:
            print(f"Error: {e}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
