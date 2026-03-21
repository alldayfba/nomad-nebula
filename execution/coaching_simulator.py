#!/usr/bin/env python3
"""
Script: coaching_simulator.py
Purpose: Generate annotated deal walkthrough reports and what-if analysis PDFs
         for Amazon FBA coaching students. Takes sourcing results and creates
         educational breakdowns showing WHY a deal is good/bad, with sensitivity
         analysis.
Inputs:  Subcommands: walkthrough, whatif, batch, reports
Outputs: PDF or text reports with annotated deal breakdowns and what-if tables
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )
except ImportError:
    print("[coaching_simulator] reportlab not installed. Install: pip install reportlab", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
DB_PATH = TMP_DIR / "price_tracker.db"

# ─── Color Palette ──────────────────────────────────────────────────────────
VERDICT_COLORS = {
    "BUY": colors.HexColor("#2E7D32"),      # green
    "MAYBE": colors.HexColor("#F9A825"),     # yellow/amber
    "SKIP": colors.HexColor("#C62828"),      # red
}
VERDICT_BG = {
    "BUY": colors.HexColor("#E8F5E9"),
    "MAYBE": colors.HexColor("#FFF8E1"),
    "SKIP": colors.HexColor("#FFEBEE"),
}

# ─── BSR Interpretation Ranges ──────────────────────────────────────────────
BSR_INTERPRETATIONS = [
    (1000, "Extremely fast seller — top 0.01% of the category. Sells many units daily."),
    (5000, "Very strong seller — high demand. Expect 8-20+ units/day."),
    (10000, "Good seller — consistent demand. Expect 3-8 units/day."),
    (25000, "Moderate seller — decent velocity. Expect 1-3 units/day."),
    (50000, "Slow-moderate — may take a few days per unit. Only worthwhile at high margins."),
    (100000, "Slow seller — a few units per week. Risky for capital tie-up."),
    (250000, "Very slow — may sit in FBA warehouse for weeks. Long-tail storage fee risk."),
    (500000, "Nearly dead listing — avoid unless extremely niche with huge margin."),
    (999999999, "Dead listing — essentially no organic sales. Do not source."),
]

# ─── Competition Explanations ───────────────────────────────────────────────
COMPETITION_EXPLANATIONS = {
    "LOW": (
        "1-3 FBA sellers. This is ideal — fewer sellers means a larger share of "
        "the Buy Box. You'll rotate into the Buy Box frequently, leading to "
        "consistent sales. This is the sweet spot for OA/RA."
    ),
    "MODERATE": (
        "4-7 FBA sellers. Acceptable but you'll share the Buy Box with others. "
        "Your share of sales decreases roughly proportionally to the seller count. "
        "Still profitable if margins are strong (30%+ ROI)."
    ),
    "HIGH": (
        "8-15 FBA sellers. Crowded listing — the Buy Box rotates among many sellers, "
        "so your share is small. Price wars are common. Only source if ROI > 50% "
        "to survive potential price drops."
    ),
    "SATURATED": (
        "15+ FBA sellers. The listing is saturated. Price erosion is almost certain. "
        "Even a great current margin will likely disappear within weeks as sellers "
        "undercut each other. Avoid."
    ),
    "HIGH_RISK": (
        "Amazon itself is selling on this listing. Amazon almost always holds the "
        "Buy Box when present. Your units will sit in the warehouse accumulating "
        "storage fees. Generally, avoid unless you can undercut Amazon's price "
        "(rare and risky)."
    ),
    "UNKNOWN": (
        "Competition data unavailable. Proceed with caution — manually check the "
        "listing on Amazon to count FBA sellers before committing capital."
    ),
}

# ─── Risk Explanations ──────────────────────────────────────────────────────
RISK_EXPLANATIONS = {
    "gating": (
        "This category requires Amazon approval (ungating) to sell. You'll need to "
        "provide invoices from authorized distributors showing purchase of 10+ units. "
        "Don't source until you've confirmed you're ungated in this category."
    ),
    "hazmat": (
        "This product contains keywords associated with hazardous materials. Hazmat "
        "items require additional documentation and may have higher FBA fees. Check "
        "the actual product — some are false positives (e.g., 'battery-operated' vs "
        "loose batteries)."
    ),
    "ip_risk": (
        "This brand is known for filing intellectual property complaints against "
        "third-party sellers. Selling their products can result in listing removal, "
        "account warnings, or suspension. Generally avoid unless you have authorized "
        "distributor invoices."
    ),
    "multipack_mismatch": (
        "The retail and Amazon quantities don't match. This is one of the most common "
        "sourcing mistakes — you think you're getting a great deal, but you're comparing "
        "a single unit to a multi-pack (or vice versa). Double-check both listings."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

def init_db():
    """Initialize the coaching_reports table in SQLite."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coaching_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            report_type TEXT NOT NULL,
            products_count INTEGER NOT NULL DEFAULT 0,
            file_path TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def log_report(student_name, report_type, products_count, file_path):
    """Log a generated report to the database."""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO coaching_reports (student_name, report_type, products_count, file_path, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (student_name, report_type, products_count, str(file_path), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def list_reports():
    """List all generated reports."""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, student_name, report_type, products_count, file_path, created_at "
        "FROM coaching_reports ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# DEAL ANNOTATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_float(val, default=0.0):
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default


def _interpret_bsr(bsr):
    """Get educational interpretation of BSR value."""
    if not bsr or bsr <= 0:
        return "No BSR data available — cannot estimate sales velocity."
    for threshold, explanation in BSR_INTERPRETATIONS:
        if bsr <= threshold:
            return explanation
    return "Unknown BSR range."


def _get_competition_explanation(competition_score):
    """Get educational explanation for competition level."""
    return COMPETITION_EXPLANATIONS.get(competition_score, COMPETITION_EXPLANATIONS["UNKNOWN"])


def annotate_deal(product_data):
    """
    Takes a single product result from the sourcing pipeline and generates a
    structured educational breakdown.

    Args:
        product_data: dict from sourcing pipeline output (with profitability key)

    Returns:
        dict with all annotation fields for the coaching report
    """
    prof = product_data.get("profitability", {})
    amazon = product_data.get("amazon_match", {})
    restrictions = product_data.get("restrictions", {})
    cost_breakdown = prof.get("cost_breakdown", {})

    name = product_data.get("name", "Unknown Product")
    asin = amazon.get("asin", product_data.get("asin", "N/A"))
    retailer = product_data.get("retailer", "Unknown")
    verdict = prof.get("verdict", "SKIP")

    # ── Buy Cost Breakdown ──────────────────────────────────────────────
    raw_cost = _safe_float(product_data.get("price", cost_breakdown.get("raw_buy_cost", 0)))
    gc_discount = _safe_float(cost_breakdown.get("gift_card_discount", 0))
    cashback = _safe_float(cost_breakdown.get("cashback_amount", 0))
    coupon = _safe_float(cost_breakdown.get("coupon_discount", 0))
    sales_tax = _safe_float(cost_breakdown.get("sales_tax", 0))
    effective_cost = _safe_float(prof.get("effective_buy_cost", raw_cost))

    buy_cost_steps = [
        ("Raw retail price", raw_cost),
        ("Gift card discount", -gc_discount if gc_discount else 0),
        ("Cashback (Rakuten/Ibotta)", -cashback if cashback else 0),
        ("Coupon / promo discount", -coupon if coupon else 0),
        ("Sales tax", sales_tax),
        ("= Effective buy cost", effective_cost),
    ]

    # ── Fee Breakdown ───────────────────────────────────────────────────
    amazon_price = _safe_float(amazon.get("price", prof.get("sell_price", 0)))
    referral_fee = _safe_float(prof.get("referral_fee", amazon_price * 0.15))
    fba_fee = _safe_float(prof.get("fba_fee", 5.0))
    prep_cost = _safe_float(prof.get("prep_cost", 0.30))
    storage_fee = _safe_float(prof.get("storage_fee", 0.10))

    fee_steps = [
        ("Referral fee (% of sale price)", referral_fee),
        ("FBA fulfillment fee", fba_fee),
        ("Prep cost (label + poly bag)", prep_cost),
        ("Monthly storage (est.)", storage_fee),
        ("= Total fees", referral_fee + fba_fee + prep_cost + storage_fee),
    ]

    # ── Profit Walkthrough ──────────────────────────────────────────────
    total_fees = referral_fee + fba_fee + prep_cost + storage_fee
    profit = amazon_price - effective_cost - total_fees
    roi = (profit / effective_cost * 100) if effective_cost > 0 else 0

    profit_steps = [
        ("Amazon sell price", amazon_price),
        ("- Effective buy cost", effective_cost),
        ("- Total Amazon fees", total_fees),
        ("= Net profit per unit", round(profit, 2)),
        ("ROI", f"{roi:.1f}%"),
    ]

    # ── Competition Analysis ────────────────────────────────────────────
    competition_score = prof.get("competition_score", "UNKNOWN")
    fba_sellers = amazon.get("fba_seller_count", "?")
    amazon_on_listing = amazon.get("amazon_on_listing", False)

    # ── BSR Interpretation ──────────────────────────────────────────────
    bsr = amazon.get("sales_rank", product_data.get("sales_rank"))
    bsr_value = _safe_float(bsr, 0)
    category = amazon.get("category", product_data.get("category", ""))

    # ── Risk Assessment ─────────────────────────────────────────────────
    risks = []
    if restrictions.get("is_gated"):
        risks.append(("Gating", RISK_EXPLANATIONS["gating"]))
    if restrictions.get("hazmat_risk"):
        risks.append(("Hazmat", RISK_EXPLANATIONS["hazmat"]))
    if restrictions.get("ip_risk"):
        risks.append(("IP Risk", RISK_EXPLANATIONS["ip_risk"]))
    multipack = product_data.get("multipack", {})
    if multipack.get("multipack_mismatch"):
        risks.append(("Multi-pack Mismatch", RISK_EXPLANATIONS["multipack_mismatch"]))

    # ── Final Verdict Reasoning ─────────────────────────────────────────
    verdict_reasons = []
    if verdict == "BUY":
        if roi >= 50:
            verdict_reasons.append(f"Strong ROI of {roi:.1f}% — well above the 30% minimum threshold")
        elif roi >= 30:
            verdict_reasons.append(f"Acceptable ROI of {roi:.1f}% — meets the 30% minimum threshold")
        if profit >= 5:
            verdict_reasons.append(f"Solid per-unit profit of ${profit:.2f}")
        if competition_score in ("LOW", "MODERATE"):
            verdict_reasons.append(f"Competition is {competition_score.lower()} — good Buy Box share expected")
        if bsr_value and bsr_value < 50000:
            verdict_reasons.append(f"BSR of {int(bsr_value):,} indicates consistent demand")
    elif verdict == "MAYBE":
        if roi < 30:
            verdict_reasons.append(f"ROI of {roi:.1f}% is below ideal — look for a lower buy cost")
        if competition_score in ("HIGH", "SATURATED"):
            verdict_reasons.append(f"Competition is {competition_score.lower()} — price erosion risk")
        if risks:
            verdict_reasons.append(f"{len(risks)} risk flag(s) detected — review before committing")
        if not verdict_reasons:
            verdict_reasons.append("Marginal deal — proceed only if you can lower your buy cost")
    else:  # SKIP
        if roi < 15:
            verdict_reasons.append(f"ROI of {roi:.1f}% is too low — minimum viable is 30%")
        if profit < 3:
            verdict_reasons.append(f"Per-unit profit of ${profit:.2f} is too thin for FBA")
        if competition_score in ("SATURATED", "HIGH_RISK"):
            verdict_reasons.append(f"Competition level ({competition_score}) makes this unsellable")
        if bsr_value and bsr_value > 200000:
            verdict_reasons.append(f"BSR of {int(bsr_value):,} is too high — item barely sells")
        if not verdict_reasons:
            verdict_reasons.append("Deal does not meet minimum sourcing criteria")

    return {
        "name": name,
        "asin": asin,
        "retailer": retailer,
        "verdict": verdict,
        "buy_cost_steps": buy_cost_steps,
        "fee_steps": fee_steps,
        "profit_steps": profit_steps,
        "amazon_price": amazon_price,
        "effective_cost": effective_cost,
        "profit": round(profit, 2),
        "roi": round(roi, 1),
        "total_fees": round(total_fees, 2),
        "competition_score": competition_score,
        "competition_explanation": _get_competition_explanation(competition_score),
        "fba_sellers": fba_sellers,
        "amazon_on_listing": amazon_on_listing,
        "bsr": int(bsr_value) if bsr_value else None,
        "bsr_interpretation": _interpret_bsr(bsr_value),
        "category": category,
        "risks": risks,
        "verdict_reasons": verdict_reasons,
        "raw_data": product_data,
    }


def generate_what_if(product_data, scenarios=None):
    """
    Generate what-if sensitivity analysis for a product.

    Args:
        product_data: dict from sourcing pipeline (or annotated deal)
        scenarios: optional list of custom scenario dicts. If None, uses defaults.

    Returns:
        list of scenario result dicts with keys:
            scenario, buy_cost, amazon_price, profit, roi, verdict
    """
    prof = product_data.get("profitability", {})
    amazon = product_data.get("amazon_match", {})

    base_buy = _safe_float(prof.get("effective_buy_cost", product_data.get("price", 0)))
    base_amazon = _safe_float(amazon.get("price", prof.get("sell_price", 0)))

    referral_fee = _safe_float(prof.get("referral_fee", base_amazon * 0.15))
    fba_fee = _safe_float(prof.get("fba_fee", 5.0))
    prep_cost = _safe_float(prof.get("prep_cost", 0.30))
    storage_fee = _safe_float(prof.get("storage_fee", 0.10))

    # Recalculate referral fee ratio for scaling
    ref_rate = (referral_fee / base_amazon) if base_amazon > 0 else 0.15

    def calc_scenario(label, buy_cost, sell_price):
        ref_fee = sell_price * ref_rate
        total_fees = ref_fee + fba_fee + prep_cost + storage_fee
        profit = sell_price - buy_cost - total_fees
        roi = (profit / buy_cost * 100) if buy_cost > 0 else 0
        if roi >= 30 and profit >= 3:
            verdict = "BUY"
        elif roi >= 15 and profit >= 1:
            verdict = "MAYBE"
        else:
            verdict = "SKIP"
        return {
            "scenario": label,
            "buy_cost": round(buy_cost, 2),
            "amazon_price": round(sell_price, 2),
            "profit": round(profit, 2),
            "roi": round(roi, 1),
            "verdict": verdict,
        }

    results = [calc_scenario("Base case", base_buy, base_amazon)]

    if scenarios:
        for s in scenarios:
            bc = s.get("buy_cost", base_buy)
            ap = s.get("amazon_price", base_amazon)
            results.append(calc_scenario(s.get("label", "Custom"), bc, ap))
    else:
        # Default scenarios
        results.append(calc_scenario("Buy cost +10%", base_buy * 1.10, base_amazon))
        results.append(calc_scenario("Buy cost +20%", base_buy * 1.20, base_amazon))
        results.append(calc_scenario("Buy cost -10%", base_buy * 0.90, base_amazon))
        results.append(calc_scenario("Amazon price -10%", base_buy, base_amazon * 0.90))
        results.append(calc_scenario("Amazon price -20%", base_buy, base_amazon * 0.80))
        results.append(calc_scenario("Amazon price -30%", base_buy, base_amazon * 0.70))

        # Competition scenarios (more sellers = lower price assumption)
        results.append(calc_scenario("Competition +3 sellers (est. -5%)", base_buy, base_amazon * 0.95))
        results.append(calc_scenario("Competition +7 sellers (est. -15%)", base_buy, base_amazon * 0.85))

        # Break-even calculation
        total_fixed_fees = fba_fee + prep_cost + storage_fee
        # break-even: sell_price - buy_cost - (sell_price * ref_rate) - fixed_fees = 0
        # sell_price * (1 - ref_rate) - buy_cost - fixed_fees = 0
        # buy_cost = sell_price * (1 - ref_rate) - fixed_fees
        breakeven_buy = base_amazon * (1 - ref_rate) - total_fixed_fees
        if breakeven_buy > 0:
            results.append({
                "scenario": "Break-even buy cost",
                "buy_cost": round(breakeven_buy, 2),
                "amazon_price": round(base_amazon, 2),
                "profit": 0.00,
                "roi": 0.0,
                "verdict": "---",
            })

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_text_report(annotated_deals):
    """Generate plain text report for terminal or Telegram output."""
    lines = []
    lines.append("=" * 70)
    lines.append("  AMAZON FBA COACHING — DEAL WALKTHROUGH REPORT")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    # Summary stats
    buys = [d for d in annotated_deals if d["verdict"] == "BUY"]
    maybes = [d for d in annotated_deals if d["verdict"] == "MAYBE"]
    skips = [d for d in annotated_deals if d["verdict"] == "SKIP"]

    lines.append(f"\n  Summary: {len(buys)} BUY | {len(maybes)} MAYBE | {len(skips)} SKIP")
    lines.append(f"  Total deals analyzed: {len(annotated_deals)}")

    if buys:
        best = max(buys, key=lambda d: d["roi"])
        lines.append(f"  Best deal: {best['name'][:40]}... — {best['roi']}% ROI")
    lines.append("")

    for i, deal in enumerate(annotated_deals, 1):
        lines.append("-" * 70)
        lines.append(f"  DEAL #{i}: [{deal['verdict']}] {deal['name'][:55]}")
        lines.append(f"  ASIN: {deal['asin']} | Retailer: {deal['retailer']}")
        lines.append("-" * 70)

        # Buy cost breakdown
        lines.append("\n  BUY COST BREAKDOWN:")
        for label, value in deal["buy_cost_steps"]:
            if isinstance(value, (int, float)):
                lines.append(f"    {label:<35} ${value:>8.2f}")
            else:
                lines.append(f"    {label:<35} {value:>9}")

        # Fee breakdown
        lines.append("\n  FEE BREAKDOWN:")
        for label, value in deal["fee_steps"]:
            lines.append(f"    {label:<35} ${value:>8.2f}")

        # Profit walkthrough
        lines.append("\n  PROFIT CALCULATION:")
        for label, value in deal["profit_steps"]:
            if isinstance(value, str):
                lines.append(f"    {label:<35} {value:>9}")
            else:
                lines.append(f"    {label:<35} ${value:>8.2f}")

        # Competition
        lines.append(f"\n  COMPETITION: {deal['competition_score']} "
                      f"({deal['fba_sellers']} FBA sellers)")
        # Wrap explanation text
        expl = deal["competition_explanation"]
        while len(expl) > 65:
            split_at = expl.rfind(" ", 0, 65)
            if split_at == -1:
                split_at = 65
            lines.append(f"    {expl[:split_at]}")
            expl = expl[split_at:].strip()
        if expl:
            lines.append(f"    {expl}")

        # BSR
        bsr_display = f"{deal['bsr']:,}" if deal["bsr"] else "N/A"
        lines.append(f"\n  BSR: {bsr_display} ({deal['category'] or 'Unknown category'})")
        bsr_interp = deal["bsr_interpretation"]
        while len(bsr_interp) > 65:
            split_at = bsr_interp.rfind(" ", 0, 65)
            if split_at == -1:
                split_at = 65
            lines.append(f"    {bsr_interp[:split_at]}")
            bsr_interp = bsr_interp[split_at:].strip()
        if bsr_interp:
            lines.append(f"    {bsr_interp}")

        # Risks
        if deal["risks"]:
            lines.append(f"\n  RISK FLAGS ({len(deal['risks'])}):")
            for risk_name, risk_expl in deal["risks"]:
                lines.append(f"    [{risk_name}]")
                while len(risk_expl) > 63:
                    split_at = risk_expl.rfind(" ", 0, 63)
                    if split_at == -1:
                        split_at = 63
                    lines.append(f"      {risk_expl[:split_at]}")
                    risk_expl = risk_expl[split_at:].strip()
                if risk_expl:
                    lines.append(f"      {risk_expl}")
        else:
            lines.append("\n  RISK FLAGS: None detected")

        # Verdict
        lines.append(f"\n  VERDICT: {deal['verdict']}")
        for reason in deal["verdict_reasons"]:
            lines.append(f"    - {reason}")

        # What-if table
        what_if = generate_what_if(deal["raw_data"])
        lines.append("\n  WHAT-IF ANALYSIS:")
        lines.append(f"    {'Scenario':<35} {'Buy Cost':>9} {'Profit':>8} {'ROI':>7} {'Verdict':>8}")
        lines.append(f"    {'-'*35} {'-'*9} {'-'*8} {'-'*7} {'-'*8}")
        for s in what_if:
            lines.append(
                f"    {s['scenario']:<35} ${s['buy_cost']:>7.2f} "
                f"${s['profit']:>6.2f} {s['roi']:>5.1f}% {s['verdict']:>7}"
            )
        lines.append("")

    # Summary page
    lines.append("=" * 70)
    lines.append("  KEY LESSONS")
    lines.append("=" * 70)

    if buys:
        lines.append("\n  TOP BUY DEALS:")
        for d in sorted(buys, key=lambda x: x["roi"], reverse=True)[:5]:
            lines.append(f"    - {d['name'][:45]} | ROI: {d['roi']}% | Profit: ${d['profit']:.2f}")

    if skips:
        lines.append("\n  WHY THESE WERE SKIPPED:")
        for d in skips[:3]:
            reasons = "; ".join(d["verdict_reasons"][:2])
            lines.append(f"    - {d['name'][:45]}")
            lines.append(f"      Reason: {reasons}")

    lines.append("\n  REMEMBER:")
    lines.append("    1. Never source without checking competition AND BSR")
    lines.append("    2. Always verify multi-pack quantities match")
    lines.append("    3. A 50% ROI today can become 0% if price drops 20%")
    lines.append("    4. Stack discounts (gift cards + cashback + coupons) to lower buy cost")
    lines.append("    5. When in doubt, skip — there are always more deals")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def _get_styles():
    """Build custom paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontSize=26,
        spaceAfter=20,
        textColor=colors.HexColor("#1B5E20"),
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle",
        parent=styles["Normal"],
        fontSize=14,
        spaceAfter=10,
        textColor=colors.HexColor("#424242"),
    ))
    styles.add(ParagraphStyle(
        name="DealTitle",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=6,
        spaceBefore=10,
    ))
    styles.add(ParagraphStyle(
        name="SectionHead",
        parent=styles["Heading3"],
        fontSize=11,
        spaceAfter=4,
        spaceBefore=8,
        textColor=colors.HexColor("#1565C0"),
    ))
    styles.add(ParagraphStyle(
        name="BodySmall",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=3,
        leading=12,
    ))
    styles.add(ParagraphStyle(
        name="VerdictBuy",
        parent=styles["Normal"],
        fontSize=13,
        textColor=VERDICT_COLORS["BUY"],
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="VerdictMaybe",
        parent=styles["Normal"],
        fontSize=13,
        textColor=VERDICT_COLORS["MAYBE"],
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="VerdictSkip",
        parent=styles["Normal"],
        fontSize=13,
        textColor=VERDICT_COLORS["SKIP"],
        spaceAfter=4,
    ))

    return styles


def _build_step_table(steps, title_color=colors.HexColor("#1565C0")):
    """Build a formatted table from step tuples [(label, value), ...]."""
    table_data = []
    for label, value in steps:
        if isinstance(value, str):
            table_data.append([label, value])
        else:
            table_data.append([label, f"${value:.2f}"])

    t = Table(table_data, colWidths=[3.5 * inch, 1.5 * inch])
    style_cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#424242")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]
    # Bold the last row (total/result)
    style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
    style_cmds.append(("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.grey))
    t.setStyle(TableStyle(style_cmds))
    return t


def _build_whatif_table(scenarios):
    """Build the what-if analysis table for the PDF."""
    header = ["Scenario", "Buy Cost", "Profit", "ROI", "Verdict"]
    data = [header]
    for s in scenarios:
        data.append([
            s["scenario"],
            f"${s['buy_cost']:.2f}",
            f"${s['profit']:.2f}",
            f"{s['roi']:.1f}%",
            s["verdict"],
        ])

    t = Table(data, colWidths=[2.5 * inch, 0.9 * inch, 0.8 * inch, 0.7 * inch, 0.7 * inch])
    style_cmds = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3F2FD")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BDBDBD")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]
    # Color-code verdict column
    for i, s in enumerate(scenarios, 1):
        v = s["verdict"]
        if v in VERDICT_BG:
            style_cmds.append(("BACKGROUND", (4, i), (4, i), VERDICT_BG[v]))
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), VERDICT_COLORS[v]))

    t.setStyle(TableStyle(style_cmds))
    return t


def generate_pdf_report(annotated_deals, output_path, student_name=None):
    """
    Generate a formatted PDF report with annotated deal breakdowns.

    Args:
        annotated_deals: list of annotated deal dicts from annotate_deal()
        output_path: path to write PDF
        student_name: optional student name for the cover page
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _get_styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    story = []

    # ── Cover Page ──────────────────────────────────────────────────────
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("Amazon FBA Deal Walkthrough", styles["CoverTitle"]))
    story.append(Paragraph("Coaching Report — Annotated Analysis", styles["CoverSubtitle"]))
    story.append(Spacer(1, 0.3 * inch))

    date_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(f"Date: {date_str}", styles["CoverSubtitle"]))
    if student_name:
        story.append(Paragraph(f"Student: {student_name}", styles["CoverSubtitle"]))

    buys = [d for d in annotated_deals if d["verdict"] == "BUY"]
    maybes = [d for d in annotated_deals if d["verdict"] == "MAYBE"]
    skips = [d for d in annotated_deals if d["verdict"] == "SKIP"]

    story.append(Spacer(1, 0.5 * inch))
    summary_data = [
        ["Total Deals Analyzed", str(len(annotated_deals))],
        ["BUY", str(len(buys))],
        ["MAYBE", str(len(maybes))],
        ["SKIP", str(len(skips))],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 1.5 * inch])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (1, 1), (1, 1), VERDICT_COLORS["BUY"]),
        ("TEXTCOLOR", (1, 2), (1, 2), VERDICT_COLORS["MAYBE"]),
        ("TEXTCOLOR", (1, 3), (1, 3), VERDICT_COLORS["SKIP"]),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
    ]))
    story.append(summary_table)

    if buys:
        best = max(buys, key=lambda d: d["roi"])
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph(
            f"Best Deal: {best['name'][:50]} — {best['roi']}% ROI, ${best['profit']:.2f} profit",
            styles["BodySmall"],
        ))

    story.append(PageBreak())

    # ── Individual Deal Pages ───────────────────────────────────────────
    for i, deal in enumerate(annotated_deals, 1):
        verdict = deal["verdict"]
        verdict_style = f"Verdict{verdict.capitalize()}" if verdict in ("Buy", "Maybe", "Skip") else None
        # Map to correct style name
        if verdict == "BUY":
            verdict_style = "VerdictBuy"
        elif verdict == "MAYBE":
            verdict_style = "VerdictMaybe"
        else:
            verdict_style = "VerdictSkip"

        # Deal header
        story.append(Paragraph(
            f"Deal #{i}: {deal['name'][:60]}",
            styles["DealTitle"],
        ))
        story.append(Paragraph(
            f"ASIN: {deal['asin']}  |  Retailer: {deal['retailer']}  |  "
            f"Verdict: <b>{verdict}</b>",
            styles[verdict_style],
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=VERDICT_COLORS.get(verdict, colors.grey)))
        story.append(Spacer(1, 0.1 * inch))

        # Buy cost breakdown
        story.append(Paragraph("Buy Cost Breakdown", styles["SectionHead"]))
        story.append(_build_step_table(deal["buy_cost_steps"]))
        story.append(Spacer(1, 0.1 * inch))

        # Fee breakdown
        story.append(Paragraph("Amazon Fee Breakdown", styles["SectionHead"]))
        story.append(_build_step_table(deal["fee_steps"]))
        story.append(Spacer(1, 0.1 * inch))

        # Profit calculation
        story.append(Paragraph("Profit Calculation", styles["SectionHead"]))
        story.append(_build_step_table(deal["profit_steps"]))
        story.append(Spacer(1, 0.1 * inch))

        # Competition
        story.append(Paragraph(
            f"Competition: {deal['competition_score']} ({deal['fba_sellers']} FBA sellers)",
            styles["SectionHead"],
        ))
        story.append(Paragraph(deal["competition_explanation"], styles["BodySmall"]))
        story.append(Spacer(1, 0.05 * inch))

        # BSR
        bsr_display = f"{deal['bsr']:,}" if deal["bsr"] else "N/A"
        story.append(Paragraph(
            f"BSR: {bsr_display} ({deal['category'] or 'Unknown'})",
            styles["SectionHead"],
        ))
        story.append(Paragraph(deal["bsr_interpretation"], styles["BodySmall"]))
        story.append(Spacer(1, 0.05 * inch))

        # Risk flags
        if deal["risks"]:
            story.append(Paragraph(f"Risk Flags ({len(deal['risks'])})", styles["SectionHead"]))
            for risk_name, risk_expl in deal["risks"]:
                story.append(Paragraph(
                    f"<b>{risk_name}:</b> {risk_expl}",
                    styles["BodySmall"],
                ))
        else:
            story.append(Paragraph("Risk Flags: None detected", styles["SectionHead"]))

        # Verdict reasoning
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Verdict: {verdict}", styles[verdict_style]))
        for reason in deal["verdict_reasons"]:
            story.append(Paragraph(f"  - {reason}", styles["BodySmall"]))

        # What-if table
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("What-If Sensitivity Analysis", styles["SectionHead"]))
        what_if = generate_what_if(deal["raw_data"])
        story.append(_build_whatif_table(what_if))

        story.append(PageBreak())

    # ── Summary Page ────────────────────────────────────────────────────
    story.append(Paragraph("Summary & Key Lessons", styles["CoverTitle"]))
    story.append(Spacer(1, 0.3 * inch))

    if buys:
        story.append(Paragraph("Best Deals (BUY)", styles["SectionHead"]))
        for d in sorted(buys, key=lambda x: x["roi"], reverse=True)[:5]:
            story.append(Paragraph(
                f"<b>{d['name'][:50]}</b> — ROI: {d['roi']}%, "
                f"Profit: ${d['profit']:.2f}, ASIN: {d['asin']}",
                styles["BodySmall"],
            ))
        story.append(Spacer(1, 0.15 * inch))

    if maybes:
        story.append(Paragraph("Borderline Deals (MAYBE)", styles["SectionHead"]))
        for d in sorted(maybes, key=lambda x: x["roi"], reverse=True)[:3]:
            story.append(Paragraph(
                f"<b>{d['name'][:50]}</b> — ROI: {d['roi']}%, "
                f"Profit: ${d['profit']:.2f}. Needs: {'; '.join(d['verdict_reasons'][:2])}",
                styles["BodySmall"],
            ))
        story.append(Spacer(1, 0.15 * inch))

    if skips:
        story.append(Paragraph("Worst Deals (SKIP) — Learn From These", styles["SectionHead"]))
        for d in sorted(skips, key=lambda x: x["roi"])[:3]:
            story.append(Paragraph(
                f"<b>{d['name'][:50]}</b> — ROI: {d['roi']}%. "
                f"Why: {'; '.join(d['verdict_reasons'][:2])}",
                styles["BodySmall"],
            ))
        story.append(Spacer(1, 0.15 * inch))

    # Key lessons
    story.append(Paragraph("Key Takeaways", styles["SectionHead"]))
    lessons = [
        "Never source without checking both competition (FBA seller count) AND demand (BSR).",
        "Always verify multi-pack quantities match between retail and Amazon listings.",
        "A 50% ROI today can become 0% if the Amazon price drops 20% — check the what-if table.",
        "Stack discounts: gift cards + cashback + coupons. Every dollar saved is pure profit.",
        "When in doubt, skip. Capital preservation beats chasing marginal deals.",
    ]
    for lesson in lessons:
        story.append(Paragraph(f"  - {lesson}", styles["BodySmall"]))

    # Build PDF
    doc.build(story)
    return str(output_path)


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def process_sourcing_results(results_json_path, max_buy=5, max_maybe=3, max_skip=2):
    """
    Load sourcing results file, annotate all deals, and select the best
    educational mix.

    Args:
        results_json_path: path to JSON from sourcing pipeline
        max_buy: max BUY deals to include (default 5)
        max_maybe: max MAYBE deals to include (default 3)
        max_skip: max SKIP deals to include for educational contrast (default 2)

    Returns:
        list of annotated deal dicts (selected subset)
    """
    with open(results_json_path) as f:
        data = json.load(f)

    products = data.get("products", data if isinstance(data, list) else [])

    # Annotate all deals
    all_annotated = []
    for product in products:
        try:
            annotated = annotate_deal(product)
            all_annotated.append(annotated)
        except Exception as e:
            print(f"[coaching_simulator] Warning: failed to annotate deal: {e}", file=sys.stderr)
            continue

    if not all_annotated:
        print("[coaching_simulator] No deals to annotate.", file=sys.stderr)
        return []

    # Separate by verdict
    buys = sorted([d for d in all_annotated if d["verdict"] == "BUY"],
                  key=lambda x: x["roi"], reverse=True)
    maybes = sorted([d for d in all_annotated if d["verdict"] == "MAYBE"],
                    key=lambda x: x["roi"], reverse=True)
    skips = sorted([d for d in all_annotated if d["verdict"] == "SKIP"],
                   key=lambda x: x["roi"])

    # Select educational mix
    selected = buys[:max_buy] + maybes[:max_maybe] + skips[:max_skip]

    print(f"[coaching_simulator] Annotated {len(all_annotated)} deals. "
          f"Selected {len(selected)} for report "
          f"({len(buys[:max_buy])} BUY, {len(maybes[:max_maybe])} MAYBE, "
          f"{len(skips[:max_skip])} SKIP).", file=sys.stderr)

    return selected


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_walkthrough(args):
    """Handle the 'walkthrough' subcommand."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    annotated = process_sourcing_results(str(input_path))
    if not annotated:
        print("[error] No deals to process.", file=sys.stderr)
        sys.exit(1)

    if args.text:
        report = generate_text_report(annotated)
        print(report)
    else:
        output = args.output or str(TMP_DIR / f"walkthrough_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        pdf_path = generate_pdf_report(annotated, output)
        log_report(None, "deal_walkthrough", len(annotated), pdf_path)
        print(f"[coaching_simulator] PDF report saved: {pdf_path}", file=sys.stderr)
        print(pdf_path)


def cmd_whatif(args):
    """Handle the 'whatif' subcommand for single product analysis."""
    # Build a minimal product_data dict from CLI args
    product_data = {
        "name": f"ASIN {args.asin}",
        "asin": args.asin,
        "price": args.buy_cost,
        "amazon_match": {
            "asin": args.asin,
            "price": args.amazon_price,
        },
        "profitability": {
            "effective_buy_cost": args.buy_cost,
            "sell_price": args.amazon_price,
            "referral_fee": args.amazon_price * 0.15,
            "fba_fee": 5.0,
            "prep_cost": 0.30,
            "storage_fee": 0.10,
        },
    }

    scenarios = generate_what_if(product_data)

    # Print table
    print(f"\nWhat-If Analysis: ASIN {args.asin}")
    print(f"Base buy cost: ${args.buy_cost:.2f} | Amazon price: ${args.amazon_price:.2f}")
    print()
    print(f"{'Scenario':<40} {'Buy Cost':>9} {'Profit':>8} {'ROI':>7} {'Verdict':>8}")
    print(f"{'-'*40} {'-'*9} {'-'*8} {'-'*7} {'-'*8}")

    for s in scenarios:
        print(f"{s['scenario']:<40} ${s['buy_cost']:>7.2f} "
              f"${s['profit']:>6.2f} {s['roi']:>5.1f}% {s['verdict']:>7}")

    print()
    log_report(None, "what_if", 1, f"CLI: ASIN {args.asin}")


def cmd_batch(args):
    """Handle the 'batch' subcommand for student-labeled reports."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    annotated = process_sourcing_results(str(input_path))
    if not annotated:
        print("[error] No deals to process.", file=sys.stderr)
        sys.exit(1)

    output = args.output or str(
        TMP_DIR / f"coaching_{args.student.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    pdf_path = generate_pdf_report(annotated, output, student_name=args.student)
    log_report(args.student, "batch", len(annotated), pdf_path)
    print(f"[coaching_simulator] Student report saved: {pdf_path}", file=sys.stderr)
    print(pdf_path)


def cmd_reports(args):
    """Handle the 'reports' subcommand — list generated reports."""
    reports = list_reports()
    if not reports:
        print("No reports generated yet.")
        return

    print(f"\n{'ID':>4}  {'Student':<20} {'Type':<18} {'Products':>8}  {'Date':<20}  Path")
    print(f"{'-'*4}  {'-'*20} {'-'*18} {'-'*8}  {'-'*20}  {'-'*30}")
    for r in reports:
        student = r["student_name"] or "—"
        print(f"{r['id']:>4}  {student:<20} {r['report_type']:<18} "
              f"{r['products_count']:>8}  {r['created_at']:<20}  {r['file_path']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Amazon FBA Coaching Simulator — Deal walkthroughs and what-if analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s walkthrough --input results.json --output report.pdf
  %(prog)s walkthrough --input results.json --text
  %(prog)s whatif --asin B08XYZ123 --buy-cost 15 --amazon-price 35
  %(prog)s batch --input results.json --student "John Doe" --output coaching_report.pdf
  %(prog)s reports
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # ── walkthrough ─────────────────────────────────────────────────────
    walk_parser = subparsers.add_parser("walkthrough", help="Full annotated deal walkthrough")
    walk_parser.add_argument("--input", required=True, help="Path to sourcing results JSON")
    walk_parser.add_argument("--output", help="Output PDF path (default: .tmp/sourcing/)")
    walk_parser.add_argument("--text", action="store_true", help="Output as text instead of PDF")

    # ── whatif ──────────────────────────────────────────────────────────
    whatif_parser = subparsers.add_parser("whatif", help="Single product what-if analysis")
    whatif_parser.add_argument("--asin", required=True, help="Amazon ASIN")
    whatif_parser.add_argument("--buy-cost", type=float, required=True, help="Your buy cost ($)")
    whatif_parser.add_argument("--amazon-price", type=float, required=True, help="Amazon sell price ($)")

    # ── batch ───────────────────────────────────────────────────────────
    batch_parser = subparsers.add_parser("batch", help="Student-labeled coaching report")
    batch_parser.add_argument("--input", required=True, help="Path to sourcing results JSON")
    batch_parser.add_argument("--student", required=True, help="Student name")
    batch_parser.add_argument("--output", help="Output PDF path")

    # ── reports ─────────────────────────────────────────────────────────
    subparsers.add_parser("reports", help="List generated reports")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Ensure tmp dir exists
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "walkthrough":
        cmd_walkthrough(args)
    elif args.command == "whatif":
        cmd_whatif(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "reports":
        cmd_reports(args)


if __name__ == "__main__":
    main()
