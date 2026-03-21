#!/usr/bin/env python3
"""
memory_migrate.py — One-time migration of existing memory files into the SQLite DB.

Parses brain.md, brain_archive.md, session snapshots, and MEMORY.md into
typed, categorized, searchable memories.

Usage:
    python execution/memory_migrate.py                    # Full migration
    python execution/memory_migrate.py --source brain     # Just brain.md
    python execution/memory_migrate.py --source archive   # Just brain_archive.md
    python execution/memory_migrate.py --source snapshots # Just snapshots
    python execution/memory_migrate.py --source memory    # Just MEMORY.md
    python execution/memory_migrate.py --dry-run          # Preview without writing
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from execution.memory_store import MemoryStore, DB_PATH

BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
ARCHIVE_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain_archive.md")
SNAPSHOTS_DIR = Path("/Users/Shared/antigravity/memory/session-snapshots")
MEMORY_MD_PATH = Path("/Users/sabbojb/.claude/projects/-Users-Shared-antigravity-projects-nomad-nebula/memory/MEMORY.md")

# Counters
stats = {"created": 0, "skipped_dedup": 0, "errors": 0}


def add_memory(store, dry_run=False, **kwargs):
    """Add a memory with stats tracking."""
    if dry_run:
        print("  [DRY] Would add: ({type}/{category}) {title}".format(**kwargs))
        stats["created"] += 1
        return
    result = store.add(skip_dedup=False, **kwargs)
    if result.get("status") == "created":
        stats["created"] += 1
    elif result.get("status") == "duplicate":
        stats["skipped_dedup"] += 1
    else:
        stats["errors"] += 1
        print("  ! Error adding '{}': {}".format(kwargs.get("title", "?"), result.get("error", "unknown")))


# ── Brain.md Parser ───────────────────────────────────────────────────────────

def parse_decisions_table(text):
    """Parse the Decisions Log markdown table."""
    memories = []
    # Match table rows: | date | decision | context |
    for match in re.finditer(
        r'^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\*{0,2}(.+?)\*{0,2}\s*\|\s*(.+?)\s*\|$',
        text, re.MULTILINE
    ):
        date, decision, context = match.group(1), match.group(2).strip(), match.group(3).strip()
        # Clean markdown bold
        decision = re.sub(r'\*{2}', '', decision)
        title = decision[:120] if len(decision) > 120 else decision
        memories.append({
            "type": "decision",
            "category": categorize_text(decision + " " + context),
            "title": title,
            "content": decision + ("\n\nContext: " + context if context else ""),
            "source": "brain.md import",
            "source_session": date,
            "tags": extract_tags(decision),
        })
    return memories


def parse_learnings_table(text):
    """Parse the Learnings markdown table."""
    memories = []
    for match in re.finditer(
        r'^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$',
        text, re.MULTILINE
    ):
        date, learning, source = match.group(1), match.group(2).strip(), match.group(3).strip()
        learning = re.sub(r'\*{2}', '', learning)
        title = learning[:120] if len(learning) > 120 else learning
        memories.append({
            "type": "learning",
            "category": categorize_text(learning),
            "title": title,
            "content": learning + ("\n\nSource: " + source if source else ""),
            "source": "brain.md import",
            "source_session": date,
            "tags": extract_tags(learning),
        })
    return memories


def parse_preferences(text):
    """Parse the Preferences bullet list."""
    memories = []
    # Find the Preferences section
    pref_match = re.search(r'## Preferences\n.*?\n((?:- .+\n)+)', text, re.DOTALL)
    if not pref_match:
        return memories
    for line in pref_match.group(1).strip().split('\n'):
        line = line.strip().lstrip('- ').strip()
        if not line:
            continue
        line = re.sub(r'\*{2}', '', line)
        memories.append({
            "type": "preference",
            "category": "general",
            "title": line[:120],
            "content": line,
            "source": "brain.md import",
            "tags": "preference",
        })
    return memories


def parse_asset_registry(text):
    """Parse the Asset Registry section."""
    memories = []
    # Find Asset Registry section
    asset_match = re.search(r'## Asset Registry\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if not asset_match:
        return memories
    for line in asset_match.group(1).strip().split('\n'):
        line = line.strip()
        if not line.startswith('- '):
            continue
        line = line.lstrip('- ').strip()
        # Extract file path if present
        path_match = re.match(r'`([^`]+)`\s*[—–-]\s*(.+)', line)
        if path_match:
            path, desc = path_match.group(1), path_match.group(2)
            desc = re.sub(r'\*{2}', '', desc)
            memories.append({
                "type": "asset",
                "category": categorize_text(desc),
                "title": "{} — {}".format(os.path.basename(path), desc[:80]),
                "content": "Path: {}\n{}".format(path, desc),
                "source": "brain.md import",
                "tags": "asset," + extract_tags(desc),
            })
    return memories


def parse_people(text):
    """Parse People & Relationships if present."""
    memories = []
    people_match = re.search(r'## People.*?\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if not people_match:
        return memories
    # Parse table rows
    for match in re.finditer(r'^\|\s*(.+?)\s*\|\s*(.+?)\s*\|', people_match.group(1), re.MULTILINE):
        name, details = match.group(1).strip(), match.group(2).strip()
        if name.startswith('---') or name.lower() == 'name':
            continue
        name = re.sub(r'\*{2}', '', name)
        memories.append({
            "type": "person",
            "category": "general",
            "title": name,
            "content": details,
            "source": "brain.md import",
            "tags": "person",
        })
    return memories


def parse_system_state(text):
    """Parse key facts from System State Snapshot as events."""
    memories = []
    # Extract businesses status
    biz_match = re.search(r'### Businesses\n((?:- .+\n)+)', text)
    if biz_match:
        for line in biz_match.group(1).strip().split('\n'):
            line = line.strip().lstrip('- ').strip()
            line = re.sub(r'\*{2}', '', line)
            if line:
                memories.append({
                    "type": "event",
                    "category": "agency" if "agency" in line.lower() else "amazon",
                    "title": line[:120],
                    "content": line,
                    "source": "brain.md import",
                    "tags": "business,status",
                })

    # Extract prospects
    for match in re.finditer(
        r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$',
        text, re.MULTILINE
    ):
        name = match.group(1).strip()
        if name.startswith('---') or name.lower() in ('prospect', 'student', 'agent'):
            continue
        if 'prospect' in text[max(0, match.start()-200):match.start()].lower():
            memories.append({
                "type": "person",
                "category": "sales",
                "title": "Prospect: {}".format(re.sub(r'\*{2}', '', name)),
                "content": "Source: {} | Interest: {} | Status: {} | Next: {}".format(
                    match.group(2).strip(), match.group(3).strip(),
                    match.group(4).strip(), match.group(5).strip()),
                "source": "brain.md import",
                "tags": "prospect,pipeline",
            })

    return memories


def parse_brain(store, text, is_archive=False, dry_run=False):
    """Parse all sections of brain.md."""
    source_label = "brain_archive.md import" if is_archive else "brain.md import"

    # Decisions
    decisions_section = re.search(r'## Decisions Log\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if decisions_section:
        for m in parse_decisions_table(decisions_section.group(1)):
            if is_archive:
                m["source"] = source_label
            add_memory(store, dry_run=dry_run, **m)

    # Learnings
    learnings_section = re.search(r'## Learnings\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if learnings_section:
        for m in parse_learnings_table(learnings_section.group(1)):
            if is_archive:
                m["source"] = source_label
            add_memory(store, dry_run=dry_run, **m)

    # Preferences (only from main brain, not archive)
    if not is_archive:
        for m in parse_preferences(text):
            add_memory(store, dry_run=dry_run, **m)

    # Assets
    for m in parse_asset_registry(text):
        if is_archive:
            m["source"] = source_label
        add_memory(store, dry_run=dry_run, **m)

    # People
    for m in parse_people(text):
        if is_archive:
            m["source"] = source_label
        add_memory(store, dry_run=dry_run, **m)

    # System state (only from main brain)
    if not is_archive:
        for m in parse_system_state(text):
            add_memory(store, dry_run=dry_run, **m)


# ── Snapshot Parser ───────────────────────────────────────────────────────────

def parse_snapshots(store, dry_run=False):
    """Parse session snapshot files into session_context + individual memories."""
    if not SNAPSHOTS_DIR.exists():
        print("  Snapshots directory not found: {}".format(SNAPSHOTS_DIR))
        return

    for f in sorted(SNAPSHOTS_DIR.glob("*.md")):
        text = f.read_text(errors="replace")
        # Extract date from filename
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
        date_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

        # Create session context record
        if not dry_run:
            title_match = re.match(r'#\s*(.+)', text)
            title = title_match.group(1).strip() if title_match else f.stem
            store.create_session(
                session_id="snapshot-{}".format(f.stem),
                topics=title,
                summary=text[:500],
            )

        # Extract key decisions/facts from snapshot
        # Look for "## What Happened", "## Key Decisions", "## Everything Built"
        for section_name in ["What Happened", "Key Decisions", "Summary", "What Was Built",
                             "Everything Built", "System Changes"]:
            section_match = re.search(
                r'##\s*{}\s*\n(.*?)(?=\n## |\Z)'.format(re.escape(section_name)),
                text, re.DOTALL
            )
            if section_match:
                content = section_match.group(1).strip()
                if len(content) > 50:  # Only meaningful content
                    add_memory(store, dry_run=dry_run,
                        type="event",
                        category=categorize_text(content),
                        title="Snapshot {}: {}".format(date_str, section_name),
                        content=content[:1000],
                        source="snapshot import",
                        source_session=date_str,
                        tags="snapshot,{}".format(section_name.lower().replace(" ", "_")),
                    )


# ── MEMORY.md Parser ──────────────────────────────────────────────────────────

def parse_memory_md(store, dry_run=False):
    """Parse the project MEMORY.md into memories."""
    if not MEMORY_MD_PATH.exists():
        print("  MEMORY.md not found: {}".format(MEMORY_MD_PATH))
        return

    text = MEMORY_MD_PATH.read_text(errors="replace")

    # Parse each ## section as a memory
    sections = re.split(r'\n## ', text)
    for section in sections[1:]:  # Skip header
        lines = section.strip().split('\n')
        title = lines[0].strip()
        content = '\n'.join(lines[1:]).strip()

        if not content or len(content) < 20:
            continue

        add_memory(store, dry_run=dry_run,
            type="learning",
            category=categorize_text(title + " " + content),
            title=title[:120],
            content=content[:2000],
            source="MEMORY.md import",
            tags=extract_tags(title),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def categorize_text(text):
    """Auto-categorize based on keywords."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["amazon", "fba", "asin", "keepa", "sourcing", "retailer", "wholesale"]):
        return "sourcing"
    if any(w in text_lower for w in ["agency", "retainer", "growth agency", "client"]):
        return "agency"
    if any(w in text_lower for w in ["sales", "closer", "setter", "call", "pipeline", "prospect", "objection"]):
        return "sales"
    if any(w in text_lower for w in ["content", "reel", "youtube", "instagram", "post"]):
        return "content"
    if any(w in text_lower for w in ["agent", "bot", "training officer", "ceo agent", "skill"]):
        return "agent"
    if any(w in text_lower for w in ["student", "coaching", "onboarding", "mike walker"]):
        return "student"
    if any(w in text_lower for w in ["api", "script", "python", "flask", "sqlite", "deploy", "modal"]):
        return "technical"
    return "general"


def extract_tags(text):
    """Extract relevant tags from text."""
    text_lower = text.lower()
    tags = set()
    tag_keywords = {
        "pricing": ["pricing", "price", "retainer", "$"],
        "sourcing": ["sourcing", "keepa", "asin", "retailer", "product"],
        "sales": ["sales", "closer", "call", "prospect", "objection"],
        "agent": ["agent", "bot", "training", "skill"],
        "content": ["content", "reel", "youtube", "video"],
        "infrastructure": ["api", "deploy", "modal", "flask", "database"],
    }
    for tag, keywords in tag_keywords.items():
        if any(kw in text_lower for kw in keywords):
            tags.add(tag)
    return ",".join(sorted(tags)) if tags else ""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrate existing memory files into SQLite DB")
    parser.add_argument("--source", choices=["brain", "archive", "snapshots", "memory", "all"],
                        default="all")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    store = MemoryStore(DB_PATH)

    print("Memory Migration — {}".format("DRY RUN" if args.dry_run else "LIVE"))
    print("DB: {}".format(DB_PATH))
    print()

    if args.source in ("brain", "all"):
        print("--- Parsing brain.md ---")
        if BRAIN_PATH.exists():
            text = BRAIN_PATH.read_text(errors="replace")
            parse_brain(store, text, is_archive=False, dry_run=args.dry_run)
            print("  brain.md: {} lines parsed".format(len(text.split('\n'))))
        else:
            print("  brain.md not found at {}".format(BRAIN_PATH))

    if args.source in ("archive", "all"):
        print("--- Parsing brain_archive.md ---")
        if ARCHIVE_PATH.exists():
            text = ARCHIVE_PATH.read_text(errors="replace")
            parse_brain(store, text, is_archive=True, dry_run=args.dry_run)
            print("  brain_archive.md: {} lines parsed".format(len(text.split('\n'))))
        else:
            print("  brain_archive.md not found")

    if args.source in ("snapshots", "all"):
        print("--- Parsing session snapshots ---")
        parse_snapshots(store, dry_run=args.dry_run)

    if args.source in ("memory", "all"):
        print("--- Parsing MEMORY.md ---")
        parse_memory_md(store, dry_run=args.dry_run)

    print()
    print("=== Migration Complete ===")
    print("  Created: {}".format(stats["created"]))
    print("  Skipped (dedup): {}".format(stats["skipped_dedup"]))
    print("  Errors: {}".format(stats["errors"]))

    if not args.dry_run:
        # Verify
        s = store.stats()
        print()
        print("DB Stats: {} active, {} archived".format(s["total_active"], s["total_archived"]))
        if s["by_type"]:
            print("  By type: {}".format(", ".join("{}: {}".format(k, v) for k, v in s["by_type"].items())))
        if s["by_category"]:
            print("  By category: {}".format(", ".join("{}: {}".format(k, v) for k, v in s["by_category"].items())))

        # FTS5 integrity check
        try:
            store.conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('integrity-check')")
            print("  FTS5 integrity: OK")
        except Exception as e:
            print("  FTS5 integrity: FAILED — {}".format(e))


if __name__ == "__main__":
    main()
