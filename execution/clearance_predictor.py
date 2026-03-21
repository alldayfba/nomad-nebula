from __future__ import annotations
"""
Clearance Cadence Predictor
Analyzes price history from results_db to detect if a product price is still dropping
vs. at final clearance level. Helps students avoid buying too early.
"""
import sqlite3
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Default DB path (same as results_db.py)
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sourcing", "results.db")


def get_price_trajectory(retailer: str, url: str = None, product_name: str = None,
                          asin: str = None, db_path: str = None) -> dict:
    """
    Analyze price trajectory for a product at a retailer.

    Returns:
        {
            "trajectory": "dropping" | "stable" | "rising" | "first_markdown" | "unknown",
            "price_count": int,
            "latest_price": float,
            "prev_price": float,
            "drop_count_30d": int,
            "recommendation": str,
            "confidence": "HIGH" | "MEDIUM" | "LOW"
        }
    """
    db_path = db_path or DEFAULT_DB_PATH

    if not os.path.exists(db_path):
        return {"trajectory": "unknown", "recommendation": "No price history yet", "confidence": "LOW", "price_count": 0}

    try:
        conn = sqlite3.connect(db_path)
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()

        # Build query
        if asin:
            query = "SELECT price, scraped_at FROM retailer_price_history WHERE asin=? AND scraped_at > ? ORDER BY scraped_at ASC"
            params = (asin, cutoff)
        elif url:
            query = "SELECT price, scraped_at FROM retailer_price_history WHERE url=? AND scraped_at > ? ORDER BY scraped_at ASC"
            params = (url, cutoff)
        else:
            return {"trajectory": "unknown", "recommendation": "No identifier provided", "confidence": "LOW", "price_count": 0}

        rows = conn.execute(query, params).fetchall()
        conn.close()

        if len(rows) < 2:
            return {
                "trajectory": "first_markdown" if rows else "unknown",
                "price_count": len(rows),
                "latest_price": rows[-1][0] if rows else None,
                "prev_price": None,
                "drop_count_30d": 0,
                "recommendation": "First time seeing this price — could drop further" if rows else "No history",
                "confidence": "LOW"
            }

        prices = [r[0] for r in rows]
        latest = prices[-1]
        prev = prices[-2]

        # Count how many times it dropped in the last 30 days
        drop_count = sum(1 for i in range(1, len(prices)) if prices[i] < prices[i-1])
        rise_count = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])

        # Calculate total drop from highest recent price
        high_price = max(prices)
        total_drop_pct = (high_price - latest) / high_price * 100 if high_price > 0 else 0

        if drop_count >= 2 and latest < prev:
            trajectory = "dropping"
            recommendation = f"Price still falling ({drop_count} drops in 30d, down {total_drop_pct:.0f}% from recent high). Wait 3-5 days."
            confidence = "HIGH" if drop_count >= 3 else "MEDIUM"
        elif drop_count >= 1 and total_drop_pct >= 20:
            trajectory = "first_markdown"
            recommendation = f"Down {total_drop_pct:.0f}% — could be final clearance or could drop more. Monitor."
            confidence = "MEDIUM"
        elif rise_count > drop_count:
            trajectory = "rising"
            recommendation = "Price trending up — buy now if profitable."
            confidence = "MEDIUM"
        else:
            trajectory = "stable"
            recommendation = "Price stable. Safe to buy at current price."
            confidence = "HIGH" if len(prices) >= 5 else "MEDIUM"

        return {
            "trajectory": trajectory,
            "price_count": len(prices),
            "latest_price": latest,
            "prev_price": prev,
            "drop_count_30d": drop_count,
            "total_drop_pct": round(total_drop_pct, 1),
            "recommendation": recommendation,
            "confidence": confidence,
        }

    except Exception as e:
        logger.warning(f"Price trajectory analysis failed: {e}")
        return {"trajectory": "unknown", "recommendation": f"Error: {e}", "confidence": "LOW", "price_count": 0}


def record_scan_prices(products: list, retailer: str, db_path: str = None) -> int:
    """
    Record prices from a scan result to the price history table.
    Call this after every scrape to build up history over time.
    Returns number of prices recorded.
    """
    db_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        count = 0
        for p in products:
            price = p.get("price") or p.get("retail_price") or p.get("buy_cost")
            if price and price > 0:
                conn.execute(
                    "INSERT INTO retailer_price_history (retailer, url, product_name, asin, price, original_price) VALUES (?,?,?,?,?,?)",
                    (retailer, p.get("url", ""), p.get("name", ""), p.get("asin"), price, p.get("original_price"))
                )
                count += 1
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Failed to record scan prices: {e}")
        return 0


if __name__ == "__main__":
    print("Clearance predictor module loaded. No test data available yet — history builds over time.")
