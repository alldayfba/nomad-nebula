#!/usr/bin/env python3
"""
Script: sourcing_alerts.py
Purpose: Send alerts when profitable products are found during FBA sourcing runs.
Inputs:  --results (path to results JSON), --db-alerts, --test, --method
Outputs: Telegram or email notification with BUY/MAYBE products

Usage:
  python execution/sourcing_alerts.py --results .tmp/sourcing/results.json
  python execution/sourcing_alerts.py --results .tmp/sourcing/results.json --method email
  python execution/sourcing_alerts.py --db-alerts
  python execution/sourcing_alerts.py --test
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def send_sourcing_alert(results_path, method="telegram"):
    """Send an alert with BUY/MAYBE products from a sourcing run.

    Args:
        results_path: Path to the sourcing results JSON file.
        method: 'telegram' or 'email'.

    Returns:
        True if alert was sent successfully, False otherwise.
    """
    results_path = Path(results_path)
    if not results_path.exists():
        print(f"[alerts] Results file not found: {results_path}", file=sys.stderr)
        return False

    with open(results_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    summary = data.get("summary", {})

    buy_products = [p for p in products
                    if p.get("profitability", {}).get("verdict") == "BUY"]
    maybe_products = [p for p in products
                      if p.get("profitability", {}).get("verdict") == "MAYBE"]

    if not buy_products and not maybe_products:
        print("[alerts] No BUY or MAYBE products — skipping alert.", file=sys.stderr)
        return False

    message = format_alert_message(buy_products, maybe_products, summary, data)

    if method == "telegram":
        return send_telegram_alert(message)
    elif method == "email":
        return _send_email_alert(message)
    else:
        print(f"[alerts] Unknown method: {method}", file=sys.stderr)
        return False


def format_alert_message(buy_products, maybe_products, summary, full_data=None):
    """Format a Telegram/email alert message.

    Args:
        buy_products: List of products with BUY verdict.
        maybe_products: List of products with MAYBE verdict.
        summary: Summary dict from the results JSON.
        full_data: Full results data (for source URL, elapsed time, etc).

    Returns:
        Formatted alert string.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    total_profitable = len(buy_products) + len(maybe_products)

    lines = []
    lines.append(f"SOURCING ALERT -- {date_str}")
    lines.append("=" * 32)
    lines.append("")

    # BUY section
    if buy_products:
        lines.append(f"BUY ({len(buy_products)} products):")
        lines.append("")
        for i, p in enumerate(buy_products, 1):
            lines.extend(_format_product_lines(i, p))
        lines.append("")

    # MAYBE section
    if maybe_products:
        lines.append(f"MAYBE ({len(maybe_products)} products):")
        lines.append("")
        for i, p in enumerate(maybe_products, 1):
            lines.extend(_format_product_lines(i, p))
        lines.append("")

    # Summary stats
    lines.append("-" * 32)
    total_analyzed = summary.get("total_analyzed", 0)
    lines.append(f"Analyzed: {total_analyzed} | Profitable: {total_profitable}")

    if summary.get("avg_roi_percent"):
        lines.append(f"Avg ROI: {summary['avg_roi_percent']}%")
    if summary.get("avg_profit_per_unit"):
        lines.append(f"Avg Profit: ${summary['avg_profit_per_unit']}")

    # Source info
    if full_data:
        source_url = full_data.get("source_url", "")
        retailer = full_data.get("retailer", "")
        elapsed = full_data.get("elapsed_seconds", "")
        if retailer or source_url:
            lines.append(f"Source: {retailer} -- {source_url}")
        if elapsed:
            lines.append(f"Completed in {elapsed}s")

    return "\n".join(lines)


def _format_product_lines(index, product):
    """Format a single product for the alert message."""
    prof = product.get("profitability", {})
    amz = product.get("amazon", {})
    name = product.get("name", "Unknown")[:60]
    buy_cost = prof.get("buy_cost", "?")
    sell_price = prof.get("sell_price", "?")
    roi = prof.get("roi_percent", "?")
    profit = prof.get("profit_per_unit", "?")
    asin = amz.get("asin", "")
    bsr = amz.get("sales_rank", "N/A")
    sellers = amz.get("fba_seller_count", "?")

    lines = [
        f"{index}. {name}",
        f"   ${buy_cost} -> ${sell_price} | ROI: {roi}% | Profit: ${profit}",
    ]

    detail_parts = []
    if asin:
        detail_parts.append(f"ASIN: {asin}")
    if bsr and bsr != "N/A":
        detail_parts.append(f"BSR: {bsr}")
    if sellers and sellers != "?":
        detail_parts.append(f"Sellers: {sellers}")
    if detail_parts:
        lines.append(f"   {' | '.join(detail_parts)}")

    if asin:
        lines.append(f"   amazon.com/dp/{asin}")

    return lines


def send_telegram_alert(message):
    """Send a message via Telegram bot.

    Uses TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env.

    Args:
        message: The text message to send.

    Returns:
        True if sent successfully, False otherwise.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[alerts] ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env",
              file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Telegram has a 4096 char limit per message; split if needed
    chunks = _split_message(message, max_len=4000)

    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "",  # plain text to avoid markdown escaping issues
        }).encode()

        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if not result.get("ok"):
                    print(f"[alerts] Telegram API error: {result}", file=sys.stderr)
                    return False
        except Exception as e:
            print(f"[alerts] ERROR sending Telegram: {e}", file=sys.stderr)
            return False

    print("[alerts] Alert sent via Telegram.", file=sys.stderr)
    return True


def _send_email_alert(message):
    """Send alert via email (requires SMTP config in .env)."""
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    to_addr = os.getenv("SOURCING_EMAIL_TO", os.getenv("BRIEFING_EMAIL_TO"))

    if not all([smtp_user, smtp_pass, to_addr]):
        print("[alerts] ERROR: SMTP credentials or email recipient not set in .env",
              file=sys.stderr)
        return False

    msg = MIMEText(message)
    msg["Subject"] = f"Sourcing Alert -- {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("[alerts] Alert sent via email.", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[alerts] ERROR sending email: {e}", file=sys.stderr)
        return False


def _split_message(message, max_len=4000):
    """Split a long message into chunks that fit within Telegram's limit."""
    if len(message) <= max_len:
        return [message]

    chunks = []
    lines = message.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_len and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def send_price_drop_alerts(db_path=None):
    """Check price tracker DB for recent price drops and send alert.

    Looks for a price_tracker module in execution/ and queries for
    unacknowledged alerts. If none found, logs and returns.

    Args:
        db_path: Optional path to price tracker SQLite DB.

    Returns:
        True if alerts were sent, False otherwise.
    """
    # Try to import price_tracker if it exists
    price_tracker_path = PROJECT_ROOT / "execution" / "price_tracker.py"
    if not price_tracker_path.exists():
        print("[alerts] price_tracker.py not found -- skipping DB alerts.", file=sys.stderr)
        return False

    import importlib.util
    spec = importlib.util.spec_from_file_location("price_tracker", price_tracker_path)
    price_tracker = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(price_tracker)
    except Exception as e:
        print(f"[alerts] Failed to load price_tracker: {e}", file=sys.stderr)
        return False

    # Look for a get_unacknowledged_alerts or similar function
    get_alerts_fn = getattr(price_tracker, "get_unacknowledged_alerts", None)
    if not get_alerts_fn:
        print("[alerts] price_tracker has no get_unacknowledged_alerts() -- skipping.",
              file=sys.stderr)
        return False

    try:
        alerts = get_alerts_fn(db_path=db_path) if db_path else get_alerts_fn()
    except Exception as e:
        print(f"[alerts] Error getting DB alerts: {e}", file=sys.stderr)
        return False

    if not alerts:
        print("[alerts] No unacknowledged price drop alerts.", file=sys.stderr)
        return False

    # Format the price drop alerts
    now = datetime.now()
    lines = [
        f"PRICE DROP ALERT -- {now.strftime('%Y-%m-%d %H:%M')}",
        "=" * 32,
        "",
    ]

    for i, alert in enumerate(alerts, 1):
        name = alert.get("name", "Unknown")
        old_price = alert.get("old_price", "?")
        new_price = alert.get("new_price", "?")
        asin = alert.get("asin", "")
        drop_pct = alert.get("drop_percent", "?")

        lines.append(f"{i}. {name}")
        lines.append(f"   ${old_price} -> ${new_price} ({drop_pct}% drop)")
        if asin:
            lines.append(f"   amazon.com/dp/{asin}")
        lines.append("")

    message = "\n".join(lines)
    return send_telegram_alert(message)


def _generate_test_message():
    """Generate a test alert message with sample data."""
    sample_buy = [
        {
            "name": "Widget Pro Max (TEST)",
            "profitability": {
                "buy_cost": 12.99,
                "sell_price": 29.99,
                "roi_percent": 45.2,
                "profit_per_unit": 8.50,
                "verdict": "BUY",
            },
            "amazon": {
                "asin": "B08TEST123",
                "sales_rank": 12500,
                "fba_seller_count": 4,
            },
        },
    ]
    sample_maybe = [
        {
            "name": "Gadget Lite (TEST)",
            "profitability": {
                "buy_cost": 8.50,
                "sell_price": 18.99,
                "roi_percent": 28.5,
                "profit_per_unit": 3.20,
                "verdict": "MAYBE",
            },
            "amazon": {
                "asin": "B08TEST456",
                "sales_rank": 45000,
            },
        },
    ]
    summary = {
        "total_analyzed": 25,
        "avg_roi_percent": 36.8,
        "avg_profit_per_unit": 5.85,
    }
    full_data = {
        "retailer": "Walmart",
        "source_url": "https://www.walmart.com/browse/clearance/test",
        "elapsed_seconds": 142,
    }

    return format_alert_message(sample_buy, sample_maybe, summary, full_data)


def main():
    parser = argparse.ArgumentParser(description="FBA sourcing alerts")
    parser.add_argument("--results", type=str, default=None,
                        help="Path to sourcing results JSON file")
    parser.add_argument("--method", type=str, default="telegram",
                        choices=["telegram", "email"],
                        help="Alert delivery method (default: telegram)")
    parser.add_argument("--db-alerts", action="store_true",
                        help="Send unacknowledged price drop alerts from DB")
    parser.add_argument("--test", action="store_true",
                        help="Send a test alert with sample data (dry run)")
    args = parser.parse_args()

    if args.test:
        message = _generate_test_message()
        print("[alerts] TEST MODE -- generated message:", file=sys.stderr)
        print(message)
        print("\n[alerts] Sending test alert...", file=sys.stderr)
        success = send_telegram_alert(message) if args.method == "telegram" \
            else _send_email_alert(message)
        sys.exit(0 if success else 1)

    if args.db_alerts:
        success = send_price_drop_alerts()
        sys.exit(0 if success else 1)

    if args.results:
        success = send_sourcing_alert(args.results, method=args.method)
        sys.exit(0 if success else 1)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
