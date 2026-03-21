#!/usr/bin/env python3
"""
Script: sop_coverage_analyzer.py
Purpose: Analyze the relationship between scripts, SOPs, agents, and directives.
         Finds orphaned SOPs, uncovered scripts, broken references, and gaps
         in the agent-skill-directive chain.

Usage:
  python execution/sop_coverage_analyzer.py                # Full analysis
  python execution/sop_coverage_analyzer.py --orphans      # Find orphaned directives
  python execution/sop_coverage_analyzer.py --uncovered    # Find scripts without SOPs
  python execution/sop_coverage_analyzer.py --broken       # Find broken references
  python execution/sop_coverage_analyzer.py --matrix       # Agent-directive matrix

Generates proposals for any gaps found.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
PROPOSALS_DIR = TMP_DIR / "proposals"
COVERAGE_FILE = TMP_DIR / "sop-coverage.json"


def ensure_dirs():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)


def get_all_scripts() -> list:
    """Get all Python scripts in execution/."""
    scripts = []
    exec_dir = PROJECT_ROOT / "execution"
    if exec_dir.exists():
        for f in sorted(exec_dir.glob("*.py")):
            if f.name != "__init__.py":
                scripts.append(f.name)
    return scripts


def get_all_directives() -> list:
    """Get all directive files."""
    directives = []
    dir_dir = PROJECT_ROOT / "directives"
    if dir_dir.exists():
        for f in sorted(dir_dir.glob("*.md")):
            directives.append(f.name)
    return directives


def get_all_agent_files() -> dict:
    """Get all agent/bot files mapped to their agent names."""
    agents = {}
    # SabboOS/Agents/
    agents_dir = PROJECT_ROOT / "SabboOS" / "Agents"
    if agents_dir.exists():
        for f in agents_dir.glob("*.md"):
            agents[f.stem] = str(f.relative_to(PROJECT_ROOT))

    # bots/*/
    bots_dir = PROJECT_ROOT / "bots"
    if bots_dir.exists():
        for bot_dir in bots_dir.iterdir():
            if bot_dir.is_dir() and not bot_dir.name.startswith("."):
                for f in bot_dir.glob("*.md"):
                    key = f"{bot_dir.name}/{f.stem}"
                    agents[key] = str(f.relative_to(PROJECT_ROOT))
    return agents


def scan_file_references(filepath: Path) -> set:
    """Scan a file for references to other files (scripts, directives, etc.)."""
    refs = set()
    if not filepath.exists():
        return refs
    content = filepath.read_text(encoding="utf-8", errors="ignore")

    # Match execution/*.py references
    for m in re.findall(r'execution/(\w+\.py)', content):
        refs.add(f"execution/{m}")

    # Match directives/*.md references
    for m in re.findall(r'directives/([\w-]+\.md)', content):
        refs.add(f"directives/{m}")

    # Match SabboOS/Agents/*.md references
    for m in re.findall(r'SabboOS/Agents/([\w]+\.md)', content):
        refs.add(f"SabboOS/Agents/{m}")

    # Match bots/*/ references
    for m in re.findall(r'bots/([\w-]+)/', content):
        refs.add(f"bots/{m}/")

    return refs


def find_orphaned_directives() -> list:
    """Find directives that are never referenced anywhere else."""
    directives = get_all_directives()
    all_refs = set()

    # Scan all files for references to directives
    for scan_dir in [PROJECT_ROOT / "execution", PROJECT_ROOT / "SabboOS",
                     PROJECT_ROOT / "bots", PROJECT_ROOT / "directives"]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".md", ".yaml"):
                refs = scan_file_references(f)
                for r in refs:
                    if r.startswith("directives/"):
                        all_refs.add(r.split("/")[1])

    orphans = []
    for d in directives:
        if d not in all_refs:
            orphans.append(d)
    return orphans


def find_uncovered_scripts() -> list:
    """Find scripts that have no SOP/directive mentioning them."""
    scripts = get_all_scripts()
    all_refs = set()

    # Scan directives for script references
    dir_dir = PROJECT_ROOT / "directives"
    if dir_dir.exists():
        for f in dir_dir.glob("*.md"):
            refs = scan_file_references(f)
            for r in refs:
                if r.startswith("execution/"):
                    all_refs.add(r.split("/")[1])

    # Also check agent files
    for scan_dir in [PROJECT_ROOT / "SabboOS", PROJECT_ROOT / "bots"]:
        if scan_dir.exists():
            for f in scan_dir.rglob("*.md"):
                refs = scan_file_references(f)
                for r in refs:
                    if r.startswith("execution/"):
                        all_refs.add(r.split("/")[1])

    uncovered = []
    for s in scripts:
        if s not in all_refs:
            uncovered.append(s)
    return uncovered


def find_broken_references() -> list:
    """Find references to files that don't exist."""
    broken = []

    for scan_dir in [PROJECT_ROOT / "directives", PROJECT_ROOT / "execution",
                     PROJECT_ROOT / "SabboOS", PROJECT_ROOT / "bots"]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*"):
            if not f.is_file() or f.suffix not in (".py", ".md", ".yaml"):
                continue
            refs = scan_file_references(f)
            for ref in refs:
                ref_path = PROJECT_ROOT / ref
                # For directory refs (bots/name/), check dir exists
                if ref.endswith("/"):
                    if not ref_path.exists():
                        broken.append({
                            "source": str(f.relative_to(PROJECT_ROOT)),
                            "reference": ref,
                            "type": "directory",
                        })
                else:
                    if not ref_path.exists():
                        broken.append({
                            "source": str(f.relative_to(PROJECT_ROOT)),
                            "reference": ref,
                            "type": "file",
                        })
    return broken


def build_agent_directive_matrix() -> dict:
    """Build a matrix showing which agents reference which directives."""
    matrix = {}
    agents = get_all_agent_files()

    for agent_key, agent_path in agents.items():
        fp = PROJECT_ROOT / agent_path
        refs = scan_file_references(fp)
        directive_refs = [r for r in refs if r.startswith("directives/")]
        script_refs = [r for r in refs if r.startswith("execution/")]
        matrix[agent_key] = {
            "file": agent_path,
            "directives": directive_refs,
            "scripts": script_refs,
        }

    return matrix


def generate_gap_proposal(gap_type: str, details: str, target_agent: str = "CEO") -> str:
    """Generate a proposal for a coverage gap."""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = list(PROPOSALS_DIR.glob(f"TP-{today}-*.yaml"))
    seq = len(existing) + 1
    pid = f"TP-{today}-{seq:03d}"

    content = f"""# Training Proposal: {pid}

proposal_id: "{pid}"
created: "{now}"
status: "pending"
theme: "coverage-gap"

# WHO
target_agent: "{target_agent}"
target_file: "auto-detect"

# WHAT
upgrade_type: "sop"
title: "Coverage gap: {gap_type}"
description: |
  {details}

# WHY
trigger: "SOP Coverage Analyzer"
evidence: "Automated scan detected gap"
expected_impact: "Close coverage gap in system documentation"

# HOW
change_type: "review"
proposed_content: |
  {details[:300]}

# RISK
risk_level: "low"
rollback_plan: "N/A — documentation only"
dependencies: []
"""
    (PROPOSALS_DIR / f"{pid}.yaml").write_text(content)
    return pid


def run_full_analysis():
    """Run complete SOP coverage analysis."""
    print(f"\n{'=' * 60}")
    print(f"  SOP COVERAGE ANALYSIS — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}")

    # Scripts
    scripts = get_all_scripts()
    directives = get_all_directives()
    agents = get_all_agent_files()
    print(f"\n  Inventory: {len(scripts)} scripts, {len(directives)} directives, {len(agents)} agent files")

    # Orphaned directives
    print(f"\n{'─' * 60}")
    print(f"  ORPHANED DIRECTIVES (never referenced)")
    print(f"{'─' * 60}")
    orphans = find_orphaned_directives()
    if orphans:
        for o in orphans:
            print(f"    {o}")
        print(f"  → {len(orphans)} orphaned directive(s)")
    else:
        print(f"    None — all directives are referenced.")

    # Uncovered scripts
    print(f"\n{'─' * 60}")
    print(f"  UNCOVERED SCRIPTS (no SOP documentation)")
    print(f"{'─' * 60}")
    uncovered = find_uncovered_scripts()
    if uncovered:
        for u in uncovered:
            print(f"    {u}")
        print(f"  → {len(uncovered)} uncovered script(s)")
    else:
        print(f"    None — all scripts have SOP coverage.")

    # Broken references
    print(f"\n{'─' * 60}")
    print(f"  BROKEN REFERENCES")
    print(f"{'─' * 60}")
    broken = find_broken_references()
    if broken:
        for b in broken:
            print(f"    {b['source']} → {b['reference']} ({b['type']} MISSING)")
        print(f"  → {len(broken)} broken reference(s)")
    else:
        print(f"    None — all references valid.")

    # Agent-directive matrix
    print(f"\n{'─' * 60}")
    print(f"  AGENT-DIRECTIVE MATRIX")
    print(f"{'─' * 60}")
    matrix = build_agent_directive_matrix()
    for agent, info in sorted(matrix.items()):
        d_count = len(info["directives"])
        s_count = len(info["scripts"])
        print(f"    {agent:<30s} {d_count} directives, {s_count} scripts")

    # Save coverage data
    coverage = {
        "timestamp": datetime.now().isoformat(),
        "scripts_total": len(scripts),
        "directives_total": len(directives),
        "agents_total": len(agents),
        "orphaned_directives": orphans,
        "uncovered_scripts": uncovered,
        "broken_references": broken,
        "matrix": matrix,
    }
    COVERAGE_FILE.write_text(json.dumps(coverage, indent=2, default=str))

    # Generate proposals for critical gaps
    proposals = 0
    if len(uncovered) >= 3:
        pid = generate_gap_proposal(
            f"{len(uncovered)} scripts lack SOP coverage",
            f"Scripts without documentation: {', '.join(uncovered[:5])}. Create SOPs to ensure system reliability."
        )
        proposals += 1
        print(f"\n  Generated proposal {pid}: SOP coverage gap")

    if broken:
        pid = generate_gap_proposal(
            f"{len(broken)} broken references found",
            f"Broken refs: {', '.join(b['reference'] for b in broken[:5])}. Fix or remove stale references."
        )
        proposals += 1
        print(f"  Generated proposal {pid}: Broken references")

    print(f"\n{'─' * 60}")
    print(f"  Coverage saved to {COVERAGE_FILE}")
    if proposals:
        print(f"  Generated {proposals} proposal(s) for critical gaps.")
    print(f"{'─' * 60}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SOP Coverage Analyzer")
    parser.add_argument("--orphans", action="store_true", help="Find orphaned directives")
    parser.add_argument("--uncovered", action="store_true", help="Find uncovered scripts")
    parser.add_argument("--broken", action="store_true", help="Find broken references")
    parser.add_argument("--matrix", action="store_true", help="Agent-directive matrix")
    args = parser.parse_args()

    ensure_dirs()

    if args.orphans:
        orphans = find_orphaned_directives()
        for o in orphans:
            print(f"  {o}")
    elif args.uncovered:
        uncovered = find_uncovered_scripts()
        for u in uncovered:
            print(f"  {u}")
    elif args.broken:
        broken = find_broken_references()
        for b in broken:
            print(f"  {b['source']} → {b['reference']}")
    elif args.matrix:
        matrix = build_agent_directive_matrix()
        print(json.dumps(matrix, indent=2))
    else:
        run_full_analysis()


if __name__ == "__main__":
    main()
