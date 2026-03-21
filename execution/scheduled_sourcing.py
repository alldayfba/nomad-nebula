#!/usr/bin/env python3
"""
Script: scheduled_sourcing.py
Purpose: Scheduled sourcing system that runs the FBA sourcing pipeline on bookmarked URLs.
Inputs:  Subcommands: add, list, remove, enable, disable, run, run-due, run-all
Outputs: Sourcing results + alerts for profitable products

Usage:
  python execution/scheduled_sourcing.py add --url "..." --label "..." [--min-roi 30] [--schedule daily]
  python execution/scheduled_sourcing.py list
  python execution/scheduled_sourcing.py remove --index 0
  python execution/scheduled_sourcing.py enable --index 0
  python execution/scheduled_sourcing.py disable --index 0
  python execution/scheduled_sourcing.py run --index 0
  python execution/scheduled_sourcing.py run-due
  python execution/scheduled_sourcing.py run-all
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
BOOKMARKS_FILE = TMP_DIR / "bookmarks.json"
BRAND_STATE_FILE = TMP_DIR / "brand_watchlist_state.json"

# Schedule thresholds (in hours)
SCHEDULE_THRESHOLDS = {
    "hourly": 1,
    "daily": 20,       # 20h to account for timing drift
    "weekly": 144,      # 6 days in hours
}

# ── Brand Watchlist ───────────────────────────────────────────────────────────
# S/A-tier brands confirmed profitable from OA analysis (March 2026).
# flags: extra CLI args to pass to source.py for this brand.
BRAND_WATCHLIST = [
    {"brand": "Zara",          "flags": ["--fbm"],         "tier": "S"},
    {"brand": "Jellycat",      "flags": [],                "tier": "S"},
    {"brand": "1883 Monin",    "flags": ["--auto-coupon"], "tier": "S"},
    {"brand": "Dr Bronners",   "flags": ["--auto-coupon"], "tier": "A"},
    {"brand": "MAC Cosmetics", "flags": ["--fbm"],         "tier": "A"},
    {"brand": "Crayola",       "flags": [],                "tier": "A"},
    {"brand": "romand",        "flags": [],                "tier": "A"},
    {"brand": "Convatec",      "flags": [],                "tier": "A"},
]


# ── Bookmark Storage ─────────────────────────────────────────────────────────

def load_bookmarks():
    """Load bookmarks from JSON file. Returns list of bookmark dicts."""
    if not BOOKMARKS_FILE.exists():
        return []
    with open(BOOKMARKS_FILE) as f:
        data = json.load(f)
    return data.get("bookmarks", [])


def save_bookmarks(bookmarks):
    """Save bookmarks list to JSON file."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(BOOKMARKS_FILE, "w") as f:
        json.dump({"bookmarks": bookmarks}, f, indent=2)


# ── Schedule Logic ───────────────────────────────────────────────────────────

def is_due(bookmark):
    """Check if a bookmark is due to run based on its schedule."""
    if not bookmark.get("enabled", True):
        return False

    schedule = bookmark.get("schedule", "daily")
    last_run = bookmark.get("last_run")

    if not last_run:
        return True  # Never run before, so it's due

    threshold_hours = SCHEDULE_THRESHOLDS.get(schedule, 20)
    last_run_dt = datetime.fromisoformat(last_run)
    elapsed = datetime.now() - last_run_dt

    return elapsed >= timedelta(hours=threshold_hours)


# ── Run Pipeline ─────────────────────────────────────────────────────────────

def run_bookmark(bookmark, index=None):
    """Run the sourcing pipeline for a single bookmark.

    Args:
        bookmark: Bookmark dict with url, label, and filter params.
        index: Index in bookmarks list (for logging).

    Returns:
        Dict with status, results_path, and summary.
    """
    label = bookmark.get("label", bookmark.get("url", "unknown"))
    url = bookmark["url"]

    idx_str = f"[{index}] " if index is not None else ""
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[scheduler] {idx_str}Running: {label}", file=sys.stderr)
    print(f"[scheduler] URL: {url}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = str(TMP_DIR / f"{ts}-scheduled-results.json")

    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    pipeline_script = str(PROJECT_ROOT / "execution" / "run_sourcing_pipeline.py")

    cmd = [
        python, pipeline_script,
        "--url", url,
        "--min-roi", str(bookmark.get("min_roi", 30)),
        "--min-profit", str(bookmark.get("min_profit", 3.0)),
        "--max-price", str(bookmark.get("max_price", 50)),
        "--max-products", str(bookmark.get("max_products", 30)),
        "--output", output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print(f"[scheduler] Pipeline FAILED for {label} (exit {result.returncode})",
                  file=sys.stderr)
            return {
                "status": "error",
                "label": label,
                "error": result.stderr[-500:] if result.stderr else "Unknown error",
                "results_path": None,
            }

    except subprocess.TimeoutExpired:
        print(f"[scheduler] Pipeline TIMED OUT for {label}", file=sys.stderr)
        return {
            "status": "timeout",
            "label": label,
            "error": "Pipeline timed out after 900s",
            "results_path": None,
        }
    except Exception as e:
        print(f"[scheduler] Pipeline ERROR for {label}: {e}", file=sys.stderr)
        return {
            "status": "error",
            "label": label,
            "error": str(e),
            "results_path": None,
        }

    # Load results summary
    summary = {}
    if Path(output_path).exists():
        with open(output_path) as f:
            data = json.load(f)
        summary = data.get("summary", {})

    return {
        "status": "success",
        "label": label,
        "results_path": output_path,
        "summary": summary,
    }


def run_bookmarks(bookmarks, indices):
    """Run pipeline for a list of bookmark indices. Returns list of results."""
    results = []
    any_buy = False

    for i in indices:
        bookmark = bookmarks[i]
        result = run_bookmark(bookmark, index=i)
        results.append(result)

        # Update last_run timestamp
        bookmark["last_run"] = datetime.now().isoformat()
        save_bookmarks(bookmarks)

        # Check if any BUY products found
        summary = result.get("summary", {})
        if summary.get("buy_count", 0) > 0:
            any_buy = True

            # Send alert + auto-export for this run
            if result.get("results_path"):
                _send_alert_if_possible(result["results_path"])
                _auto_export_if_possible(result["results_path"])

    # Print summary
    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[scheduler] BATCH COMPLETE -- {len(results)} bookmarks processed", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    for r in results:
        status_icon = "OK" if r["status"] == "success" else "FAIL"
        summary = r.get("summary", {})
        buy_count = summary.get("buy_count", 0)
        maybe_count = summary.get("maybe_count", 0)
        print(f"  [{status_icon}] {r['label']}: BUY={buy_count} MAYBE={maybe_count}",
              file=sys.stderr)

    return results


def _send_alert_if_possible(results_path):
    """Try to send a sourcing alert for the given results file."""
    try:
        # Import from same directory
        alerts_module = PROJECT_ROOT / "execution" / "sourcing_alerts.py"
        if not alerts_module.exists():
            print("[scheduler] sourcing_alerts.py not found -- skipping alert.", file=sys.stderr)
            return

        import importlib.util
        spec = importlib.util.spec_from_file_location("sourcing_alerts", alerts_module)
        sourcing_alerts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sourcing_alerts)

        sourcing_alerts.send_sourcing_alert(results_path, method="telegram")
    except Exception as e:
        print(f"[scheduler] Alert failed: {e}", file=sys.stderr)


def _auto_export_if_possible(results_path):
    """Try to export sourcing results to Google Sheets (non-fatal on failure)."""
    try:
        export_module = PROJECT_ROOT / "execution" / "export_to_sheets.py"
        if not export_module.exists():
            print("[scheduler] export_to_sheets.py not found -- skipping Sheets export.", file=sys.stderr)
            return

        import importlib.util
        spec = importlib.util.spec_from_file_location("export_to_sheets", export_module)
        export_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(export_mod)

        url = export_mod.export_to_sheets(results_path)
        if url:
            print(f"[scheduler] Exported to Sheets: {url}", file=sys.stderr)
    except Exception as e:
        print(f"[scheduler] Sheets export failed: {e}", file=sys.stderr)


# ── Brand Watchlist State ─────────────────────────────────────────────────────

def _load_brand_state():
    """Load per-brand last_run state. Returns dict keyed by brand name."""
    if not BRAND_STATE_FILE.exists():
        return {}
    with open(BRAND_STATE_FILE) as f:
        return json.load(f)


def _save_brand_state(state):
    """Save per-brand last_run state to disk."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(BRAND_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _is_brand_due(state, brand_key, schedule_hours=20):
    """Return True if brand hasn't been scanned in schedule_hours hours."""
    last_run = state.get(brand_key)
    if not last_run:
        return True
    elapsed = datetime.now() - datetime.fromisoformat(last_run)
    return elapsed >= timedelta(hours=schedule_hours)


# ── CLI Commands ─────────────────────────────────────────────────────────────

def cmd_add(args):
    """Add a new bookmark."""
    bookmarks = load_bookmarks()

    bookmark = {
        "url": args.url,
        "label": args.label or args.url[:60],
        "min_roi": args.min_roi,
        "min_profit": args.min_profit,
        "max_price": args.max_price,
        "max_products": args.max_products,
        "schedule": args.schedule,
        "last_run": None,
        "enabled": True,
        "added_at": datetime.now().isoformat(),
    }

    bookmarks.append(bookmark)
    save_bookmarks(bookmarks)

    print(f"Bookmark added at index {len(bookmarks) - 1}:")
    print(f"  Label:    {bookmark['label']}")
    print(f"  URL:      {bookmark['url']}")
    print(f"  Schedule: {bookmark['schedule']}")
    print(f"  Filters:  ROI >= {bookmark['min_roi']}% | "
          f"Profit >= ${bookmark['min_profit']} | "
          f"Max price: ${bookmark['max_price']}")


def cmd_list(args):
    """List all bookmarks."""
    bookmarks = load_bookmarks()

    if not bookmarks:
        print("No bookmarks. Add one with: scheduled_sourcing.py add --url ... --label ...")
        return

    print(f"{'=' * 70}")
    print(f"  SOURCING BOOKMARKS ({len(bookmarks)} total)")
    print(f"{'=' * 70}")

    for i, b in enumerate(bookmarks):
        status = "ON " if b.get("enabled", True) else "OFF"
        schedule = b.get("schedule", "daily")
        last_run = b.get("last_run", "never")
        if last_run and last_run != "never":
            # Show relative time
            try:
                lr_dt = datetime.fromisoformat(last_run)
                elapsed = datetime.now() - lr_dt
                hours = elapsed.total_seconds() / 3600
                if hours < 1:
                    last_run_str = f"{int(elapsed.total_seconds() / 60)}m ago"
                elif hours < 24:
                    last_run_str = f"{hours:.1f}h ago"
                else:
                    last_run_str = f"{hours / 24:.1f}d ago"
            except (ValueError, TypeError):
                last_run_str = last_run
        else:
            last_run_str = "never"

        due_str = " [DUE]" if is_due(b) else ""

        print(f"\n  [{i}] [{status}] {b.get('label', 'unnamed')}{due_str}")
        print(f"      URL:      {b.get('url', '')}")
        print(f"      Schedule: {schedule} | Last run: {last_run_str}")
        print(f"      Filters:  ROI >= {b.get('min_roi', 30)}% | "
              f"Profit >= ${b.get('min_profit', 3.0)} | "
              f"Max price: ${b.get('max_price', 50)}")

    print(f"\n{'=' * 70}")


def cmd_remove(args):
    """Remove a bookmark by index."""
    bookmarks = load_bookmarks()
    idx = args.index

    if idx < 0 or idx >= len(bookmarks):
        print(f"Error: Index {idx} out of range (0-{len(bookmarks) - 1})", file=sys.stderr)
        sys.exit(1)

    removed = bookmarks.pop(idx)
    save_bookmarks(bookmarks)
    print(f"Removed bookmark [{idx}]: {removed.get('label', removed.get('url', ''))}")


def cmd_enable(args):
    """Enable a bookmark."""
    bookmarks = load_bookmarks()
    idx = args.index

    if idx < 0 or idx >= len(bookmarks):
        print(f"Error: Index {idx} out of range (0-{len(bookmarks) - 1})", file=sys.stderr)
        sys.exit(1)

    bookmarks[idx]["enabled"] = True
    save_bookmarks(bookmarks)
    print(f"Enabled bookmark [{idx}]: {bookmarks[idx].get('label', '')}")


def cmd_disable(args):
    """Disable a bookmark."""
    bookmarks = load_bookmarks()
    idx = args.index

    if idx < 0 or idx >= len(bookmarks):
        print(f"Error: Index {idx} out of range (0-{len(bookmarks) - 1})", file=sys.stderr)
        sys.exit(1)

    bookmarks[idx]["enabled"] = False
    save_bookmarks(bookmarks)
    print(f"Disabled bookmark [{idx}]: {bookmarks[idx].get('label', '')}")


def cmd_run(args):
    """Run a specific bookmark by index."""
    bookmarks = load_bookmarks()
    idx = args.index

    if idx < 0 or idx >= len(bookmarks):
        print(f"Error: Index {idx} out of range (0-{len(bookmarks) - 1})", file=sys.stderr)
        sys.exit(1)

    run_bookmarks(bookmarks, [idx])


def cmd_run_due(args):
    """Run all due bookmarks."""
    bookmarks = load_bookmarks()

    if not bookmarks:
        print("No bookmarks configured. Add one first.", file=sys.stderr)
        sys.exit(0)

    due_indices = [i for i, b in enumerate(bookmarks) if is_due(b)]

    if not due_indices:
        print("[scheduler] No bookmarks are due. Nothing to run.", file=sys.stderr)
    else:
        print(f"[scheduler] {len(due_indices)} bookmark(s) due to run.", file=sys.stderr)
        run_bookmarks(bookmarks, due_indices)

    # Print cron setup instructions
    print(f"\n{'─' * 60}")
    print("To schedule hourly sourcing checks:")
    print("  crontab -e")
    print(f"  0 * * * * cd {PROJECT_ROOT} && .venv/bin/python execution/scheduled_sourcing.py "
          f"run-due 2>> .tmp/sourcing/cron.log")
    print(f"{'─' * 60}")


def cmd_run_all(args):
    """Run all enabled bookmarks regardless of schedule."""
    bookmarks = load_bookmarks()

    if not bookmarks:
        print("No bookmarks configured. Add one first.", file=sys.stderr)
        sys.exit(0)

    enabled_indices = [i for i, b in enumerate(bookmarks) if b.get("enabled", True)]

    if not enabled_indices:
        print("[scheduler] No enabled bookmarks. Nothing to run.", file=sys.stderr)
        sys.exit(0)

    print(f"[scheduler] Running ALL {len(enabled_indices)} enabled bookmark(s).", file=sys.stderr)
    run_bookmarks(bookmarks, enabled_indices)


# ── Brand Watchlist Scanner ───────────────────────────────────────────────────

def cmd_brand_scan(args):
    """Scan each due brand in BRAND_WATCHLIST using source.py."""
    state = _load_brand_state()
    source_script = str(PROJECT_ROOT / "execution" / "source.py")
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

    due = [b for b in BRAND_WATCHLIST if _is_brand_due(state, b["brand"])]

    if not due:
        print("[brand-scan] All brands up-to-date. Nothing to run.", file=sys.stderr)
        _print_brand_cron_tip()
        return

    print(f"[brand-scan] {len(due)} brand(s) due to scan.", file=sys.stderr)

    for entry in due:
        brand = entry["brand"]
        extra_flags = entry["flags"]
        tier = entry["tier"]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(TMP_DIR / f"{ts}-brand-{brand.lower().replace(' ', '_')}.json")

        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"[brand-scan] [{tier}] {brand}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

        # source.py brand only accepts: brand_name, --retailers, --max, --min-profit, --deep-verify
        # Filter extra_flags to only supported args
        supported_brand_flags = {"--retailers", "-r", "--max", "-n", "--min-profit", "--deep-verify"}
        filtered_flags = []
        skip_next = False
        for i, flag in enumerate(extra_flags):
            if skip_next:
                skip_next = False
                continue
            if flag in supported_brand_flags:
                filtered_flags.append(flag)
                if i + 1 < len(extra_flags) and not extra_flags[i + 1].startswith("-"):
                    filtered_flags.append(extra_flags[i + 1])
                    skip_next = True
            elif not flag.startswith("-"):
                filtered_flags.append(flag)
            else:
                print(f"[brand-scan] Skipping unsupported flag '{flag}' for brand mode",
                      file=sys.stderr)

        cmd = [python, source_script, "brand", brand] + filtered_flags

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            if result.returncode != 0:
                print(f"[brand-scan] source.py FAILED for {brand} (exit {result.returncode})",
                      file=sys.stderr)
                continue

            # Only update state on success
            state[brand] = datetime.now().isoformat()
            _save_brand_state(state)

            # Check for BUY results in stdout (source.py prints JSON to stdout)
            try:
                data = json.loads(result.stdout) if result.stdout.strip() else {}
                buy_count = data.get("summary", {}).get("buy_count", 0)
                maybe_count = data.get("summary", {}).get("maybe_count", 0)
                print(f"[brand-scan] {brand}: BUY={buy_count} MAYBE={maybe_count}", file=sys.stderr)

                # Save results to file
                if data:
                    with open(output_path, "w") as f:
                        json.dump(data, f, indent=2, default=str)
            except json.JSONDecodeError:
                print(f"[brand-scan] {brand}: completed (no JSON output)", file=sys.stderr)

                if buy_count > 0:
                    _send_alert_if_possible(output_path)
                    _auto_export_if_possible(output_path)

        except subprocess.TimeoutExpired:
            print(f"[brand-scan] TIMED OUT for {brand}", file=sys.stderr)
            state[brand] = datetime.now().isoformat()
            _save_brand_state(state)
        except Exception as e:
            print(f"[brand-scan] ERROR for {brand}: {e}", file=sys.stderr)

    _print_brand_cron_tip()


def _print_brand_cron_tip():
    """Print cron setup instructions for brand-scan."""
    print(f"\n{'─' * 60}")
    print("To schedule daily brand scans at 8am:")
    print("  crontab -e")
    print(f"  0 8 * * * cd {PROJECT_ROOT} && .venv/bin/python execution/scheduled_sourcing.py "
          f"brand-scan 2>> .tmp/sourcing/brand-scan.log")
    print(f"{'─' * 60}")


# ── CardBear Auto-Trigger ─────────────────────────────────────────────────────

def cmd_cardbear_scan(args):
    """Scrape CardBear for gift card discounts and auto-trigger sourcing for retailers >= 10%."""
    try:
        import importlib.util
        cb_module = PROJECT_ROOT / "execution" / "scrape_cardbear.py"
        if not cb_module.exists():
            print("[cardbear-scan] scrape_cardbear.py not found.", file=sys.stderr)
            sys.exit(1)

        spec = importlib.util.spec_from_file_location("scrape_cardbear", cb_module)
        cardbear = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cardbear)

        # Step 1: Scrape current rates
        print("[cardbear-scan] Scraping CardBear gift card rates...", file=sys.stderr)
        result = cardbear.scrape_cardbear()
        print(f"[cardbear-scan] Scraped {result['retailers_scraped']} retailers, "
              f"{result['retailers_with_discount']} with active discounts.", file=sys.stderr)

        if result.get("new_highs"):
            print(f"[cardbear-scan] {len(result['new_highs'])} discount increase(s):", file=sys.stderr)
            for h in result["new_highs"]:
                print(f"  {h['retailer']}: {h['old_discount']}% → {h['new_discount']}%", file=sys.stderr)

        # Step 2: Trigger sourcing for retailers >= min_discount
        min_discount = args.min_discount
        dry_run = not args.execute
        print(f"\n[cardbear-scan] Checking for retailers >= {min_discount}% gift card discount...",
              file=sys.stderr)
        actions = cardbear.trigger_sourcing(
            min_discount=min_discount,
            dry_run=dry_run,
            max_products=args.max_products,
            min_roi=args.min_roi,
        )

        if actions:
            print(f"\n[cardbear-scan] {len(actions)} retailer(s) actioned.", file=sys.stderr)
            for a in actions:
                print(f"  {a['retailer']}: {a['discount_percent']}% → {a['action']}", file=sys.stderr)
        else:
            print(f"[cardbear-scan] No retailers met the {min_discount}% threshold.", file=sys.stderr)

    except Exception as e:
        print(f"[cardbear-scan] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'─' * 60}")
    print("To schedule daily CardBear scans at 9am:")
    print("  crontab -e")
    print(f"  0 9 * * * cd {PROJECT_ROOT} && .venv/bin/python execution/scheduled_sourcing.py "
          f"cardbear-scan --execute 2>> .tmp/sourcing/cardbear-scan.log")
    print(f"{'─' * 60}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scheduled FBA sourcing -- manage bookmarked URLs and run sourcing pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add
    p_add = subparsers.add_parser("add", help="Add a new bookmark")
    p_add.add_argument("--url", required=True, help="Retail URL to source from")
    p_add.add_argument("--label", default=None, help="Human-readable label for this bookmark")
    p_add.add_argument("--min-roi", type=float, default=30, help="Minimum ROI %% (default: 30)")
    p_add.add_argument("--min-profit", type=float, default=3.5, help="Min profit per unit (default: $3.50)")
    p_add.add_argument("--max-price", type=float, default=50, help="Max buy price (default: $50)")
    p_add.add_argument("--max-products", type=int, default=30, help="Max products to scrape (default: 30)")
    p_add.add_argument("--schedule", default="daily", choices=["hourly", "daily", "weekly"],
                       help="Run schedule (default: daily)")

    # list
    subparsers.add_parser("list", help="List all bookmarks")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove a bookmark")
    p_remove.add_argument("--index", type=int, required=True, help="Bookmark index to remove")

    # enable
    p_enable = subparsers.add_parser("enable", help="Enable a bookmark")
    p_enable.add_argument("--index", type=int, required=True, help="Bookmark index to enable")

    # disable
    p_disable = subparsers.add_parser("disable", help="Disable a bookmark")
    p_disable.add_argument("--index", type=int, required=True, help="Bookmark index to disable")

    # run
    p_run = subparsers.add_parser("run", help="Run a specific bookmark now")
    p_run.add_argument("--index", type=int, required=True, help="Bookmark index to run")

    # run-due
    subparsers.add_parser("run-due", help="Run all bookmarks that are due")

    # run-all
    subparsers.add_parser("run-all", help="Run all enabled bookmarks now (ignore schedule)")

    # brand-scan
    subparsers.add_parser("brand-scan", help="Scan all due brands from the S/A-tier watchlist")

    # cardbear-scan
    p_cardbear = subparsers.add_parser(
        "cardbear-scan",
        help="Scrape CardBear gift card rates and auto-trigger sourcing for retailers >= threshold"
    )
    p_cardbear.add_argument("--min-discount", type=float, default=10.0,
                            help="Min gift card discount %% to trigger sourcing (default: 10)")
    p_cardbear.add_argument("--execute", action="store_true",
                            help="Actually run sourcing (default: dry-run only)")
    p_cardbear.add_argument("--max-products", type=int, default=30,
                            help="Max products per sourcing run (default: 30)")
    p_cardbear.add_argument("--min-roi", type=float, default=30,
                            help="Min ROI threshold (default: 30)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    command_map = {
        "add": cmd_add,
        "list": cmd_list,
        "remove": cmd_remove,
        "enable": cmd_enable,
        "disable": cmd_disable,
        "run": cmd_run,
        "run-due": cmd_run_due,
        "run-all": cmd_run_all,
        "brand-scan": cmd_brand_scan,
        "cardbear-scan": cmd_cardbear_scan,
    }

    command_map[args.command](args)


if __name__ == "__main__":
    main()
