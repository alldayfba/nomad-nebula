#!/usr/bin/env python3
"""
pipeline_runner.py — Wired pipeline orchestrator.

Chains existing tools with automatic verification and contract validation.
Each pipeline is a sequence of steps that auto-trigger quality checks.

Usage:
    # Full lead gen pipeline: scrape → filter → email gen → verify → export
    python execution/pipeline_runner.py lead-gen \
        --query "dentists" --location "Miami FL" --max 30

    # Sourcing pipeline: source → profitability → contract validate → alert
    python execution/pipeline_runner.py sourcing \
        --mode brand --brand "Jellycat" --max-results 20

    # Creator refresh pipeline: check freshness → scrape latest → video-to-action → update brain
    python execution/pipeline_runner.py creator-refresh \
        --creator "nick-saraev"

    # Outreach pipeline: scrape → filter → parallel browser outreach
    python execution/pipeline_runner.py outreach \
        --query "chiropractors" --location "Austin TX" --max 20
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
VENV_ACTIVATE = "source .venv/bin/activate 2>/dev/null || true"


def log(msg: str):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_step(name: str, cmd: str, cwd: str = None) -> dict:
    """Run a pipeline step and return result."""
    log(f"STEP: {name}")
    start = time.time()
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd or str(PROJECT_ROOT), timeout=600,
    )
    elapsed = round(time.time() - start, 1)

    success = result.returncode == 0
    if not success:
        log(f"  ✗ FAILED ({elapsed}s): {result.stderr[:300]}")
    else:
        log(f"  ✓ Done ({elapsed}s)")

    return {
        "step": name,
        "success": success,
        "elapsed": elapsed,
        "stdout": result.stdout[-500:] if result.stdout else "",
        "stderr": result.stderr[-300:] if result.stderr else "",
    }


def find_latest_file(pattern: str, directory: Path = None) -> Path:
    """Find the most recently modified file matching a glob pattern."""
    search_dir = directory or TMP_DIR
    files = sorted(search_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


# ── Pipeline: Lead Gen ────────────────────────────────────────────────────────

def pipeline_lead_gen(args):
    """Full lead gen: scrape → filter → email gen → verify each → export."""
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    leads_csv = TMP_DIR / f"leads_{timestamp}.csv"
    filtered_csv = TMP_DIR / f"filtered_{timestamp}.csv"
    emails_csv = TMP_DIR / f"emails_{timestamp}.csv"

    # Step 1: Scrape
    r = run_step("Scrape Google Maps",
        f"{VENV_ACTIVATE} && python execution/run_scraper.py "
        f"--query \"{args.query}\" --location \"{args.location}\" "
        f"--max {args.max} --output {leads_csv}")
    results.append(r)
    if not r["success"]:
        return results

    # Step 2: ICP Filter
    r = run_step("Filter ICP",
        f"{VENV_ACTIVATE} && python execution/filter_icp.py "
        f"--input {leads_csv} --output {filtered_csv} --threshold {args.threshold}")
    results.append(r)
    if not r["success"]:
        # If filter fails, use unfiltered leads
        log("  ⚠ Filter failed, using unfiltered leads")
        filtered_csv = leads_csv

    # Count filtered leads
    try:
        with open(filtered_csv) as f:
            lead_count = sum(1 for _ in csv.DictReader(f))
        log(f"  {lead_count} leads passed ICP filter")
    except Exception:
        lead_count = 0

    if lead_count == 0:
        log("  No leads passed filter. Pipeline complete.")
        return results

    # Step 3: Generate Emails
    r = run_step("Generate Emails",
        f"{VENV_ACTIVATE} && python execution/generate_emails.py "
        f"--input {filtered_csv} --output {emails_csv}")
    results.append(r)
    if not r["success"]:
        return results

    # Step 4: Verify a sample email via verification loop
    r = run_step("Verify Sample Email (quality check)",
        f"{VENV_ACTIVATE} && python execution/verification_loop.py "
        f"--task \"Review this email CSV for quality. Check 3 random emails for personalization, "
        f"clarity, and CTA strength. The CSV is at {emails_csv}\" "
        f"--producer-model claude --reviewer-model claude "
        f"--save {TMP_DIR}/verified_emails_{timestamp}.json")
    results.append(r)

    # Step 5: Summary
    log(f"\n{'='*50}")
    log(f"PIPELINE COMPLETE — Lead Gen")
    log(f"  Leads scraped: {leads_csv}")
    log(f"  Filtered: {filtered_csv}")
    log(f"  Emails: {emails_csv}")
    log(f"  Steps: {len(results)} | Passed: {sum(1 for r in results if r['success'])}")
    log(f"{'='*50}")

    return results


# ── Pipeline: Sourcing ────────────────────────────────────────────────────────

def pipeline_sourcing(args):
    """Sourcing: source → profitability → contract validate."""
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 1: Run sourcing
    source_cmd = f"{VENV_ACTIVATE} && python execution/source.py {args.mode}"
    if args.brand:
        source_cmd += f" --brand \"{args.brand}\""
    if args.max_results:
        source_cmd += f" --max-results {args.max_results}"
    if args.asin:
        source_cmd += f" --asin {args.asin}"

    r = run_step(f"Source Products ({args.mode})", source_cmd)
    results.append(r)
    if not r["success"]:
        return results

    # Step 2: Find the output and validate against contract
    sourcing_output = find_latest_file("sourcing_*.json") or find_latest_file("sourcing_*.md")
    if sourcing_output:
        r = run_step("Validate Against Sourcing Contract",
            f"{VENV_ACTIVATE} && python execution/prompt_contracts/validate_contract.py "
            f"--contract execution/prompt_contracts/contracts/sourcing_report.yaml "
            f"--output {sourcing_output}")
        results.append(r)

    log(f"\nPIPELINE COMPLETE — Sourcing ({args.mode})")
    return results


# ── Pipeline: Creator Refresh ─────────────────────────────────────────────────

def pipeline_creator_refresh(args):
    """Creator refresh: check freshness → find latest video → video-to-action → update brain."""
    results = []
    creator = args.creator
    brain_dir = PROJECT_ROOT / "bots" / "creators"
    brain_file = brain_dir / f"{creator}-brain.md"

    if not brain_file.exists():
        log(f"Creator brain not found: {brain_file}")
        log(f"Available: {[f.stem.replace('-brain', '') for f in brain_dir.glob('*-brain.md')]}")
        return results

    # Step 1: Check freshness
    log(f"Checking freshness of {creator} brain...")
    content = brain_file.read_text()
    import re
    last_updated = re.search(r"Last Updated:\s*(\d{4}-\d{2}-\d{2})", content)
    if last_updated:
        log(f"  Last updated: {last_updated.group(1)}")
    else:
        log(f"  No Last Updated timestamp found")

    # Step 2: Scrape latest content
    r = run_step(f"Scrape Latest Content ({creator})",
        f"{VENV_ACTIVATE} && python execution/scrape_creator_intel.py "
        f"--creator \"{creator}\"")
    results.append(r)

    # Step 3: Check for new transcripts and run video-to-action
    transcript_dir = TMP_DIR / "creators" / creator / "videos"
    if transcript_dir.exists():
        transcripts = sorted(transcript_dir.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
        if transcripts:
            latest_transcript = transcripts[0]
            log(f"  Latest transcript: {latest_transcript.name}")

            r = run_step(f"Video-to-Action ({latest_transcript.name})",
                f"{VENV_ACTIVATE} && python execution/video_to_action.py "
                f"--transcript \"{latest_transcript}\" "
                f"--context \"Agency OS (growth agency) + Amazon OS (FBA coaching)\"")
            results.append(r)

    # Step 4: Rebuild brain
    r = run_step(f"Rebuild Creator Brain ({creator})",
        f"{VENV_ACTIVATE} && python execution/build_creator_brain.py "
        f"--name \"{creator}\"")
    results.append(r)

    log(f"\nPIPELINE COMPLETE — Creator Refresh ({creator})")
    return results


# ── Pipeline: Outreach ────────────────────────────────────────────────────────

def pipeline_outreach(args):
    """Full outreach: scrape → filter → parallel browser outreach."""
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    leads_csv = TMP_DIR / f"leads_{timestamp}.csv"
    filtered_csv = TMP_DIR / f"filtered_{timestamp}.csv"

    # Step 1: Scrape
    r = run_step("Scrape Google Maps",
        f"{VENV_ACTIVATE} && python execution/run_scraper.py "
        f"--query \"{args.query}\" --location \"{args.location}\" "
        f"--max {args.max} --output {leads_csv}")
    results.append(r)
    if not r["success"]:
        return results

    # Step 2: ICP Filter
    r = run_step("Filter ICP",
        f"{VENV_ACTIVATE} && python execution/filter_icp.py "
        f"--input {leads_csv} --output {filtered_csv} --threshold {args.threshold}")
    results.append(r)
    if not r["success"]:
        filtered_csv = leads_csv

    # Step 3: Parallel browser outreach (DRY RUN by default for safety)
    dry_flag = "" if args.live else "--dry-run"
    r = run_step("Parallel Browser Outreach",
        f"{VENV_ACTIVATE} && python execution/parallel_outreach.py "
        f"--input {filtered_csv} "
        f"--max-browsers {args.browsers} "
        f"--message-template {args.template} "
        f"{dry_flag}")
    results.append(r)

    mode = "LIVE" if args.live else "DRY RUN"
    log(f"\nPIPELINE COMPLETE — Outreach ({mode})")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run wired pipelines with auto-verification")
    subparsers = parser.add_subparsers(dest="pipeline", required=True)

    # Lead Gen
    lg = subparsers.add_parser("lead-gen", help="Scrape → Filter → Email → Verify")
    lg.add_argument("--query", required=True)
    lg.add_argument("--location", required=True)
    lg.add_argument("--max", type=int, default=20)
    lg.add_argument("--threshold", type=int, default=6, help="ICP score threshold")

    # Sourcing
    src = subparsers.add_parser("sourcing", help="Source → Profitability → Contract Validate")
    src.add_argument("--mode", required=True, help="brand, category, asin, scan, etc.")
    src.add_argument("--brand", help="Brand name (for brand mode)")
    src.add_argument("--asin", help="ASIN (for asin mode)")
    src.add_argument("--max-results", type=int, default=20)

    # Creator Refresh
    cr = subparsers.add_parser("creator-refresh", help="Check freshness → Scrape → Video-to-Action → Rebuild brain")
    cr.add_argument("--creator", required=True, help="Creator slug (e.g., nick-saraev)")

    # Outreach
    out = subparsers.add_parser("outreach", help="Scrape → Filter → Parallel Browser Outreach")
    out.add_argument("--query", required=True)
    out.add_argument("--location", required=True)
    out.add_argument("--max", type=int, default=20)
    out.add_argument("--threshold", type=int, default=6)
    out.add_argument("--browsers", type=int, default=3)
    out.add_argument("--template", default="outreach_intro")
    out.add_argument("--live", action="store_true", help="Actually submit forms (default: dry-run)")

    args = parser.parse_args()
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{'='*50}")
    print(f"PIPELINE: {args.pipeline.upper()}")
    print(f"{'='*50}")

    start = time.time()

    if args.pipeline == "lead-gen":
        results = pipeline_lead_gen(args)
    elif args.pipeline == "sourcing":
        results = pipeline_sourcing(args)
    elif args.pipeline == "creator-refresh":
        results = pipeline_creator_refresh(args)
    elif args.pipeline == "outreach":
        results = pipeline_outreach(args)
    else:
        print(f"Unknown pipeline: {args.pipeline}")
        sys.exit(1)

    elapsed = round(time.time() - start, 1)
    passed = sum(1 for r in results if r.get("success"))
    failed = len(results) - passed

    print(f"\n{'='*50}")
    print(f"DONE in {elapsed}s — {passed} passed, {failed} failed")
    print(f"{'='*50}")

    # Save pipeline log
    log_path = TMP_DIR / f"pipeline_{args.pipeline}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps({
        "pipeline": args.pipeline,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
        "steps": results,
    }, indent=2))
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
