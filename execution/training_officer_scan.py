#!/usr/bin/env python3
"""
Script: training_officer_scan.py
Purpose: Scan the system for changes, detect agent improvement opportunities,
         generate Training Proposals, and output the Training Officer Report.

Usage:
  python execution/training_officer_scan.py              # Full scan + proposals
  python execution/training_officer_scan.py --dry-run    # Scan only, no writes
  python execution/training_officer_scan.py --list-pending   # List pending proposals
  python execution/training_officer_scan.py --show TP-2026-02-21-001  # Show proposal
  python execution/training_officer_scan.py --health     # Agent health check only
  python execution/training_officer_scan.py --themes     # Group pending proposals by theme
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import subprocess

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))
SHARED_ROOT = Path("/Users/Shared/antigravity")

# Output directories
TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
PROPOSALS_DIR = TMP_DIR / "proposals"
SCANS_DIR = TMP_DIR / "scans"
LAST_SCAN_FILE = TMP_DIR / "last-scan.json"
HEALTH_FILE = TMP_DIR / "agent-health.json"
LEARNINGS_FILE = TMP_DIR / "learnings.md"
QUALITY_FILE = TMP_DIR / "quality-scores.json"

# Monitored directories
MONITORED_DIRS = [
    PROJECT_ROOT / "directives",
    PROJECT_ROOT / "execution",
    PROJECT_ROOT / "SabboOS" / "Agents",
    PROJECT_ROOT / "SabboOS",
    PROJECT_ROOT / "bots",
    PROJECT_ROOT / "clients",
    SHARED_ROOT / "memory",
    SHARED_ROOT / "proposals",
]

# File extensions to monitor
MONITORED_EXTS = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}


# ─── Skill Ownership Map ──────────────────────────────────────────────────────
# Each skill domain has ONE owner agent. Only the owner gets full skill training.
# Other agents get awareness-only context (brief mention + delegation pointer).

SKILL_OWNERSHIP = {
    # Outreach-owned skills (Dream 100 is EXCLUSIVELY outreach)
    "dream 100":       "outreach",
    "dream100":        "outreach",
    "gammadoc":        "outreach",
    "cold email":      "outreach",
    "cold outreach":   "outreach",
    "sales call":      "outreach",
    "objection":       "outreach",
    "closer":          "outreach",
    "setter":          "outreach",
    "follow up":       "outreach",
    "dm outreach":     "outreach",
    # Content-owned
    "vsl script":      "content",
    "vsl framework":   "content",
    "organic content": "content",
    "social media":    "content",
    "tiktok":          "content",
    "instagram":       "content",
    "reel":            "content",
    # Ads-copy-owned
    "ad creative":     "ads-copy",
    "meta ads":        "ads-copy",
    "facebook ads":    "ads-copy",
    "youtube ads":     "ads-copy",
    "ad hook":         "ads-copy",
    "cpl":             "ads-copy",
    "roas":            "ads-copy",
    # WebBuild-owned
    "landing page":    "WebBuild",
    "website build":   "WebBuild",
    "funnel page":     "WebBuild",
    "html build":      "WebBuild",
    "tailwind":        "WebBuild",
    # Lead-gen-owned
    "lead scrape":     "lead-gen",
    "google maps":     "lead-gen",
    "prospect list":   "lead-gen",
    "lead generation": "lead-gen",
    # Amazon-owned
    "fba":             "amazon",
    "ppc campaign":    "amazon",
    "listing optimization": "amazon",
    "inventory management": "amazon",
    "asin":            "amazon",
    # Sourcing-owned
    "sourcing pipeline": "sourcing",
    "retail arbitrage": "sourcing",
    "online arbitrage": "sourcing",
    "keepa":           "sourcing",
    "reverse sourcing": "sourcing",
    # CEO-owned
    "kpi":             "CEO",
    "revenue target":  "CEO",
    "constraint":      "CEO",
    "business strategy": "CEO",
    "delegation":      "CEO",
}

# Agent registry
AGENT_REGISTRY = {
    "CEO": {
        "file": "SabboOS/Agents/CEO.md",
        "domain": "Strategy, KPIs, constraints, delegation",
        "keywords": ["kpi", "revenue", "constraint", "brief", "optimization", "metric",
                      "churn", "retention", "close rate", "pipeline", "delegation"],
    },
    "WebBuild": {
        "file": "SabboOS/Agents/WebBuild.md",
        "domain": "Web assets, copy generation, funnels",
        "keywords": ["website", "landing page", "html", "tailwind", "copy",
                      "headline", "cta", "funnel", "deploy"],
    },
    "ads-copy": {
        "file": "bots/ads-copy/",
        "domain": "Paid advertising, ad creative",
        "keywords": ["ad", "creative", "hook", "meta", "facebook", "youtube",
                      "cpl", "ctr", "roas", "targeting", "audience"],
    },
    "content": {
        "file": "bots/content/",
        "domain": "Organic content, VSL scripts, social",
        "keywords": ["content", "social", "instagram", "tiktok", "youtube",
                      "post", "reel", "story", "organic", "vsl"],
    },
    "outreach": {
        "file": "bots/outreach/",
        "domain": "Cold outreach, sales, Dream 100",
        "keywords": ["outreach", "email", "dm", "cold", "dream 100", "dream100",
                      "objection", "sales call", "closer", "setter", "follow up",
                      "gammadoc"],
    },
    "lead-gen": {
        "file": "directives/lead-gen-sop.md",
        "domain": "Lead generation, prospect research",
        "keywords": ["lead", "scrape", "google maps", "prospect", "database",
                      "csv", "contact", "business list"],
    },
    "amazon": {
        "file": "bots/amazon/",
        "domain": "Amazon FBA, PPC, listings",
        "keywords": ["amazon", "fba", "ppc", "listing", "asin", "bsr",
                      "supplier", "inventory", "fulfillment"],
    },
    "sourcing": {
        "file": "SabboOS/Agents/Sourcing.md",
        "domain": "FBA Sourcing, arbitrage",
        "keywords": ["sourcing", "retail", "walmart", "target", "costco",
                      "arbitrage", "roi", "profit", "upc", "keepa"],
    },
    "CodeSec": {
        "file": "SabboOS/Agents/CodeSec.md",
        "domain": "Code security, quality, infrastructure integrity",
        "keywords": ["security", "vulnerability", "injection", "hardcoded", "secret",
                      "permission", "syntax error", "import error", "best practice",
                      "codesec", "csr", "infrastructure"],
    },
    "AutomationBuilder": {
        "file": "SabboOS/Agents/AutomationBuilder.md",
        "domain": "Zapier and GHL automation design, build, audit",
        "keywords": ["zapier", "zap", "gohighlevel", "ghl", "workflow", "automation",
                      "trigger", "webhook", "integration", "nurture sequence",
                      "pipeline automation", "sms sequence", "email sequence"],
    },
    "project-manager": {
        "file": "bots/project-manager/",
        "domain": "Project tracking, milestones, tasks, dependencies, congruence",
        "keywords": ["project", "milestone", "deadline", "blocker", "congruence",
                      "health score", "at-risk", "workload", "dependency", "task"],
    },
}


# ─── Utilities ────────────────────────────────────────────────────────────────

def ensure_dirs():
    """Create output directories if they don't exist."""
    for d in [TMP_DIR, PROPOSALS_DIR, SCANS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_env():
    """Load .env file from project root."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_last_scan() -> dict:
    """Load the last scan state."""
    if LAST_SCAN_FILE.exists():
        return json.loads(LAST_SCAN_FILE.read_text())
    return {"last_scan": None, "file_hashes": {}}


def save_last_scan(state: dict):
    """Save current scan state."""
    LAST_SCAN_FILE.write_text(json.dumps(state, indent=2, default=str))


def get_monitored_files() -> dict:
    """Get all monitored files with their modification times."""
    files = {}
    for dir_path in MONITORED_DIRS:
        if not dir_path.exists():
            continue
        for f in dir_path.rglob("*"):
            if (f.is_file()
                    and f.suffix.lower() in MONITORED_EXTS
                    and not any(part.startswith(".") for part in f.parts)
                    and ".tmp" not in str(f)):
                try:
                    files[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
    return files


def get_next_proposal_id() -> str:
    """Generate the next sequential proposal ID for today."""
    today = datetime.now().strftime("%Y-%m-%d")
    existing = list(PROPOSALS_DIR.glob(f"TP-{today}-*.yaml"))
    seq = len(existing) + 1
    return f"TP-{today}-{seq:03d}"


def load_learnings() -> list:
    """Load rejection learnings to inform future proposals."""
    if not LEARNINGS_FILE.exists():
        return []
    content = LEARNINGS_FILE.read_text(encoding="utf-8", errors="ignore")
    learnings = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            learnings.append(line)
    return learnings[-20:]  # Last 20 learnings


# ─── Change Detection ────────────────────────────────────────────────────────

def detect_changes(last_scan: dict) -> tuple:
    """Compare current files to last scan. Returns (new, modified, deleted)."""
    current_files = get_monitored_files()
    old_hashes = last_scan.get("file_hashes", {})

    new_files = []
    modified_files = []
    deleted_files = []

    for path, mtime in current_files.items():
        if path not in old_hashes:
            new_files.append(path)
        elif mtime > old_hashes[path]:
            modified_files.append(path)

    for path in old_hashes:
        if path not in current_files:
            deleted_files.append(path)

    return new_files, modified_files, deleted_files


# ─── Agent Matching (Ownership-Aware) ────────────────────────────────────────

def get_skill_owner(text: str) -> Optional[str]:
    """Check if content matches a skill with a designated owner."""
    text_lower = text.lower()
    for skill_phrase, owner in SKILL_OWNERSHIP.items():
        if skill_phrase in text_lower:
            return owner
    return None


def match_agents(content: str, filename: str) -> list:
    """
    Determine which agents should receive a proposal for this file.

    Ownership rules:
    1. If the file content matches a skill with a designated owner,
       ONLY the owner agent gets a full proposal.
    2. If the file is inside an agent's own directory, that agent gets it.
    3. General keyword matching (2+ hits) for files without clear ownership.
    4. Files with no match default to CEO.
    """
    text = (content + " " + filename).lower()

    # Rule 1: Check skill ownership — if a file is about Dream 100,
    # ONLY the outreach agent gets it, not everyone
    skill_owner = get_skill_owner(text)
    if skill_owner:
        return [skill_owner]

    # Rule 2: Check if file lives inside an agent's directory
    for agent_name, info in AGENT_REGISTRY.items():
        agent_file = info["file"]
        if agent_file.endswith("/") and agent_file in filename:
            return [agent_name]

    # Rule 3: Keyword matching with ownership guard
    matches = []
    scores = {}
    for agent_name, info in AGENT_REGISTRY.items():
        score = sum(1 for kw in info["keywords"] if kw in text)
        if score >= 2:
            scores[agent_name] = score

    if scores:
        # Return only the top-scoring agent to avoid duplication
        best = max(scores, key=scores.get)
        matches.append(best)
        # Add secondary agents only if they score within 1 of the best
        # AND the content isn't owned by a specific skill
        best_score = scores[best]
        for agent, score in scores.items():
            if agent != best and score >= best_score - 1 and score >= 3:
                matches.append(agent)

    # Rule 4: Fallback — general system changes go to CEO
    if not matches:
        matches.append("CEO")

    return matches


def classify_upgrade_type(filepath: str, content: str) -> str:
    """Determine what kind of upgrade this change represents."""
    fp = filepath.lower()
    if "/directives/" in fp:
        return "sop"
    elif "/execution/" in fp and fp.endswith(".py"):
        return "tool"
    elif "/agents/" in fp:
        return "bio"
    elif "/clients/" in fp or "/memory/" in fp:
        return "context"
    elif "skills" in fp or "training" in fp:
        return "skill"
    else:
        return "context"


# ─── LLM Backend ─────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 512) -> str:
    """Call Claude via CLI (Max plan) or fall back to API if available."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # Try direct API first if key exists
    if HAS_ANTHROPIC and api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except Exception as e:
            err_str = str(e)
            if "credit balance" not in err_str and "authentication" not in err_str.lower():
                raise  # Re-raise non-billing errors
            # Fall through to CLI

    # Use claude CLI (Max plan) — no API key needed
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    clean_cwd = "/tmp/claude-proxy-workspace"
    os.makedirs(clean_cwd, exist_ok=True)

    result = subprocess.run(
        ["claude", "--print", "--model", "haiku", "-p", prompt],
        capture_output=True, text=True, timeout=120, env=env, cwd=clean_cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:500]}")

    # Strip status line if leaked
    lines = result.stdout.strip().split("\n")
    cleaned = [l for l in lines if not (l.strip().startswith("~$") and "active" in l and "queued" in l)]
    return "\n".join(cleaned).strip()


# ─── Proposal Generation ─────────────────────────────────────────────────────

def generate_proposal_content(filepath: str, content: str, change_type: str,
                               agent: str, learnings: list) -> Optional[dict]:
    """Use Claude to generate a concise proposal for an agent upgrade."""
    preview = content[:3000]
    filename = Path(filepath).name

    learnings_context = ""
    if learnings:
        learnings_context = "\n\nPast rejection learnings (avoid repeating these patterns):\n" + "\n".join(f"- {l}" for l in learnings[-5:])

    prompt = f"""You are the Training Officer for SabboOS. A file has changed and you need to determine how it should improve the "{agent}" agent.

Changed file: {filename}
File path: {filepath}
Change type: {change_type} (new file or modification)

File content preview:
{preview}

Agent "{agent}" handles: {AGENT_REGISTRY.get(agent, {}).get('domain', 'general tasks')}

IMPORTANT OWNERSHIP RULES:
- This proposal is specifically for the "{agent}" agent ONLY
- Do NOT suggest content that belongs to a different agent's domain
- Dream 100, cold outreach, GammaDoc → ONLY for outreach agent
- VSL scripts, organic content → ONLY for content agent
- Ad creative, hooks, Meta/YouTube ads → ONLY for ads-copy agent
- Landing pages, website builds → ONLY for WebBuild agent
- If the file content is not relevant to "{agent}", set relevance_score to 1
{learnings_context}

Generate a training proposal. Respond with valid JSON only:
{{
  "title": "One-line summary of the proposed upgrade (max 80 chars)",
  "description": "2-3 sentences: what should change in the agent and why",
  "upgrade_type": "skill|context|memory|tool|sop|bio",
  "expected_impact": "One sentence: what improves if this is applied",
  "proposed_content": "The exact text to append/add to the agent's skills or context (keep concise, 3-8 lines max)",
  "risk_level": "low|medium|high",
  "relevance_score": 1-10,
  "theme": "A 2-3 word category like: outreach, content, ads, sourcing, systems, compliance, analytics"
}}

Rules:
- Only propose changes with relevance_score >= 5
- Be specific, not vague
- proposed_content should be ready to paste into the agent file
- If the file isn't relevant to this agent, set relevance_score to 1"""

    try:
        raw = _call_llm(prompt)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"[training-officer] WARNING: Proposal generation failed for {filename} → {agent}: {e}")
        return None


def write_proposal(proposal_id: str, filepath: str, agent: str,
                   upgrade_data: dict, change_type: str) -> Path:
    """Write a proposal YAML file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    agent_info = AGENT_REGISTRY.get(agent, {})
    target_file = agent_info.get("file", f"SabboOS/Agents/{agent}.md")
    theme = upgrade_data.get("theme", "general")

    content = f"""# Training Proposal: {proposal_id}

proposal_id: "{proposal_id}"
created: "{now}"
status: "pending"
theme: "{theme}"

# WHO
target_agent: "{agent}"
target_file: "{target_file}"

# WHAT
upgrade_type: "{upgrade_data.get('upgrade_type', 'context')}"
title: "{upgrade_data.get('title', 'Untitled upgrade')}"
description: |
  {upgrade_data.get('description', 'No description.')}

# WHY
trigger: "File changed: {Path(filepath).name}"
evidence: "Detected change in {filepath}"
expected_impact: "{upgrade_data.get('expected_impact', 'Improves agent capability')}"

# HOW
change_type: "append"
proposed_content: |
  {upgrade_data.get('proposed_content', '# No content generated')}

# RISK
risk_level: "{upgrade_data.get('risk_level', 'low')}"
rollback_plan: "Remove the appended content from {target_file}"
dependencies: []
"""
    proposal_path = PROPOSALS_DIR / f"{proposal_id}.yaml"
    proposal_path.write_text(content)
    return proposal_path


# ─── CEO Brief Analysis ──────────────────────────────────────────────────────

def read_latest_ceo_brief() -> Optional[dict]:
    """Read today's CEO brief if it exists."""
    ceo_dir = PROJECT_ROOT / ".tmp" / "ceo"
    if not ceo_dir.exists():
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    brief_file = ceo_dir / f"brief_{today}.md"
    if not brief_file.exists():
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        brief_file = ceo_dir / f"brief_{yesterday}.md"
        if not brief_file.exists():
            return None

    content = brief_file.read_text(encoding="utf-8", errors="ignore")
    result = {"file": str(brief_file), "content": content}

    if "CONSTRAINT OF THE DAY" in content:
        lines = content.split("CONSTRAINT OF THE DAY")[1].split("\n")
        constraint_lines = [l.strip() for l in lines[1:6] if l.strip() and not l.startswith("━")]
        result["constraint"] = " ".join(constraint_lines)

    return result


# ─── CHANGELOG Analysis ──────────────────────────────────────────────────────

def read_new_changelog_entries(last_scan_time: Optional[str]) -> list:
    """Read CHANGELOG entries added since last scan."""
    changelog = PROJECT_ROOT / "SabboOS" / "CHANGELOG.md"
    if not changelog.exists():
        return []

    content = changelog.read_text(encoding="utf-8", errors="ignore")
    entries = []
    for line in content.splitlines():
        if line.startswith("|") and "---" not in line and "Date" not in line:
            entries.append(line.strip())

    if not last_scan_time:
        return entries

    scan_date = last_scan_time[:10] if last_scan_time else "2000-01-01"
    recent = [e for e in entries if e.split("|")[1].strip() >= scan_date]
    return recent


# ─── Agent Health ─────────────────────────────────────────────────────────────

def compute_agent_health() -> dict:
    """Compute health scorecard for all agents."""
    health = {}
    now = datetime.now()
    stale_threshold = timedelta(days=14)

    for agent_name, info in AGENT_REGISTRY.items():
        agent_path = PROJECT_ROOT / info["file"]
        if agent_path.exists() and agent_path.is_file():
            mtime = datetime.fromtimestamp(agent_path.stat().st_mtime)
            days_old = (now - mtime).days
            status = "current" if (now - mtime) < stale_threshold else "stale"
        elif agent_path.exists() and agent_path.is_dir():
            newest = max(
                (f.stat().st_mtime for f in agent_path.rglob("*") if f.is_file()),
                default=0
            )
            if newest:
                mtime = datetime.fromtimestamp(newest)
                days_old = (now - mtime).days
                status = "current" if (now - mtime) < stale_threshold else "stale"
            else:
                mtime = None
                days_old = -1
                status = "missing"
        else:
            mtime = None
            days_old = -1
            status = "missing"

        health[agent_name] = {
            "last_updated": mtime.strftime("%Y-%m-%d") if mtime else "N/A",
            "days_since_update": days_old,
            "status": status,
            "domain": info["domain"],
        }

    HEALTH_FILE.write_text(json.dumps(health, indent=2, default=str))
    return health


# ─── Pending Proposals ───────────────────────────────────────────────────────

def parse_proposal(filepath: Path) -> dict:
    """Parse a proposal YAML file into a dict."""
    content = filepath.read_text()
    info = {"file": filepath.name, "id": filepath.stem, "raw": content}
    for line in content.splitlines():
        if line.startswith("target_agent:"):
            info["agent"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("upgrade_type:"):
            info["type"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("title:"):
            info["title"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("status:"):
            info["status"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("theme:"):
            info["theme"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
    return info


def list_pending_proposals() -> list:
    """List all pending proposals."""
    pending = []
    if not PROPOSALS_DIR.exists():
        return pending

    for f in sorted(PROPOSALS_DIR.glob("TP-*.yaml")):
        info = parse_proposal(f)
        if info.get("status") == "pending":
            pending.append(info)
    return pending


def list_proposals_by_theme() -> dict:
    """Group pending proposals by theme for batch review."""
    pending = list_pending_proposals()
    themes = defaultdict(list)
    for p in pending:
        theme = p.get("theme", "general")
        themes[theme].append(p)
    return dict(themes)


# ─── Rejection Learning ──────────────────────────────────────────────────────

def record_rejection(proposal_id: str, reason: str):
    """Record a rejection with reason to learnings file for future improvement."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"| {now} | {proposal_id} | {reason} |"

    if not LEARNINGS_FILE.exists():
        header = """# Training Officer — Rejection Learnings
> Auto-populated when proposals are rejected. Used to improve future proposals.

| Date | Proposal | Reason |
|---|---|---|
"""
        LEARNINGS_FILE.write_text(header + entry + "\n")
    else:
        with open(LEARNINGS_FILE, "a") as f:
            f.write(entry + "\n")

    print(f"[training-officer] Learning recorded: {proposal_id} — {reason}")


# ─── Report Generation ───────────────────────────────────────────────────────

def generate_report(new_files: list, modified_files: list, deleted_files: list,
                    proposals_generated: int, health: dict,
                    ceo_brief: Optional[dict], changelog_entries: list) -> str:
    """Generate the Training Officer Report."""
    today = datetime.now().strftime("%A, %Y-%m-%d")
    pending = list_pending_proposals()

    constraint = "None — system healthy"
    if ceo_brief and "constraint" in ceo_brief:
        constraint = ceo_brief["constraint"][:80]

    agent_counts = {}
    for p in pending:
        agent = p.get("agent", "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    # Theme grouping
    themes = defaultdict(int)
    for p in pending:
        themes[p.get("theme", "general")] += 1

    report = f"""
{'=' * 60}
  TRAINING OFFICER REPORT — {today}
{'=' * 60}

{'─' * 60}
 CHANGES DETECTED
{'─' * 60}

 New files:                          {len(new_files)}
 Modified files:                     {len(modified_files)}
 Deleted files:                      {len(deleted_files)}
 New changelog entries:              {len(changelog_entries)}
 CEO constraint (latest):            {constraint}

{'─' * 60}
 NEW PROPOSALS GENERATED
{'─' * 60}

 Proposals generated this scan:      {proposals_generated}

{'─' * 60}
 PENDING PROPOSALS (AWAITING APPROVAL)
{'─' * 60}

 Total pending:                      {len(pending)}
"""

    if pending:
        report += "\n By agent:\n"
        for agent, count in sorted(agent_counts.items()):
            report += f"   {agent:20s} {count} proposal(s)\n"

        if themes:
            report += "\n By theme:\n"
            for theme, count in sorted(themes.items(), key=lambda x: -x[1]):
                report += f"   {theme:20s} {count} proposal(s)\n"

        report += "\n Proposals:\n"
        for p in pending:
            theme_tag = f"[{p.get('theme', '?')}]"
            report += f"   {p.get('id', '?'):25s} | {p.get('agent', '?'):15s} | {theme_tag:15s} | {p.get('title', 'Untitled')}\n"

    report += f"""
{'─' * 60}
 AGENT HEALTH SCORECARD
{'─' * 60}

 {'Agent':<15s} {'Last Updated':<15s} {'Domain':<30s} {'Status':<10s}
 {'─' * 70}
"""
    for agent_name, h in health.items():
        status_icon = "current" if h["status"] == "current" else ("STALE" if h["status"] == "stale" else "MISSING")
        report += f" {agent_name:<15s} {h['last_updated']:<15s} {h['domain']:<30s} {status_icon:<10s}\n"

    if pending:
        top = pending[0]
        report += f"""
{'─' * 60}
 RECOMMENDED PRIORITY
{'─' * 60}

 Review {top.get('id', '?')} first — {top.get('title', 'see proposal details')}.
"""

    report += f"""
{'─' * 60}
 Commands:
   --show ID         Show proposal details
   --list-pending    List all pending
   --themes          Group by theme for batch review
   --health          Agent health only
{'─' * 60}
"""
    return report


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Training Officer — Agent improvement scanner")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no proposals written")
    parser.add_argument("--list-pending", action="store_true", help="List pending proposals")
    parser.add_argument("--show", type=str, help="Show a specific proposal by ID")
    parser.add_argument("--health", action="store_true", help="Agent health check only")
    parser.add_argument("--themes", action="store_true", help="Group pending proposals by theme")
    args = parser.parse_args()

    load_env()
    ensure_dirs()

    # ── List pending ──
    if args.list_pending:
        pending = list_pending_proposals()
        if not pending:
            print("[training-officer] No pending proposals.")
            return
        print(f"\n[training-officer] {len(pending)} pending proposal(s):\n")
        for p in pending:
            theme_tag = f"[{p.get('theme', '?')}]"
            print(f"  {p.get('id', '?'):25s} | {p.get('agent', '?'):15s} | {theme_tag:15s} | {p.get('title', 'Untitled')}")
        print()
        return

    # ── Theme grouping ──
    if args.themes:
        themes = list_proposals_by_theme()
        if not themes:
            print("[training-officer] No pending proposals.")
            return
        print(f"\n[training-officer] Proposals grouped by theme:\n")
        for theme, proposals in sorted(themes.items()):
            print(f"  [{theme}] — {len(proposals)} proposal(s):")
            for p in proposals:
                print(f"    {p.get('id', '?'):25s} | {p.get('agent', '?'):15s} | {p.get('title', 'Untitled')}")
            print()
        return

    # ── Show specific proposal ──
    if args.show:
        proposal_file = PROPOSALS_DIR / f"{args.show}.yaml"
        if not proposal_file.exists():
            print(f"[training-officer] Proposal not found: {args.show}")
            sys.exit(1)
        print(proposal_file.read_text())
        return

    # ── Health check only ──
    if args.health:
        health = compute_agent_health()
        print(f"\n[training-officer] Agent Health Scorecard\n")
        print(f" {'Agent':<15s} {'Last Updated':<15s} {'Domain':<30s} {'Status':<10s}")
        print(f" {'─' * 70}")
        for name, h in health.items():
            status = "current" if h["status"] == "current" else ("STALE" if h["status"] == "stale" else "MISSING")
            print(f" {name:<15s} {h['last_updated']:<15s} {h['domain']:<30s} {status:<10s}")
        print()
        return

    # ── Full scan ──

    last_scan = load_last_scan()
    last_scan_time = last_scan.get("last_scan")

    print(f"[training-officer] Starting scan...")
    if last_scan_time:
        print(f"[training-officer] Last scan: {last_scan_time}")
    else:
        print(f"[training-officer] First scan — establishing baseline.")

    # Step 1-2: Detect changes
    new_files, modified_files, deleted_files = detect_changes(last_scan)
    changed = new_files + modified_files
    print(f"[training-officer] Found {len(new_files)} new, {len(modified_files)} modified, {len(deleted_files)} deleted files.")

    # Step 3: CEO brief
    ceo_brief = read_latest_ceo_brief()
    if ceo_brief and "constraint" in ceo_brief:
        print(f"[training-officer] CEO constraint: {ceo_brief['constraint'][:60]}...")

    # Step 4: CHANGELOG
    changelog_entries = read_new_changelog_entries(last_scan_time)
    if changelog_entries:
        print(f"[training-officer] {len(changelog_entries)} new changelog entries.")

    # Step 5: Load rejection learnings
    learnings = load_learnings()
    if learnings:
        print(f"[training-officer] Loaded {len(learnings)} rejection learnings.")

    # Step 6: Generate proposals — batched by agent, smart-filtered
    proposals_generated = 0
    auto_applied = 0

    if not args.dry_run and changed:
        # ── Smart filter: only files that affect agent behavior ──
        actionable = []
        skipped = 0
        for fp in changed:
            p = Path(fp)
            name = p.name.lower()
            fp_lower = fp.lower()

            # Skip non-actionable files
            if any(skip in fp_lower for skip in [
                ".tmp/", "/memory/", "/proposals/", "/session-snapshots/",
                "/scans/", "exp_0", "snapshot-", "timelog", "deadlines",
            ]):
                skipped += 1
                continue
            if name.startswith("exp_") and name.endswith(".json"):
                skipped += 1
                continue
            # Only keep files that affect agents: directives, scripts, agent defs, bot configs
            if not any(d in fp_lower for d in [
                "/directives/", "/execution/", "/agents/", "/bots/",
                "/sabbo", "/clients/",
            ]):
                skipped += 1
                continue
            # Skip tiny files
            try:
                if p.stat().st_size < 50:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            actionable.append(fp)

        print(f"[training-officer] Filtered {len(changed)} → {len(actionable)} actionable files ({skipped} skipped).")

        if not actionable:
            print(f"[training-officer] No actionable changes found.")
        else:
            # ── Group files by matched agent ──
            agent_files = defaultdict(list)
            for fp in actionable:
                try:
                    content = Path(fp).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if not content.strip():
                    continue
                agents = match_agents(content, fp)
                for agent in agents:
                    agent_files[agent].append((fp, content[:2000]))  # Cap preview

            print(f"[training-officer] Changes touch {len(agent_files)} agent(s): {', '.join(agent_files.keys())}")

            # ── One batched LLM call per agent ──
            for agent, files_and_previews in agent_files.items():
                file_summaries = []
                for fp, preview in files_and_previews[:20]:  # Cap at 20 files per agent
                    fname = Path(fp).name
                    change_type = classify_upgrade_type(fp, preview)
                    file_summaries.append(f"- **{fname}** ({change_type}): {preview[:300]}")

                file_list = "\n".join(file_summaries)
                domain = AGENT_REGISTRY.get(agent, {}).get("domain", "general tasks")

                learnings_context = ""
                if learnings:
                    learnings_context = "\n\nPast rejection learnings (avoid repeating):\n" + "\n".join(f"- {l}" for l in learnings[-5:])

                prompt = f"""You are the Training Officer for SabboOS. Multiple files have changed that are relevant to the "{agent}" agent (domain: {domain}).

Review these {len(files_and_previews)} changed files and produce the TOP 3-5 most impactful upgrades for this agent. Consolidate related changes into single proposals. Skip anything trivial.

Changed files:
{file_list}
{learnings_context}

Respond with a JSON array of proposals (3-5 max, ranked by impact). Each proposal:
{{
  "title": "One-line summary (max 80 chars)",
  "description": "2-3 sentences: what should change and why",
  "upgrade_type": "skill|context|memory|tool|sop|bio",
  "expected_impact": "One sentence: what improves",
  "proposed_content": "The exact text to append (3-8 lines max, ready to paste)",
  "risk_level": "low|medium|high",
  "relevance_score": 1-10,
  "theme": "2-3 word category",
  "source_files": ["list of filenames that triggered this"]
}}

Rules:
- Only include proposals with relevance_score >= 6
- Consolidate: if 5 files all relate to sourcing, that's 1 proposal not 5
- Be specific, not vague. proposed_content must be paste-ready.
- Return valid JSON array only, no markdown fences."""

                try:
                    raw = _call_llm(prompt, max_tokens=2048)
                    # Strip markdown fences if present
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    proposals_list = json.loads(raw.strip())
                    if not isinstance(proposals_list, list):
                        proposals_list = [proposals_list]
                except Exception as e:
                    print(f"[training-officer] WARNING: Batch proposal failed for {agent}: {e}")
                    continue

                for upgrade_data in proposals_list:
                    if upgrade_data.get("relevance_score", 0) < 6:
                        continue
                    proposal_id = get_next_proposal_id()
                    source = ", ".join(upgrade_data.get("source_files", ["batch"]))
                    write_proposal(proposal_id, source, agent, upgrade_data, "batch")
                    proposals_generated += 1

                    # Auto-apply: low risk + high relevance
                    score = upgrade_data.get("relevance_score", 0)
                    risk = upgrade_data.get("risk_level", "medium")
                    if score >= 8 and risk == "low":
                        # Auto-apply
                        proposal_path = PROPOSALS_DIR / f"{proposal_id}.yaml"
                        try:
                            from apply_proposal import parse_proposal as ap_parse, apply_proposal as ap_apply, update_proposal_status
                            parsed = ap_parse(proposal_path)
                            if ap_apply(parsed):
                                update_proposal_status(proposal_path, "applied")
                                auto_applied += 1
                                print(f"[training-officer]   [AUTO-APPLIED] {proposal_id}: {upgrade_data.get('title', '?')} → {agent}")
                                continue
                        except Exception:
                            pass  # Fall through to pending

                    print(f"[training-officer]   [PENDING] {proposal_id}: {upgrade_data.get('title', '?')} → {agent} (score={score}, risk={risk})")

            if auto_applied:
                print(f"[training-officer] Auto-applied {auto_applied} low-risk/high-impact proposals.")

    elif args.dry_run:
        print(f"[training-officer] DRY RUN — {len(changed)} files would be analyzed for proposals.")

    # Step 7: Update scan state
    if not args.dry_run:
        current_files = get_monitored_files()
        save_last_scan({
            "last_scan": datetime.now().isoformat(),
            "file_hashes": current_files,
        })

    # Step 8: Health + Report
    health = compute_agent_health()
    report = generate_report(
        new_files, modified_files, deleted_files,
        proposals_generated, health, ceo_brief, changelog_entries
    )
    print(report)

    # Save scan report
    if not args.dry_run:
        scan_file = SCANS_DIR / f"scan-{datetime.now().strftime('%Y-%m-%d-%H%M')}.md"
        scan_file.write_text(report)
        print(f"[training-officer] Report saved to {scan_file}")


if __name__ == "__main__":
    main()
