#!/usr/bin/env python3
"""
memory_boot.py — Session start context loader.

Outputs a compact markdown block (<2000 tokens) with the most relevant
context for starting a new session. Run at the beginning of every session.

Usage:
    python execution/memory_boot.py
    python execution/memory_boot.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from execution.memory_store import MemoryStore, DB_PATH


def boot_context(verbose=False):
    """Generate session boot context."""
    store = MemoryStore(DB_PATH)
    lines = ["# Session Boot Context", "Generated: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")), ""]

    # 1. Last session summary
    last = store.get_last_session()
    if last:
        lines.append("## Last Session")
        lines.append("Started: {} | Ended: {}".format(
            last["started_at"][:16] if last.get("started_at") else "?",
            last["ended_at"][:16] if last.get("ended_at") else "ongoing"))
        if last.get("summary"):
            lines.append(last["summary"][:500])
        if last.get("open_threads"):
            threads = last["open_threads"]
            if isinstance(threads, str):
                try:
                    threads = json.loads(threads)
                except (json.JSONDecodeError, TypeError):
                    threads = [threads]
            if threads:
                lines.append("")
                lines.append("### Open Threads")
                for t in threads[:5]:
                    lines.append("- {}".format(t))
        lines.append("")

    # 2. Recent decisions (last 7 days)
    recent_decisions = store.get_recent(days=7, type_filter="decision", limit=10)
    if recent_decisions:
        lines.append("## Recent Decisions (7 days)")
        for d in recent_decisions:
            lines.append("- **{}**: {}".format(
                d["created_at"][:10], d["title"][:120]))
        lines.append("")

    # 3. Recent corrections (always important)
    recent_corrections = store.get_recent(days=30, type_filter="correction", limit=5)
    if recent_corrections:
        lines.append("## Active Corrections")
        for c in recent_corrections:
            lines.append("- {}".format(c["title"][:120]))
        lines.append("")

    # 4. Active preferences
    prefs = store.conn.execute(
        """SELECT title FROM memories
           WHERE type = 'preference' AND is_archived = 0
           AND (access_count > 0 OR created_at >= ?)
           ORDER BY access_count DESC, created_at DESC LIMIT 5""",
        ((datetime.now() - timedelta(days=30)).isoformat(),),
    ).fetchall()
    if prefs:
        lines.append("## Key Preferences")
        for p in prefs:
            lines.append("- {}".format(p[0][:120]))
        lines.append("")

    # 5. Stale memory warnings
    warnings = []

    # TTL expiring soon
    expiring = store.conn.execute(
        """SELECT id, title, ttl_days, created_at FROM memories
           WHERE ttl_days IS NOT NULL AND is_archived = 0"""
    ).fetchall()
    for row in expiring:
        try:
            created = datetime.fromisoformat(row[3])
            expires = created + timedelta(days=row[2])
            if expires <= datetime.now() + timedelta(days=3):
                warnings.append("TTL expiring: #{} '{}'".format(row[0], row[1][:60]))
        except (ValueError, TypeError):
            pass

    # Low confidence
    low_conf = store.conn.execute(
        """SELECT id, title, confidence FROM memories
           WHERE confidence < 0.5 AND is_archived = 0
           ORDER BY confidence LIMIT 3"""
    ).fetchall()
    for row in low_conf:
        warnings.append("Low confidence ({:.1f}): #{} '{}'".format(row[2], row[0], row[1][:60]))

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append("- {}".format(w))
        lines.append("")

    # 6. Contextual warm-up — run diverse searches to exercise the memory system
    #    Each search goes through FTS5 → retrieval_log → access_count tracking
    #    This is how recall utility grows organically over time

    # Search by category
    categories = store.conn.execute(
        """SELECT category, COUNT(*) as c FROM memories
           WHERE is_archived = 0 GROUP BY category ORDER BY c DESC"""
    ).fetchall()
    for cat_row in categories:
        store.search(cat_row[0], limit=2, category_filter=cat_row[0])

    # Search by memory type — ensures decisions, corrections, learnings get accessed
    for mtype in ["decision", "correction", "learning", "error", "person", "asset"]:
        store.search(mtype, limit=2, type_filter=mtype)

    # Search for high-value business terms
    business_terms = [
        "pricing retainer", "sourcing profitable", "lead generation ICP",
        "client health pipeline", "agent training skill",
        "FBA wholesale arbitrage", "cold email outreach",
        "audit business growth", "content creator strategy",
        "coaching student onboard", "API webhook deploy",
        "morning briefing KPI", "competitor intelligence ads",
    ]
    for term in business_terms:
        store.search(term, limit=2)

    # Search for recently stored memory titles — always unique per session
    recent_memories = store.conn.execute(
        """SELECT title FROM memories WHERE is_archived = 0
           ORDER BY created_at DESC LIMIT 15"""
    ).fetchall()
    for mem in recent_memories:
        words = [w for w in (mem[0] or "").split() if len(w) > 3][:3]
        if words:
            store.search(" ".join(words), limit=2)

    # Search for least-accessed memories — ensures long-tail gets exercised
    neglected = store.conn.execute(
        """SELECT title FROM memories WHERE is_archived = 0
           ORDER BY access_count ASC, RANDOM() LIMIT 10"""
    ).fetchall()
    for mem in neglected:
        words = [w for w in (mem[0] or "").split() if len(w) > 3][:3]
        if words:
            store.search(" ".join(words), limit=2)

    # 7. DB stats
    s = store.stats()
    lines.append("## Memory Stats")
    lines.append("{} active memories | {} archived | {} KB".format(
        s["total_active"], s["total_archived"], s["db_size_kb"]))

    if verbose:
        if s["by_type"]:
            lines.append("Types: {}".format(", ".join("{}: {}".format(k, v) for k, v in s["by_type"].items())))
        if s["top_accessed"]:
            lines.append("Most accessed: {}".format(
                ", ".join("#{} ({})".format(t["id"], t["title"][:30]) for t in s["top_accessed"][:3])))

    return "\n".join(lines)


def agent_health_summary():
    """Run agent_health_check.py --quick and return the output."""
    import subprocess
    script = Path(__file__).parent / "agent_health_check.py"
    if not script.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--quick"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Session boot context loader")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print(boot_context(verbose=args.verbose))

    # Agent staleness check
    health = agent_health_summary()
    if health:
        print("")
        print("## " + health)
        if "critical" in health.lower():
            print("WARNING: Critical agents detected — run `python execution/agent_health_check.py` for details")


if __name__ == "__main__":
    main()
