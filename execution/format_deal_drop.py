#!/usr/bin/env python3
"""
Script: format_deal_drop.py
Purpose: Convert sourcing results JSON →
         (1) IC-style deal drop CSV (Inner Circle Approved Products sheet format)
         (2) Discord-formatted deal drop messages (ready to paste into channel)

IC columns:
  Image | Product Name | ASIN | Source URL | Cost Price | Sale Price |
  Profit | ROI | Coupons | VA Comments

Discord output: one @everyone block per product, with bold formatting,
  emoji structure, financials, market intel, discount stack, and links.

Usage:
  python execution/format_deal_drop.py --input .tmp/sourcing/results.json
  python execution/format_deal_drop.py --input .tmp/sourcing/results.json --discord
  python execution/format_deal_drop.py --input .tmp/sourcing/results.json --min-verdict BUY
  python execution/format_deal_drop.py --input .tmp/sourcing/results.json --output /path/to/out.csv
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

IC_HEADERS = [
    "Image",
    "Product Name",
    "ASIN",
    "Source URL",
    "Cost Price",
    "Sale Price",
    "Profit",
    "ROI",
    "Coupons",
    "VA Comments",
]

VERDICT_RANK = {"BUY": 0, "MAYBE": 1}


def _image_url(asin):
    """Return standard Amazon product thumbnail URL for an ASIN."""
    if not asin:
        return ""
    return f"https://images.amazon.com/images/P/{asin}.jpg"


def _format_coupons(prof):
    """Build a human-readable coupons string from profitability dict."""
    parts = []
    code = prof.get("coupon_code_used")
    pct = prof.get("coupon_percent_applied", 0)
    gc = prof.get("gift_card_discount", 0)
    cashback = prof.get("cashback_percent", 0)

    if code and pct:
        parts.append(f"{code} ({pct:.0f}% off)")
    elif pct:
        parts.append(f"{pct:.0f}% coupon")

    if gc and gc > 0:
        parts.append(f"{gc:.0f}% GC")

    if cashback and cashback > 0:
        parts.append(f"{cashback:.0f}% cashback")

    return " + ".join(parts) if parts else ""


def _va_comments(product, prof):
    """Auto-generate VA Comments from key metrics."""
    verdict = prof.get("verdict", "")
    roi = prof.get("roi_percent")
    profit = prof.get("profit_per_unit")
    sellers = product.get("amazon", {}).get("fba_seller_count")
    monthly_sales = prof.get("estimated_monthly_sales")
    fbm = prof.get("fbm_mode", False)

    parts = [verdict]

    if roi is not None:
        parts.append(f"{roi:.0f}% ROI")
    if profit is not None:
        parts.append(f"${profit:.2f} profit")
    if sellers is not None:
        parts.append(f"{sellers} FBA seller{'s' if sellers != 1 else ''}")
    if monthly_sales is not None:
        k = monthly_sales / 1000
        parts.append(f"~{k:.1f}k/mo sales" if k >= 1 else f"~{monthly_sales}/mo sales")
    if fbm:
        parts.append("FBM")

    return " | ".join(parts)


def _product_to_ic_row(product):
    """Convert a product dict → list of IC column values."""
    prof = product.get("profitability", {})
    amazon = product.get("amazon", {})

    asin = amazon.get("asin", "")
    product_name = product.get("name", "") or amazon.get("title", "")
    source_url = product.get("source_url", "") or product.get("url", "") or product.get("retail_url", "")
    buy_cost = prof.get("buy_cost")
    sell_price = prof.get("sell_price")
    profit = prof.get("profit_per_unit")
    roi = prof.get("roi_percent")

    def fmt_dollar(val):
        return f"${val:.2f}" if val is not None else ""

    def fmt_pct(val):
        return f"{val:.1f}%" if val is not None else ""

    return [
        _image_url(asin),
        product_name,
        asin,
        source_url,
        fmt_dollar(buy_cost),
        fmt_dollar(sell_price),
        fmt_dollar(profit),
        fmt_pct(roi),
        _format_coupons(prof),
        _va_comments(product, prof),
    ]


DIVIDER = "▬" * 32


def _format_discord_message(product):
    """Build a single Discord deal drop message for one product.

    Uses Discord markdown: **bold**, `code`, > blockquote.
    Returns a string ready to paste into a Discord channel.
    """
    prof = product.get("profitability", {})
    amazon = product.get("amazon", {})

    name = product.get("name", "") or amazon.get("title", "Unknown Product")
    asin = amazon.get("asin", "")
    source_url = product.get("source_url", "") or product.get("url", "") or product.get("retail_url", "")
    amazon_url = f"https://www.amazon.com/dp/{asin}" if asin else ""

    buy_cost = prof.get("buy_cost")
    sell_price = prof.get("sell_price")
    profit = prof.get("profit_per_unit")
    roi = prof.get("roi_percent")
    monthly_profit = prof.get("estimated_monthly_profit")
    monthly_sales = prof.get("estimated_monthly_sales")
    bsr = amazon.get("sales_rank")
    bsr_category = amazon.get("category", "")
    fba_sellers = amazon.get("fba_seller_count")
    fbm = prof.get("fbm_mode", False)
    verdict = prof.get("verdict", "BUY")

    # Profit margin = profit / sell_price * 100
    margin = round(profit / sell_price * 100, 2) if profit and sell_price else None

    def d(val):
        return f"${val:.2f}" if val is not None else "—"

    def pct(val):
        return f"{val:.1f}%" if val is not None else "—"

    def fmt_bsr(val, cat):
        if val is None:
            return "—"
        s = f"#{val:,}"
        return f"{s} ({cat})" if cat else s

    def fmt_sales(val):
        if val is None:
            return "—"
        return f"~{val:,} units/mo"

    # ── Discount stack line ───────────────────────────────────────────────────
    coupons = _format_coupons(prof)

    # ── Notes / signal line ───────────────────────────────────────────────────
    notes_parts = []
    if verdict == "MAYBE":
        notes_parts.append("⚠️ MAYBE — review before buying")
    if fba_sellers is not None:
        notes_parts.append(f"{fba_sellers} FBA seller{'s' if fba_sellers != 1 else ''}")
    if fbm:
        notes_parts.append("FBM eligible (fragrance/hazmat)")
    if monthly_sales and monthly_sales > 500:
        notes_parts.append("high velocity")
    notes_line = " · ".join(notes_parts) if notes_parts else "Strong BUY signal"

    # ── Build message ─────────────────────────────────────────────────────────
    lines = [
        "@everyone",
        DIVIDER,
        f"🏷️ **{name}**",
        DIVIDER,
        "",
        "💸 **Financials**",
        f"> 🛒 **Buy:** {d(buy_cost)}  →  💰 **Sell:** {d(sell_price)}",
        f"> 📈 **Profit:** {d(profit)}  |  🧮 **Margin:** {pct(margin)}  |  📊 **ROI:** {pct(roi)}",
    ]

    if monthly_profit is not None:
        lines.append(f"> 💵 **Est. Monthly Profit:** {d(monthly_profit)}")

    lines += [
        "",
        "📊 **Market Intel**",
        f"> 📦 ASIN: `{asin}`",
        f"> 📉 BSR: {fmt_bsr(bsr, bsr_category)}",
        f"> 👥 FBA Sellers: {fba_sellers if fba_sellers is not None else '—'}",
        f"> 📈 Est. Sales: {fmt_sales(monthly_sales)}",
    ]

    if coupons:
        lines += [
            "",
            "🎟️ **Discount Stack**",
            f"> {coupons}",
        ]

    lines += [
        "",
        "📝 **Notes**",
        f"> {notes_line}",
        "",
        "🔗 **Links**",
    ]

    link_parts = []
    if source_url:
        link_parts.append(f"🛍️ [Buy Here]({source_url})")
    if amazon_url:
        link_parts.append(f"📦 [Amazon Listing]({amazon_url})")

    if link_parts:
        lines.append(f"> {' · '.join(link_parts)}")
    else:
        lines.append("> _(no links available)_")

    lines.append(DIVIDER)

    return "\n".join(lines)


def format_discord_drop(results_path, output_path=None, min_verdict="MAYBE"):
    """Convert results JSON to Discord-formatted deal drop messages.

    Args:
        results_path: Path to sourcing results JSON.
        output_path: Optional output .txt path. Defaults to .tmp/sourcing/<ts>-discord-drop.txt.
        min_verdict: "BUY" (BUY only) or "MAYBE" (BUY + MAYBE).

    Returns:
        Path to output .txt file, or None if no products.
    """
    results_path = Path(results_path)
    if not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        return None

    with open(results_path) as f:
        results = json.load(f)

    products = results.get("products", [])
    verdicts_allowed = {"BUY"} if min_verdict == "BUY" else {"BUY", "MAYBE"}
    actionable = [
        p for p in products
        if p.get("profitability", {}).get("verdict") in verdicts_allowed
    ]

    if not actionable:
        print(f"[discord-drop] No {'/'.join(sorted(verdicts_allowed))} products found.",
              file=sys.stderr)
        return None

    actionable.sort(key=lambda p: (
        VERDICT_RANK.get(p.get("profitability", {}).get("verdict", ""), 99),
        -(p.get("profitability", {}).get("roi_percent") or 0),
    ))

    if output_path is None:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(TMP_DIR / f"{ts}-discord-drop.txt")

    messages = [_format_discord_message(p) for p in actionable]
    content = "\n\n\n".join(messages)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    buy_count = sum(1 for p in actionable if p["profitability"]["verdict"] == "BUY")
    maybe_count = len(actionable) - buy_count
    print(f"[discord-drop] {len(actionable)} messages ({buy_count} BUY, {maybe_count} MAYBE)",
          file=sys.stderr)
    print(f"[discord-drop] Output: {output_path}", file=sys.stderr)

    # Print each message to stdout so it can be reviewed/piped
    print("\n" + "=" * 60)
    print("DISCORD MESSAGES — copy/paste each block into Discord:")
    print("=" * 60)
    for i, msg in enumerate(messages, 1):
        verdict = actionable[i - 1].get("profitability", {}).get("verdict", "")
        name = actionable[i - 1].get("name", "") or actionable[i - 1].get("amazon", {}).get("title", "")
        print(f"\n── Message {i}/{len(messages)} [{verdict}] {name[:50]} ──")
        print(msg)

    return output_path


def format_deal_drop(results_path, output_path=None, min_verdict="MAYBE", discord=False):
    """Convert results JSON to IC-style deal drop CSV (and optionally Discord messages).

    Args:
        results_path: Path to sourcing results JSON.
        output_path: Optional output CSV path. Defaults to .tmp/sourcing/<ts>-deal-drop.csv.
        min_verdict: Minimum verdict to include — "BUY" (BUY only) or "MAYBE" (BUY + MAYBE).
        discord: If True, also write a Discord-formatted .txt alongside the CSV.

    Returns:
        Path to output CSV, or None if no products to export.
    """
    results_path = Path(results_path)
    if not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        return None

    with open(results_path) as f:
        results = json.load(f)

    products = results.get("products", [])

    # Filter by verdict
    verdicts_allowed = {"BUY"} if min_verdict == "BUY" else {"BUY", "MAYBE"}
    actionable = [
        p for p in products
        if p.get("profitability", {}).get("verdict") in verdicts_allowed
    ]

    if not actionable:
        print(f"[deal-drop] No {'/'.join(sorted(verdicts_allowed))} products found. Nothing to export.",
              file=sys.stderr)
        return None

    # Sort: BUY first, then by ROI descending
    actionable.sort(key=lambda p: (
        VERDICT_RANK.get(p.get("profitability", {}).get("verdict", ""), 99),
        -(p.get("profitability", {}).get("roi_percent") or 0),
    ))

    # Determine output path
    if output_path is None:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(TMP_DIR / f"{ts}-deal-drop.csv")

    # Write CSV
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(IC_HEADERS)
        for product in actionable:
            writer.writerow(_product_to_ic_row(product))

    buy_count = sum(1 for p in actionable if p["profitability"]["verdict"] == "BUY")
    maybe_count = len(actionable) - buy_count

    print(f"[deal-drop] Wrote {len(actionable)} products ({buy_count} BUY, {maybe_count} MAYBE)",
          file=sys.stderr)
    print(f"[deal-drop] Output: {output_path}", file=sys.stderr)

    # Also write Discord messages if requested
    if discord:
        discord_path = output_path.replace(".csv", "-discord.txt")
        format_discord_drop(results_path, output_path=discord_path, min_verdict=min_verdict)

    # Print path to stdout for piping
    print(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Format sourcing results as IC-style deal drop CSV"
    )
    parser.add_argument("--input", required=True,
                        help="Path to results JSON (from calculate_fba_profitability.py)")
    parser.add_argument("--output", default=None,
                        help="Output CSV path (default: .tmp/sourcing/<ts>-deal-drop.csv)")
    parser.add_argument("--min-verdict", default="MAYBE", choices=["BUY", "MAYBE"],
                        help="Minimum verdict to include: BUY (only BUY) or MAYBE (BUY+MAYBE). "
                             "Default: MAYBE")
    parser.add_argument("--discord", action="store_true",
                        help="Also output Discord-formatted messages (.txt alongside CSV)")
    parser.add_argument("--discord-only", action="store_true",
                        help="Output Discord messages only (no CSV)")
    args = parser.parse_args()

    if args.discord_only:
        path = format_discord_drop(args.input, min_verdict=args.min_verdict)
    else:
        path = format_deal_drop(
            args.input,
            output_path=args.output,
            min_verdict=args.min_verdict,
            discord=args.discord,
        )
    if not path:
        sys.exit(1)


if __name__ == "__main__":
    main()
