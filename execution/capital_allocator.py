#!/usr/bin/env python3
"""
Script: capital_allocator.py
Purpose: Solve optimal capital allocation across BUY-verdict products to maximize
         expected profit within a fixed budget, respecting velocity and risk constraints.
Inputs:  subcommand (allocate | compare | simulate), --budget, --results,
         --max-per-product, --min-roi, --max-days-to-sell, --months (simulate only)
Outputs: JSON to stdout, progress to stderr
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ─── Allocation Constraints (defaults) ────────────────────────────────────────
DEFAULT_MAX_PER_PRODUCT = 20       # hard cap on units per ASIN
DEFAULT_MIN_ROI = 25.0             # skip products below this ROI %
DEFAULT_MAX_DAYS_TO_SELL = 90      # skip products estimated to take longer
MAX_DAYS_TO_SELL_CAP = 180         # absolute ceiling for estimated_days_to_sell
BUDGET_CONCENTRATION_CAP = 0.30    # no single product > 30% of total budget


# ─── Core helpers ─────────────────────────────────────────────────────────────

def compute_annualized_roi(roi_percent: float, monthly_sales: float,
                           units_to_buy: int) -> tuple[float, float]:
    """Compute annualized ROI and estimated days to sell.

    annualized_roi = roi_percent * (365 / days_to_sell)
    days_to_sell   = 30 / (monthly_sales / units_to_buy),  capped at MAX_DAYS_TO_SELL_CAP

    Returns (annualized_roi, est_days_to_sell).
    """
    if not monthly_sales or monthly_sales <= 0:
        return 0.0, float(MAX_DAYS_TO_SELL_CAP)

    raw_days = 30.0 / (monthly_sales / units_to_buy)
    est_days = min(raw_days, MAX_DAYS_TO_SELL_CAP)
    annualized = roi_percent * (365.0 / est_days) if est_days > 0 else 0.0
    return round(annualized, 1), round(est_days, 1)


def extract_product_fields(product: dict) -> dict | None:
    """Pull the relevant fields from a results.json product entry.

    Returns a flat dict ready for the allocation algo, or None if unusable.
    """
    prof = product.get("profitability", {})
    amz = product.get("amazon", {})

    verdict = prof.get("verdict", "SKIP")
    if verdict != "BUY":
        return None

    asin = amz.get("asin") or product.get("asin")
    name = product.get("name") or amz.get("title") or asin or "Unknown"
    buy_cost = prof.get("buy_cost")
    profit_per_unit = prof.get("profit_per_unit")
    roi_percent = prof.get("roi_percent")
    monthly_sales = prof.get("estimated_monthly_sales")
    deal_score = prof.get("deal_score", 0)

    # Skip if essential numbers are missing
    if not all([buy_cost, profit_per_unit is not None, roi_percent is not None]):
        return None
    if buy_cost <= 0:
        return None

    return {
        "asin": asin,
        "name": name,
        "buy_cost": float(buy_cost),
        "profit_per_unit": float(profit_per_unit),
        "roi_percent": float(roi_percent),
        "monthly_sales": float(monthly_sales) if monthly_sales else 1.0,
        "deal_score": deal_score,
    }


def compute_max_units(monthly_sales: float, max_per_product: int) -> int:
    """Determine max units to buy: min(monthly_sales * 2, 30, max_per_product)."""
    velocity_cap = int(monthly_sales * 2)
    return max(1, min(velocity_cap, 30, max_per_product))


# ─── Allocation algorithm ─────────────────────────────────────────────────────

def build_candidates(products: list[dict], budget: float,
                     max_per_product: int, min_roi: float,
                     max_days_to_sell: float) -> list[dict]:
    """Extract, filter, and rank candidates by annualized ROI."""
    candidates = []

    for raw in products:
        p = extract_product_fields(raw)
        if p is None:
            continue

        # Filter: min ROI
        if p["roi_percent"] < min_roi:
            print(f"[allocator] SKIP {p['asin']} — ROI {p['roi_percent']}% < {min_roi}%",
                  file=sys.stderr)
            continue

        # Determine tentative units to size days_to_sell estimate
        max_units = compute_max_units(p["monthly_sales"], max_per_product)
        annualized_roi, est_days = compute_annualized_roi(
            p["roi_percent"], p["monthly_sales"], max_units
        )

        # Filter: max days to sell
        if est_days > max_days_to_sell:
            print(f"[allocator] SKIP {p['asin']} — est {est_days:.0f} days > {max_days_to_sell}",
                  file=sys.stderr)
            continue

        # Filter: product can't even be bought once
        if p["buy_cost"] > budget:
            print(f"[allocator] SKIP {p['asin']} — unit cost ${p['buy_cost']:.2f} > budget",
                  file=sys.stderr)
            continue

        candidates.append({
            **p,
            "max_units": max_units,
            "annualized_roi": annualized_roi,
            "est_days_to_sell": est_days,
        })

    # Sort descending by annualized ROI
    candidates.sort(key=lambda c: c["annualized_roi"], reverse=True)
    print(f"[allocator] {len(candidates)} candidates after filters", file=sys.stderr)
    return candidates


def greedy_allocate(candidates: list[dict], budget: float,
                    concentration_cap: float = BUDGET_CONCENTRATION_CAP) -> list[dict]:
    """Greedy allocation: buy as many units of top-ranked products as budget allows.

    Constraints:
    - No single product > concentration_cap of total budget
    - Remaining budget cascade: try fewer units if full quantity not affordable
    """
    remaining = budget
    plan = []
    max_single = budget * concentration_cap

    for c in candidates:
        if remaining < c["buy_cost"]:
            break  # can't buy even 1 unit from here on (sorted by annualized ROI)

        # Units capped by: velocity limit, concentration cap, and remaining budget
        affordable_units = int(remaining // c["buy_cost"])
        concentration_units = int(max_single // c["buy_cost"])
        units = min(c["max_units"], affordable_units, concentration_units)
        units = max(1, units)

        total_cost = round(units * c["buy_cost"], 2)
        expected_profit = round(units * c["profit_per_unit"], 2)

        # Recompute annualized ROI for the actual units purchased
        annualized_roi, est_days = compute_annualized_roi(
            c["roi_percent"], c["monthly_sales"], units
        )

        plan.append({
            "rank": len(plan) + 1,
            "asin": c["asin"],
            "name": c["name"],
            "units": units,
            "cost_per_unit": round(c["buy_cost"], 2),
            "total_cost": total_cost,
            "profit_per_unit": round(c["profit_per_unit"], 2),
            "expected_profit": expected_profit,
            "roi_percent": round(c["roi_percent"], 1),
            "annualized_roi": annualized_roi,
            "est_days_to_sell": round(est_days, 1),
            "budget_percent": round((total_cost / budget) * 100, 1),
        })

        remaining = round(remaining - total_cost, 2)
        print(f"[allocator] ALLOC {c['asin']} x{units} @ ${c['buy_cost']:.2f} "
              f"= ${total_cost:.2f} | remaining ${remaining:.2f}", file=sys.stderr)

    return plan


def build_projections(plan: list[dict], budget: float) -> dict:
    """Compute portfolio-level projections from the purchase plan."""
    if not plan:
        return {
            "total_expected_profit": 0.0,
            "portfolio_roi": 0.0,
            "portfolio_annualized_roi": 0.0,
            "avg_days_to_recover": 0,
            "capital_turns_per_year": 0.0,
        }

    total_cost = sum(item["total_cost"] for item in plan)
    total_profit = round(sum(item["expected_profit"] for item in plan), 2)
    portfolio_roi = round((total_profit / total_cost) * 100, 1) if total_cost > 0 else 0.0

    # Weighted average days to sell (weighted by capital deployed)
    weighted_days = sum(
        item["est_days_to_sell"] * item["total_cost"] for item in plan
    )
    avg_days = round(weighted_days / total_cost) if total_cost > 0 else 0

    portfolio_annualized_roi = round(
        portfolio_roi * (365.0 / avg_days), 1
    ) if avg_days > 0 else 0.0

    capital_turns = round(365.0 / avg_days, 1) if avg_days > 0 else 0.0

    return {
        "total_expected_profit": total_profit,
        "portfolio_roi": portfolio_roi,
        "portfolio_annualized_roi": portfolio_annualized_roi,
        "avg_days_to_recover": avg_days,
        "capital_turns_per_year": capital_turns,
    }


# ─── Subcommands ──────────────────────────────────────────────────────────────

def cmd_allocate(args) -> dict:
    """Allocate a fixed budget across the best BUY products."""
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"[allocator] ERROR: results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path) as f:
        data = json.load(f)

    raw_products = data.get("products", [])
    print(f"[allocator] Loaded {len(raw_products)} products from {results_path.name}",
          file=sys.stderr)

    candidates = build_candidates(
        raw_products, args.budget,
        args.max_per_product, args.min_roi, args.max_days_to_sell
    )

    plan = greedy_allocate(candidates, args.budget)

    allocated = round(sum(item["total_cost"] for item in plan), 2)
    remaining = round(args.budget - allocated, 2)
    utilization = round((allocated / args.budget) * 100, 1) if args.budget > 0 else 0.0
    projections = build_projections(plan, args.budget)

    print(f"[allocator] Allocated ${allocated:.2f} / ${args.budget:.2f} "
          f"({utilization}% utilization)", file=sys.stderr)
    print(f"[allocator] Expected profit: ${projections['total_expected_profit']:.2f} "
          f"| Portfolio ROI: {projections['portfolio_roi']}%", file=sys.stderr)

    return {
        "budget": round(args.budget, 2),
        "allocated": allocated,
        "remaining": remaining,
        "utilization_percent": utilization,
        "purchase_plan": plan,
        "projections": projections,
        "generated_at": datetime.now().isoformat(),
        "source": str(results_path),
    }


def cmd_compare(args) -> dict:
    """Compare allocations across two or more sourcing run result files."""
    if len(args.results) < 2:
        print("[allocator] ERROR: compare requires at least 2 --results files", file=sys.stderr)
        sys.exit(1)

    comparisons = []

    for results_path_str in args.results:
        results_path = Path(results_path_str)
        if not results_path.exists():
            print(f"[allocator] WARNING: file not found: {results_path}, skipping",
                  file=sys.stderr)
            continue

        with open(results_path) as f:
            data = json.load(f)

        raw_products = data.get("products", [])
        print(f"[allocator] Comparing {results_path.name} ({len(raw_products)} products)",
              file=sys.stderr)

        candidates = build_candidates(
            raw_products, args.budget,
            args.max_per_product, args.min_roi, args.max_days_to_sell
        )
        plan = greedy_allocate(candidates, args.budget)
        allocated = round(sum(item["total_cost"] for item in plan), 2)
        remaining = round(args.budget - allocated, 2)
        utilization = round((allocated / args.budget) * 100, 1) if args.budget > 0 else 0.0
        projections = build_projections(plan, args.budget)

        comparisons.append({
            "source": str(results_path),
            "filename": results_path.name,
            "retailer": data.get("retailer", "unknown"),
            "products_analyzed": len(raw_products),
            "candidates_qualified": len(candidates),
            "budget": round(args.budget, 2),
            "allocated": allocated,
            "remaining": remaining,
            "utilization_percent": utilization,
            "purchase_plan": plan,
            "projections": projections,
        })

    # Rank by expected profit
    comparisons.sort(key=lambda c: c["projections"]["total_expected_profit"], reverse=True)
    for i, comp in enumerate(comparisons):
        comp["rank"] = i + 1

    # Summary comparison row
    winner = comparisons[0] if comparisons else None

    return {
        "budget": round(args.budget, 2),
        "runs_compared": len(comparisons),
        "winner": winner["filename"] if winner else None,
        "winner_expected_profit": winner["projections"]["total_expected_profit"] if winner else 0,
        "comparisons": comparisons,
        "generated_at": datetime.now().isoformat(),
    }


def cmd_simulate(args) -> dict:
    """Project compound capital growth by reinvesting profits each cycle.

    Each cycle = avg_days_to_recover (the portfolio's weighted avg sell-through time).
    Shows month-by-month (approximated) capital curve over `months`.
    """
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"[allocator] ERROR: results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path) as f:
        data = json.load(f)

    raw_products = data.get("products", [])
    print(f"[allocator] Simulate: {len(raw_products)} products, "
          f"${args.budget:.2f} budget, {args.months} months", file=sys.stderr)

    candidates = build_candidates(
        raw_products, args.budget,
        args.max_per_product, args.min_roi, args.max_days_to_sell
    )
    initial_plan = greedy_allocate(candidates, args.budget)
    projections = build_projections(initial_plan, args.budget)

    avg_days = projections["avg_days_to_recover"]
    portfolio_roi_pct = projections["portfolio_roi"]

    if avg_days <= 0 or portfolio_roi_pct <= 0:
        print("[allocator] WARNING: no valid allocation — simulation empty", file=sys.stderr)
        return {
            "budget": round(args.budget, 2),
            "months": args.months,
            "avg_cycle_days": avg_days,
            "portfolio_roi_per_cycle": portfolio_roi_pct,
            "monthly_curve": [],
            "final_capital": round(args.budget, 2),
            "total_profit": 0.0,
            "total_return_percent": 0.0,
            "generated_at": datetime.now().isoformat(),
        }

    total_days = args.months * 30
    cycles_per_year = 365.0 / avg_days
    roi_per_cycle = portfolio_roi_pct / 100.0  # as a multiplier

    # Simulate day by day, track monthly snapshots
    capital = args.budget
    monthly_curve = []
    day = 0
    next_cycle_day = avg_days

    # Track cycles completed within each month
    month_capital_start = capital
    current_month = 1
    cycles_this_month = 0

    while day <= total_days:
        # Snapshot at each month boundary
        if day >= current_month * 30 or day == total_days:
            monthly_curve.append({
                "month": current_month,
                "day": day,
                "capital": round(capital, 2),
                "gain_vs_start": round(capital - args.budget, 2),
                "cumulative_roi_percent": round(((capital - args.budget) / args.budget) * 100, 1),
                "cycles_completed": round(day / avg_days, 1) if avg_days > 0 else 0,
            })
            if day >= current_month * 30:
                current_month += 1
                if current_month > args.months:
                    break

        # Apply profit at each cycle
        if day >= next_cycle_day and day < total_days:
            profit_this_cycle = round(capital * roi_per_cycle, 2)
            capital = round(capital + profit_this_cycle, 2)
            next_cycle_day += avg_days
            print(f"[allocator] Cycle complete @ day {int(day)}: "
                  f"capital ${capital:.2f}", file=sys.stderr)

        day += 1

    final_capital = round(capital, 2)
    total_profit = round(final_capital - args.budget, 2)
    total_return_pct = round((total_profit / args.budget) * 100, 1) if args.budget > 0 else 0.0

    print(f"[allocator] Simulation done: ${args.budget:.2f} → ${final_capital:.2f} "
          f"over {args.months} months ({total_return_pct}% total return)", file=sys.stderr)

    return {
        "budget": round(args.budget, 2),
        "months": args.months,
        "avg_cycle_days": avg_days,
        "portfolio_roi_per_cycle": portfolio_roi_pct,
        "cycles_per_year": round(cycles_per_year, 1),
        "initial_plan_summary": {
            "products": len(initial_plan),
            "allocated": round(sum(i["total_cost"] for i in initial_plan), 2),
            "projections": projections,
        },
        "monthly_curve": monthly_curve,
        "final_capital": final_capital,
        "total_profit": total_profit,
        "total_return_percent": total_return_pct,
        "generated_at": datetime.now().isoformat(),
        "source": str(results_path),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capital allocator for Amazon FBA sourcing — maximize profit within budget"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── shared args factory ──
    def add_shared_args(sub):
        sub.add_argument("--budget", type=float, required=True,
                         help="Total capital budget in dollars (e.g. 1500)")
        sub.add_argument("--results", required=True, nargs="+",
                         help="Path(s) to profitability results JSON")
        sub.add_argument("--max-per-product", type=int, default=DEFAULT_MAX_PER_PRODUCT,
                         help=f"Max units per ASIN (default: {DEFAULT_MAX_PER_PRODUCT})")
        sub.add_argument("--min-roi", type=float, default=DEFAULT_MIN_ROI,
                         help=f"Minimum ROI %% to include (default: {DEFAULT_MIN_ROI})")
        sub.add_argument("--max-days-to-sell", type=float, default=DEFAULT_MAX_DAYS_TO_SELL,
                         help=f"Skip products taking longer than N days (default: {DEFAULT_MAX_DAYS_TO_SELL})")

    # ── allocate ──
    sub_allocate = subparsers.add_parser(
        "allocate", help="Allocate budget across BUY products"
    )
    add_shared_args(sub_allocate)
    # allocate only takes one results file; enforce at runtime
    sub_allocate.add_argument("--results", required=True,
                              help="Path to profitability results JSON")

    # ── compare ──
    sub_compare = subparsers.add_parser(
        "compare", help="Compare allocations across multiple sourcing runs"
    )
    add_shared_args(sub_compare)

    # ── simulate ──
    sub_simulate = subparsers.add_parser(
        "simulate", help="Project compound capital growth over N months"
    )
    add_shared_args(sub_simulate)
    sub_simulate.add_argument("--months", type=int, default=6,
                              help="Number of months to project (default: 6)")
    # simulate only takes one results file
    sub_simulate.add_argument("--results", required=True,
                              help="Path to profitability results JSON")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.budget <= 0:
        print("[allocator] ERROR: --budget must be > 0", file=sys.stderr)
        sys.exit(1)

    # Normalize --results to always be a list for shared helpers
    if isinstance(args.results, str):
        args.results = [args.results]

    print(f"[allocator] Command: {args.command} | Budget: ${args.budget:.2f}", file=sys.stderr)

    if args.command == "allocate":
        result = cmd_allocate(args)
    elif args.command == "compare":
        result = cmd_compare(args)
    elif args.command == "simulate":
        result = cmd_simulate(args)
    else:
        print(f"[allocator] ERROR: unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
