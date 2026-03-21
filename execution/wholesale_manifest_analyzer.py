#!/usr/bin/env python3
from __future__ import annotations
"""
Script: wholesale_manifest_analyzer.py
Purpose: Accept a wholesaler's price list (CSV or Excel) and run every SKU through the
         full FBA profitability stack — matching to Amazon, computing fees, and outputting
         a ranked BUY/MAYBE/SKIP sheet.
Inputs:  --manifest (CSV or .xlsx), optional column overrides, --min-roi, --min-profit,
         --max-price, --export-sheets
Outputs: JSON (stdout) with ranked products; stderr progress with ETA
Subcommands:
  analyze  — full pipeline (match + profitability) for every SKU
  preview  — show column detection results without running analysis (dry run)
"""

import argparse
import ast
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Dependency guard ──────────────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup  # noqa: F401 — used by imported helpers
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    openpyxl = None  # only required for .xlsx input

# ── Path setup + dotenv ───────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Import shared pipeline functions ─────────────────────────────────────────
from execution.match_amazon_products import (
    search_amazon_playwright,
    search_keepa,
    get_amazon_product_details,
    get_keepa_product_details,
    title_similarity,
    USER_AGENT,
    AMAZON_SEARCH_DELAY,
)
from execution.calculate_fba_profitability import (
    calculate_product_profitability,
    get_referral_fee_rate,
    estimate_fba_fee,
    estimate_monthly_sales,
)

# ── Constants ─────────────────────────────────────────────────────────────────
KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")

# Column detection: standard key → candidate substrings (case-insensitive partial match)
COLUMN_HINTS = {
    "upc":    ["upc", "barcode", "ean", "gtin"],
    "cost":   ["cost", "price", "wholesale", "unit cost", "each"],
    "name":   ["name", "description", "title", "item", "product"],
    "pack":   ["pack", "case", "qty", "quantity", "units per case"],
    "brand":  ["brand", "manufacturer", "vendor"],
}

# ── Column detection ──────────────────────────────────────────────────────────

def detect_columns(headers: list[str]) -> dict[str, str | None]:
    """Auto-detect which header maps to each standard field.

    Returns a dict like:
        {"upc": "UPC Code", "cost": "Unit Cost", "name": "Description", ...}
    Values are the actual header strings, or None if not found.
    """
    mapping: dict[str, str | None] = {key: None for key in COLUMN_HINTS}
    headers_lower = [h.lower().strip() for h in headers]

    for std_key, hints in COLUMN_HINTS.items():
        for hint in hints:
            for i, h in enumerate(headers_lower):
                if hint in h:
                    mapping[std_key] = headers[i]
                    break
            if mapping[std_key]:
                break

    return mapping


def apply_column_overrides(mapping: dict, overrides: dict) -> dict:
    """Merge user-specified column overrides into auto-detected mapping."""
    for std_key, col_name in overrides.items():
        if col_name:
            mapping[std_key] = col_name
    return mapping


# ── Manifest parsing ──────────────────────────────────────────────────────────

def _parse_cost(value: str) -> float | None:
    """Strip currency symbols and parse a cost string to float."""
    if not value:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(value).strip())
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_pack(value: str) -> int:
    """Parse pack/case size to int. Returns 1 if unparseable."""
    if not value:
        return 1
    cleaned = re.sub(r"[^\d]", "", str(value).strip())
    try:
        qty = int(cleaned)
        return qty if qty >= 1 else 1
    except ValueError:
        return 1


def parse_manifest(path: str | Path, column_overrides: dict | None = None) -> tuple[list[dict], dict]:
    """Parse a CSV or Excel manifest file into a list of standardised product dicts.

    Each dict contains:
        name, upc, wholesale_cost, pack_qty, brand, _raw (original row dict)

    Returns (products, column_mapping).
    """
    path = Path(path)
    suffix = path.suffix.lower()
    rows: list[dict] = []

    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            rows = list(reader)
    elif suffix in (".xlsx", ".xls"):
        if openpyxl is None:
            print("ERROR: openpyxl is required for Excel files — pip install openpyxl", file=sys.stderr)
            sys.exit(1)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return [], {}
        headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
        for row in all_rows[1:]:
            rows.append({headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)})
        wb.close()
    else:
        print(f"ERROR: Unsupported file type '{suffix}'. Use .csv or .xlsx", file=sys.stderr)
        sys.exit(1)

    col_map = detect_columns(list(headers))
    if column_overrides:
        col_map = apply_column_overrides(col_map, column_overrides)

    products: list[dict] = []
    for row in rows:
        # Skip entirely blank rows
        if not any(str(v).strip() for v in row.values()):
            continue

        raw_cost = row.get(col_map["cost"], "") if col_map["cost"] else ""
        raw_pack = row.get(col_map["pack"], "") if col_map["pack"] else ""

        product = {
            "name":           row.get(col_map["name"], "").strip() if col_map["name"] else "",
            "upc":            row.get(col_map["upc"], "").strip() if col_map["upc"] else None,
            "wholesale_cost": _parse_cost(raw_cost),
            "pack_qty":       _parse_pack(raw_pack),
            "brand":          row.get(col_map["brand"], "").strip() if col_map["brand"] else None,
            "_raw":           row,
        }

        # Normalise UPC: strip to digits, None if empty/too short
        if product["upc"]:
            upc_digits = re.sub(r"\D", "", product["upc"])
            product["upc"] = upc_digits if len(upc_digits) >= 8 else None

        products.append(product)

    return products, col_map


# ── Pack size adjustment ──────────────────────────────────────────────────────

def adjust_for_pack_size(cost: float | None, pack_qty: int) -> float | None:
    """Convert a case/pack cost to cost per individual unit."""
    if cost is None or pack_qty <= 1:
        return cost
    return round(cost / pack_qty, 4)


# ── Amazon matching (single product) ─────────────────────────────────────────

def _match_sku_to_amazon(page, sku: dict) -> dict:
    """Match a single manifest SKU to Amazon. Returns amazon data dict.

    Strategy order (Keepa-first when available, Playwright fallback):
      1. Keepa UPC search  — fast, reliable, rich data, no throttle
      2. Keepa title search — fallback if UPC misses
      3. Playwright UPC search — free tier fallback
      4. Playwright title search — last resort
    """
    upc = sku.get("upc")
    name = sku.get("name", "")
    best_match: dict | None = None
    best_confidence = 0.0
    match_method = "none"

    # ── Keepa path (preferred — no throttle, richer data) ────────────────
    if KEEPA_API_KEY:
        # Keepa Strategy 1: UPC search
        if upc:
            keepa_result = search_keepa(upc, is_upc=True)
            if keepa_result and keepa_result.get("asin"):
                best_match = keepa_result
                best_confidence = 0.92
                match_method = "keepa_upc"

        # Keepa Strategy 2: title search fallback
        if (not best_match or best_confidence < 0.7) and name:
            keepa_result = search_keepa(name, is_upc=False)
            if keepa_result and keepa_result.get("asin"):
                sim = title_similarity(name, keepa_result.get("title", ""))
                if sim > best_confidence:
                    best_match = keepa_result
                    best_confidence = max(sim, 0.60)
                    match_method = "keepa_title"

    # ── Playwright path (fallback when Keepa unavailable or missed) ──────
    if not best_match:
        # Playwright Strategy 1: UPC search
        if upc:
            results = search_amazon_playwright(page, upc, is_upc=True)
            time.sleep(AMAZON_SEARCH_DELAY)
            if results:
                best_match = results[0]
                best_confidence = 0.90
                match_method = "upc"

        # Playwright Strategy 2: title search
        if (not best_match or best_confidence < 0.7) and name:
            results = search_amazon_playwright(page, name, is_upc=False)
            time.sleep(AMAZON_SEARCH_DELAY)
            if results:
                for result in results:
                    sim = title_similarity(name, result.get("title", ""))
                    if not result.get("sponsored"):
                        sim += 0.05
                    if sim > best_confidence:
                        best_match = result
                        best_confidence = sim
                        match_method = "title"

    if not best_match:
        return {"asin": None, "match_confidence": 0.0, "match_method": "none"}

    # Enrich with detail data if not already from Keepa
    if best_match.get("asin") and best_confidence >= 0.5:
        if best_match.get("data_source") != "keepa":
            # Playwright match — enrich via Keepa or detail page
            if KEEPA_API_KEY:
                keepa_details = get_keepa_product_details(best_match["asin"])
                if keepa_details:
                    for key, val in keepa_details.items():
                        if val is not None and not best_match.get(key):
                            best_match[key] = val
            else:
                details = get_amazon_product_details(page, best_match["asin"])
                best_match.update(details)
                time.sleep(AMAZON_SEARCH_DELAY)

    best_match["match_confidence"] = round(best_confidence, 3)
    best_match["match_method"] = match_method
    best_match.pop("sponsored", None)
    return best_match


# ── Full manifest analysis ────────────────────────────────────────────────────

def analyze_manifest(
    products: list[dict],
    min_roi: float = 30.0,
    min_profit: float = 3.0,
    max_price: float = 999.0,
    shipping_cost: float = 1.00,
) -> list[dict]:
    """Run the full FBA pipeline on every manifest SKU.

    Each product dict is enriched with 'amazon' and 'profitability' keys,
    then sorted BUY → MAYBE → SKIP by ROI descending within each tier.
    """
    total = len(products)
    print(f"[manifest] Analyzing {total} SKUs...", file=sys.stderr)

    use_keepa = bool(KEEPA_API_KEY)
    if use_keepa:
        print("[manifest] Keepa API available — using for richer data", file=sys.stderr)
    else:
        print("[manifest] No Keepa key — using Playwright (free tier)", file=sys.stderr)

    start_time = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        for i, sku in enumerate(products):
            elapsed = time.time() - start_time
            if i > 0:
                avg_per_item = elapsed / i
                remaining = avg_per_item * (total - i)
                eta = str(timedelta(seconds=int(remaining)))
            else:
                eta = "calculating..."

            label = (sku.get("name") or sku.get("upc") or f"SKU#{i+1}")[:55]
            print(f"  [{i+1}/{total}] {label}  ETA: {eta}", file=sys.stderr)

            # Build per-unit cost from manifest (adjust for pack size)
            unit_cost = adjust_for_pack_size(sku.get("wholesale_cost"), sku.get("pack_qty", 1))

            # Match to Amazon
            amazon_data = _match_sku_to_amazon(page, sku)

            if amazon_data.get("asin"):
                print(f"    → ASIN {amazon_data['asin']} | "
                      f"conf: {amazon_data.get('match_confidence', 0):.2f} | "
                      f"${amazon_data.get('amazon_price', 'N/A')}",
                      file=sys.stderr)
            else:
                print("    → No Amazon match", file=sys.stderr)

            # Build product dict in the shape calculate_product_profitability expects
            product_for_calc = {
                "name":         sku.get("name", ""),
                "brand":        sku.get("brand"),
                "upc":          sku.get("upc"),
                "sale_price":   unit_cost,
                "retail_price": unit_cost,
                "retailer":     "wholesale",
                "amazon":       amazon_data,
            }

            # Calculate profitability
            profitability = calculate_product_profitability(
                product_for_calc,
                shipping_to_fba=shipping_cost,
            )

            # Apply max_price filter
            buy_cost = profitability.get("buy_cost")
            if buy_cost and buy_cost > max_price:
                profitability["verdict"] = "SKIP"
                profitability["skip_reason"] = f"Buy cost ${buy_cost} exceeds max ${max_price}"

            # Apply min_roi / min_profit overrides to MAYBE/BUY threshold
            roi = profitability.get("roi_percent", 0) or 0
            profit = profitability.get("profit_per_unit", 0) or 0
            if profitability["verdict"] == "BUY" and (roi < min_roi or profit < min_profit):
                profitability["verdict"] = "MAYBE"
                profitability["skip_reason"] = None

            sku["amazon"] = amazon_data
            sku["profitability"] = profitability
            # Remove internal raw row from output (bloats JSON)
            sku.pop("_raw", None)

        browser.close()

    # Sort: BUY → MAYBE → SKIP, each tier by ROI descending
    tier_order = {"BUY": 0, "MAYBE": 1, "SKIP": 2}
    products.sort(
        key=lambda p: (
            tier_order.get(p.get("profitability", {}).get("verdict", "SKIP"), 2),
            -(p.get("profitability", {}).get("roi_percent") or 0),
        )
    )

    elapsed_total = time.time() - start_time
    print(f"[manifest] Done in {elapsed_total:.1f}s", file=sys.stderr)
    return products


# ── Build output JSON ─────────────────────────────────────────────────────────

def build_output(manifest_path: str, products: list[dict]) -> dict:
    """Assemble the final output JSON structure."""
    matched = sum(1 for p in products if p.get("amazon", {}).get("asin"))
    unmatched = len(products) - matched

    buy = [p for p in products if p.get("profitability", {}).get("verdict") == "BUY"]
    maybe = [p for p in products if p.get("profitability", {}).get("verdict") == "MAYBE"]
    skip = [p for p in products if p.get("profitability", {}).get("verdict") == "SKIP"]

    actionable_rois = [
        p["profitability"]["roi_percent"]
        for p in (buy + maybe)
        if p.get("profitability", {}).get("roi_percent") is not None
    ]
    avg_roi = round(sum(actionable_rois) / len(actionable_rois), 1) if actionable_rois else 0.0

    return {
        "manifest_file": str(manifest_path),
        "total_skus":    len(products),
        "matched":       matched,
        "unmatched":     unmatched,
        "products":      products,
        "summary": {
            "buy_count":       len(buy),
            "maybe_count":     len(maybe),
            "skip_count":      len(skip),
            "avg_roi_percent": avg_roi,
        },
        "analyzed_at": datetime.now().isoformat(),
    }


# ── Subcommand: preview ───────────────────────────────────────────────────────

def cmd_preview(args):
    """Show column detection results and a sample of parsed rows. No API calls."""
    overrides = _collect_overrides(args)
    products, col_map = parse_manifest(args.manifest, overrides)

    print("\n=== Column Mapping ===", file=sys.stderr)
    for std_key, actual_col in col_map.items():
        status = f"→ '{actual_col}'" if actual_col else "NOT DETECTED"
        print(f"  {std_key:<8} {status}", file=sys.stderr)

    print(f"\n=== Sample Rows (first 5 of {len(products)}) ===", file=sys.stderr)
    for p in products[:5]:
        unit_cost = adjust_for_pack_size(p.get("wholesale_cost"), p.get("pack_qty", 1))
        print(
            f"  name={p['name'][:40]!r}  upc={p['upc']}  "
            f"wholesale=${p['wholesale_cost']}  pack={p['pack_qty']}  "
            f"unit_cost=${unit_cost}  brand={p['brand']}",
            file=sys.stderr,
        )

    result = {
        "manifest_file":  str(args.manifest),
        "total_rows":     len(products),
        "column_mapping": col_map,
        "sample":         [
            {
                "name":          p["name"],
                "upc":           p["upc"],
                "wholesale_cost": p["wholesale_cost"],
                "pack_qty":      p["pack_qty"],
                "unit_cost":     adjust_for_pack_size(p.get("wholesale_cost"), p.get("pack_qty", 1)),
                "brand":         p["brand"],
            }
            for p in products[:10]
        ],
    }
    print(json.dumps(result, indent=2))


# ── Subcommand: analyze ───────────────────────────────────────────────────────

def cmd_analyze(args):
    """Full pipeline: parse manifest → match Amazon → calculate profitability → output JSON."""
    overrides = _collect_overrides(args)
    products, col_map = parse_manifest(args.manifest, overrides)

    if not products:
        print("ERROR: No products parsed from manifest.", file=sys.stderr)
        sys.exit(1)

    print(f"[manifest] Parsed {len(products)} SKUs from {args.manifest}", file=sys.stderr)
    print(f"[manifest] Column mapping: {col_map}", file=sys.stderr)

    products = analyze_manifest(
        products,
        min_roi=args.min_roi,
        min_profit=args.min_profit,
        max_price=args.max_price,
        shipping_cost=args.shipping_cost,
    )

    output = build_output(args.manifest, products)

    buy   = output["summary"]["buy_count"]
    maybe = output["summary"]["maybe_count"]
    skip  = output["summary"]["skip_count"]
    print(
        f"[manifest] Results: {buy} BUY | {maybe} MAYBE | {skip} SKIP | "
        f"avg ROI {output['summary']['avg_roi_percent']}%",
        file=sys.stderr,
    )

    # Write to file if --output specified
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"[manifest] Saved to {out_path}", file=sys.stderr)

    # Export to Google Sheets
    if args.export_sheets:
        _export_to_sheets(output, args)

    # Always write JSON to stdout
    print(json.dumps(output, indent=2))


def _export_to_sheets(output: dict, args):
    """Write results JSON to a temp file and call export_to_sheets.export_to_sheets()."""
    tmp_dir = Path(__file__).parent.parent / ".tmp" / "sourcing"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "wholesale_manifest_results.json"

    # export_to_sheets expects products with "profitability" key — already present
    with open(tmp_path, "w") as f:
        json.dump(output, f, indent=2)

    try:
        from execution.export_to_sheets import export_to_sheets
        sheet_url = export_to_sheets(tmp_path)
        if sheet_url:
            print(f"[manifest] Google Sheet: {sheet_url}", file=sys.stderr)
    except Exception as e:
        print(f"[manifest] Sheets export failed: {e}", file=sys.stderr)


# ── Helper: collect column overrides from args ────────────────────────────────

def _collect_overrides(args) -> dict:
    overrides: dict = {}
    if getattr(args, "upc_col", None):
        overrides["upc"] = args.upc_col
    if getattr(args, "cost_col", None):
        overrides["cost"] = args.cost_col
    if getattr(args, "name_col", None):
        overrides["name"] = args.name_col
    if getattr(args, "pack_col", None):
        overrides["pack"] = args.pack_col
    if getattr(args, "brand_col", None):
        overrides["brand"] = args.brand_col
    return overrides


# ── CLI ───────────────────────────────────────────────────────────────────────

def _add_manifest_args(parser):
    """Shared args for both subcommands."""
    parser.add_argument("--manifest", required=True, help="Path to CSV or .xlsx supplier price list")
    parser.add_argument("--upc-col",   default=None, help="Override: actual column name for UPC/barcode")
    parser.add_argument("--cost-col",  default=None, help="Override: actual column name for unit cost")
    parser.add_argument("--name-col",  default=None, help="Override: actual column name for product name")
    parser.add_argument("--pack-col",  default=None, help="Override: actual column name for pack/case size")
    parser.add_argument("--brand-col", default=None, help="Override: actual column name for brand")


def main():
    parser = argparse.ArgumentParser(
        description="Wholesale manifest FBA profitability analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python execution/wholesale_manifest_analyzer.py analyze --manifest supplier.csv --min-roi 30\n"
            "  python execution/wholesale_manifest_analyzer.py analyze --manifest supplier.xlsx "
            "--cost-col 'Unit Cost' --upc-col 'UPC' --pack-col 'Case Qty' --output results.json\n"
            "  python execution/wholesale_manifest_analyzer.py preview --manifest supplier.csv\n"
            "  python execution/wholesale_manifest_analyzer.py analyze --manifest supplier.csv --export-sheets\n"
        ),
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # ── preview ──────────────────────────────────────────────────────────────
    preview_parser = subparsers.add_parser(
        "preview",
        help="Show detected column mapping and sample rows — no API calls",
    )
    _add_manifest_args(preview_parser)

    # ── analyze ──────────────────────────────────────────────────────────────
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run full FBA pipeline on every SKU in the manifest",
    )
    _add_manifest_args(analyze_parser)
    analyze_parser.add_argument(
        "--min-roi", type=float, default=30.0,
        help="Minimum ROI %% for BUY verdict (default: 30)",
    )
    analyze_parser.add_argument(
        "--min-profit", type=float, default=3.0,
        help="Minimum profit per unit ($) for BUY verdict (default: 3.0)",
    )
    analyze_parser.add_argument(
        "--max-price", type=float, default=999.0,
        help="Maximum buy cost to include (default: no limit)",
    )
    analyze_parser.add_argument(
        "--shipping-cost", type=float, default=1.00,
        help="Estimated shipping cost per unit to FBA (default: $1.00)",
    )
    analyze_parser.add_argument(
        "--output", default=None,
        help="Optional path to save JSON output (also written to stdout)",
    )
    analyze_parser.add_argument(
        "--export-sheets", action="store_true",
        help="Auto-export results to Google Sheets after analysis",
    )

    args = parser.parse_args()

    if args.subcommand == "preview":
        cmd_preview(args)
    elif args.subcommand == "analyze":
        cmd_analyze(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
