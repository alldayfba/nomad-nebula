"""
run_dream100.py

Master orchestrator for the Dream 100 pipeline.

Runs all 3 steps in sequence:
  1. research_prospect.py   → .tmp/research_<name>.json
  2. generate_dream100_assets.py → .tmp/assets_<name>.json
  3. assemble_gammadoc.py   → .tmp/gammadoc_<name>.md

Usage:
    # Full pipeline (recommended):
    python execution/run_dream100.py \
        --name "Alex Hormozi" \
        --website "https://acquisition.com" \
        --niche "business education" \
        --offer "high-ticket business programs" \
        --platform "youtube"

    # Skip research (if site blocks scrapers):
    python execution/run_dream100.py \
        --name "Alex Hormozi" \
        --niche "business education" \
        --offer "high-ticket business programs at $10K+" \
        --platform "youtube" \
        --skip-research

    # Batch mode (CSV of prospects):
    python execution/run_dream100.py --batch prospects.csv

    # Resume from existing research:
    python execution/run_dream100.py \
        --name "Alex Hormozi" \
        --research .tmp/research_Alex_Hormozi_20260220.json \
        --niche "business education" \
        --offer "high-ticket programs"

Batch CSV format:
    name,website,niche,offer,platform
    Alex Hormozi,https://acquisition.com,business education,high-ticket programs,youtube
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_script(script: str, args: list[str]) -> tuple[bool, str]:
    """Run a Python script with args. Returns (success, output)."""
    cmd = [sys.executable, f"execution/{script}"] + args
    print(f"\n  → {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output)
    return result.returncode == 0, output


def extract_output_path(output: str, prefix: str) -> str | None:
    """Extract a .tmp/ file path from script stdout."""
    for line in output.splitlines():
        # Look for lines like "✓ Research complete: .tmp/research_..."
        if ".tmp/" in line and prefix in line:
            parts = line.split(".tmp/")
            if len(parts) > 1:
                path = ".tmp/" + parts[1].split()[0].rstrip(".,")
                if Path(path).exists():
                    return path
    # Fallback: glob for most recent matching file
    tmp = Path(".tmp")
    if not tmp.exists():
        return None
    pattern = f"{prefix}_*"
    matches = sorted(tmp.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(matches[0]) if matches else None


def run_single(
    name: str,
    website: str | None,
    niche: str,
    offer: str,
    platform: str,
    skip_research: bool = False,
    research_path: str | None = None,
) -> dict:
    """Run the full Dream 100 pipeline for a single prospect."""
    safe_name = name.replace(" ", "_")
    result = {
        "prospect": name,
        "started_at": datetime.now().isoformat(),
        "research": None,
        "assets": None,
        "gammadoc": None,
        "success": False,
    }

    print(f"\n{'='*60}")
    print(f"  Dream 100 Pipeline: {name}")
    print(f"{'='*60}")

    # ─── Step 1: Research ───────────────────────────────────────────
    if research_path:
        print(f"\n[Step 1] Using existing research: {research_path}")
        result["research"] = research_path
    elif skip_research:
        print("\n[Step 1] Skipping research (--skip-research flag)")
    else:
        if not website:
            print("ERROR: --website required unless --skip-research or --research is provided")
            return result

        print("\n[Step 1] Researching prospect website...")
        success, output = run_script("research_prospect.py", [
            "--name", name,
            "--website", website,
            "--niche", niche,
            "--offer", offer,
        ])
        if not success:
            print(f"WARNING: Research failed. Continuing without research data.")
        else:
            result["research"] = extract_output_path(output, "research")
            if result["research"]:
                print(f"  Research saved: {result['research']}")

    # ─── Step 2: Generate Assets ────────────────────────────────────
    print("\n[Step 2] Generating Dream 100 assets...")
    asset_args = ["--prospect-name", name]
    if result["research"]:
        asset_args += ["--research", result["research"]]
    else:
        asset_args += [
            "--niche", niche,
            "--offer", offer,
            "--funnel-type", "unknown",
        ]

    success, output = run_script("generate_dream100_assets.py", asset_args)
    if not success:
        print("ERROR: Asset generation failed. Cannot continue.")
        return result
    result["assets"] = extract_output_path(output, "assets")
    if result["assets"]:
        print(f"  Assets saved: {result['assets']}")
    else:
        print("ERROR: Could not locate assets output file.")
        return result

    # ─── Step 3: Assemble GammaDoc ──────────────────────────────────
    print("\n[Step 3] Assembling GammaDoc...")
    assemble_args = [
        "--assets", result["assets"],
        "--prospect-name", name,
        "--their-offer", offer,
    ]
    if result["research"]:
        assemble_args += ["--research", result["research"]]

    success, output = run_script("assemble_gammadoc.py", assemble_args)
    if not success:
        print("ERROR: GammaDoc assembly failed.")
        return result
    result["gammadoc"] = extract_output_path(output, "gammadoc")
    result["success"] = bool(result["gammadoc"])

    # ─── Summary ────────────────────────────────────────────────────
    result["completed_at"] = datetime.now().isoformat()
    print(f"\n{'='*60}")
    if result["success"]:
        print(f"  ✓ Done: {name}")
        print(f"  GammaDoc: {result['gammadoc']}")
        print(f"\n  Next steps:")
        print(f"  1. Open the GammaDoc file above")
        print(f"  2. Paste into Gamma.app → match their brand")
        print(f"  3. Enable open tracking → publish → send")
        print(f"  4. Follow up 4-7x minimum (most sales close at touch 4-7)")
    else:
        print(f"  ✗ Pipeline failed for: {name}")
    print(f"{'='*60}\n")

    return result


def run_batch(csv_path: str) -> list[dict]:
    """Run the Dream 100 pipeline for multiple prospects from a CSV."""
    p = Path(csv_path)
    if not p.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    results = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n[batch] Processing {len(rows)} prospects from {csv_path}")

    for i, row in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}]", end="")
        result = run_single(
            name=row.get("name", "Unknown"),
            website=row.get("website", ""),
            niche=row.get("niche", ""),
            offer=row.get("offer", ""),
            platform=row.get("platform", "meta"),
        )
        results.append(result)

    # Save batch summary
    tmp = Path(".tmp")
    tmp.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = tmp / f"dream100_batch_{ts}.json"
    summary_path.write_text(json.dumps(results, indent=2))

    succeeded = sum(1 for r in results if r["success"])
    print(f"\n[batch] Complete: {succeeded}/{len(rows)} succeeded")
    print(f"[batch] Summary saved: {summary_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Dream 100 master pipeline — research → assets → GammaDoc"
    )
    # Single prospect args
    parser.add_argument("--name", help="Prospect name")
    parser.add_argument("--website", help="Their website URL")
    parser.add_argument("--niche", help="Their niche/industry")
    parser.add_argument("--offer", help="What they sell")
    parser.add_argument("--platform", default="meta", choices=["meta", "youtube", "instagram", "email"], help="Primary marketing platform")
    parser.add_argument("--skip-research", action="store_true", help="Skip website research step")
    parser.add_argument("--research", help="Path to existing research JSON (skips Step 1)")
    # Batch mode
    parser.add_argument("--batch", help="Path to CSV file for batch processing")
    args = parser.parse_args()

    # ─── Batch mode ─────────────────────────────────────────────────
    if args.batch:
        run_batch(args.batch)
        return

    # ─── Single mode ────────────────────────────────────────────────
    if not args.name:
        print("ERROR: --name required (or use --batch for CSV)")
        parser.print_help()
        sys.exit(1)

    required_without_research = ["niche", "offer"]
    if not args.research and not args.skip_research:
        for r in required_without_research:
            if not getattr(args, r):
                print(f"ERROR: --{r} required")
                sys.exit(1)

    run_single(
        name=args.name,
        website=args.website,
        niche=args.niche or "",
        offer=args.offer or "",
        platform=args.platform,
        skip_research=args.skip_research,
        research_path=args.research,
    )


if __name__ == "__main__":
    main()
