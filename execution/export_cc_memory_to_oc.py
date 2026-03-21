#!/usr/bin/env python3
"""
export_cc_memory_to_oc.py — Export Claude Code's full knowledge to OC workspace.

Purpose: Keep OpenClaw fully in sync with everything CC knows and has built.
Covers: memory.db (480+ entries), directives (SOPs), bots/agents, creator brains,
        execution scripts, skills, SabboOS agents, session snapshots.

Triggered:
  - Every ~5 min by watch_openclaw_events.py daemon
  - Instantly via memory_file_change.py PostToolUse hook on any file change in
    bots/, directives/, SabboOS/, execution/, .claude/

Usage:
    python3 execution/export_cc_memory_to_oc.py           # full export
    python3 execution/export_cc_memory_to_oc.py --quick   # memory only (fast)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent
DB_PATH        = Path("/Users/Shared/antigravity/memory/ceo/memory.db")
SNAPSHOTS_DIR  = Path("/Users/Shared/antigravity/memory/session-snapshots")
OC_WORKSPACE   = Path("/Users/SabboOpenClawAI/.openclaw/workspace/main")
OUTPUT_FILE    = OC_WORKSPACE / "CC_KNOWLEDGE.md"

MAX_CONTENT    = 400   # chars per memory entry
MAX_DIRECTIVE  = 300   # chars per directive description
MAX_SNAPSHOT   = 500   # chars per snapshot summary
MAX_SNAPSHOTS  = 8     # most recent session snapshots to include


# ── Memory export ─────────────────────────────────────────────────────────────

CATEGORY_ORDER = ["person", "decision", "learning", "asset", "reference",
                  "preference", "error", "correction"]

def _export_memory() -> tuple[int, list[str]]:
    lines = ["## Memory — Everything CC Knows", ""]
    if not DB_PATH.exists():
        return 0, lines + ["*memory.db not found*", ""]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, type, category, title, content, tags FROM memories ORDER BY type, category, created_at DESC"
    ).fetchall()
    conn.close()

    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r["type"], []).append(dict(r))

    total = 0
    for t in CATEGORY_ORDER:
        entries = grouped.get(t, [])
        if not entries:
            continue
        lines.append(f"### {t.title()}s ({len(entries)})")
        lines.append("")
        for e in entries:
            content = (e.get("content") or "").strip()
            if len(content) > MAX_CONTENT:
                content = content[:MAX_CONTENT] + "…"
            tags = e.get("tags", "")
            cat  = e.get("category", "")
            lines.append(f"**{e['title']}**" + (f" · *{cat}*" if cat else "") + (f" · `{tags}`" if tags else ""))
            if content:
                lines.append(content)
            lines.append("")
        total += len(entries)

    return total, lines


# ── Directives (SOPs) ─────────────────────────────────────────────────────────

def _export_directives() -> tuple[int, list[str]]:
    lines = ["## Directives (SOPs)", ""]
    directives_dir = PROJECT_ROOT / "directives"
    if not directives_dir.exists():
        return 0, lines + ["*directives/ not found*", ""]

    count = 0
    for f in sorted(directives_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        # First non-empty, non-header line as summary
        summary = ""
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                summary = line[:MAX_DIRECTIVE]
                break
        lines.append(f"**{f.stem}** — {summary}")
        count += 1

    lines.append("")
    return count, lines


# ── Bots & Agents ─────────────────────────────────────────────────────────────

def _export_bots() -> tuple[int, list[str]]:
    lines = ["## Bots & Agents (bots/)", ""]
    bots_dir = PROJECT_ROOT / "bots"
    if not bots_dir.exists():
        return 0, lines + ["*bots/ not found*", ""]

    count = 0
    for bot_dir in sorted(bots_dir.iterdir()):
        if not bot_dir.is_dir() or bot_dir.name.startswith("_"):
            continue
        identity = bot_dir / "identity.md"
        skills   = bot_dir / "skills.md"
        tools    = bot_dir / "tools.md"

        lines.append(f"### {bot_dir.name}")
        if identity.exists():
            text = identity.read_text(encoding="utf-8", errors="ignore")
            # First meaningful paragraph
            para = ""
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---") and not line.startswith(">"):
                    para = line[:300]
                    break
            if para:
                lines.append(para)

        # List skills if present
        if skills.exists():
            skill_lines = [l.strip() for l in skills.read_text(errors="ignore").splitlines()
                          if l.strip().startswith("-") or l.strip().startswith("*")][:6]
            if skill_lines:
                lines.append("Skills: " + " | ".join(s.lstrip("-* ") for s in skill_lines))

        lines.append("")
        count += 1

    return count, lines


# ── SabboOS Agents ────────────────────────────────────────────────────────────

def _export_sabbo_os_agents() -> tuple[int, list[str]]:
    lines = ["## SabboOS Agents (SabboOS/Agents/)", ""]
    agents_dir = PROJECT_ROOT / "SabboOS" / "Agents"
    if not agents_dir.exists():
        return 0, lines + ["*SabboOS/Agents/ not found*", ""]

    count = 0
    for f in sorted(agents_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        summary = ""
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                summary = line[:250]
                break
        lines.append(f"**{f.stem}** — {summary}")
        count += 1

    lines.append("")
    return count, lines


# ── Creator Brains ────────────────────────────────────────────────────────────

def _export_creators() -> tuple[int, list[str]]:
    lines = ["## Creator Strategy Brains (bots/creators/)", ""]
    creators_dir = PROJECT_ROOT / "bots" / "creators"
    if not creators_dir.exists():
        return 0, lines + ["*bots/creators/ not found*", ""]

    count = 0
    for f in sorted(creators_dir.glob("*-brain.md")):
        creator = f.stem.replace("-brain", "").replace("-", " ").title()
        text = f.read_text(encoding="utf-8", errors="ignore")

        # Pull first 300 chars of actual content (skip frontmatter/headers)
        content_lines = []
        in_frontmatter = False
        for line in text.splitlines():
            s = line.strip()
            if s == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if s.startswith("#") or not s:
                continue
            content_lines.append(s)
            if len(" ".join(content_lines)) > 250:
                break

        summary = " ".join(content_lines)[:250]
        lines.append(f"**{creator}** — {summary}")
        count += 1

    lines.append("")
    return count, lines


# ── Skills ────────────────────────────────────────────────────────────────────

def _export_skills() -> tuple[int, list[str]]:
    lines = ["## Claude Code Skills (/.claude/skills/)", ""]
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    if not skills_dir.exists():
        return 0, lines + ["*skills/ not found*", ""]

    import re
    count = 0
    for f in sorted(skills_dir.glob("*.md")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        name  = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        desc  = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        trig  = re.search(r"^trigger:\s*(.+)$", text, re.MULTILINE)
        name  = name.group(1).strip() if name else f.stem
        desc  = desc.group(1).strip() if desc else ""
        trig  = trig.group(1).strip() if trig else ""
        lines.append(f"`/{name}` — {desc}" + (f" *(trigger: {trig})*" if trig else ""))
        count += 1

    lines.append("")
    return count, lines


# ── Session Snapshots ─────────────────────────────────────────────────────────

def _export_snapshots() -> tuple[int, list[str]]:
    lines = ["## Session Snapshots (recent builds)", ""]
    if not SNAPSHOTS_DIR.exists():
        return 0, lines + ["*snapshots/ not found*", ""]

    snapshots = sorted(SNAPSHOTS_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:MAX_SNAPSHOTS]
    count = 0
    for f in snapshots:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # First 500 chars of content
        summary_lines = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("---"):
                summary_lines.append(s)
            if len(" ".join(summary_lines)) > MAX_SNAPSHOT:
                break
        summary = " ".join(summary_lines)[:MAX_SNAPSHOT]
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"**{f.name}** ({mtime})")
        lines.append(summary)
        lines.append("")
        count += 1

    return count, lines


# ── Execution Scripts ─────────────────────────────────────────────────────────

def _export_scripts() -> tuple[int, list[str]]:
    lines = ["## Execution Scripts (execution/*.py)", ""]
    execution_dir = PROJECT_ROOT / "execution"
    if not execution_dir.exists():
        return 0, lines + ["*execution/ not found*", ""]

    import re
    count = 0
    for f in sorted(execution_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")[:1500]
        # Extract from module docstring only
        m = re.search(r'"""(.*?)"""', text, re.DOTALL)
        purpose = ""
        if m:
            doc = m.group(1)
            pm = re.search(r'Purpose:\s*(.+)', doc)
            if pm:
                purpose = pm.group(1).strip()
            else:
                for line in doc.splitlines():
                    line = line.strip()
                    if line:
                        purpose = line[:120]
                        break
        if purpose:
            lines.append(f"`{f.name}` — {purpose}")
            count += 1

    lines.append("")
    return count, lines


# ── Main export ───────────────────────────────────────────────────────────────

def export(quick: bool = False) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = []

    # Always export memory
    mem_count, mem_lines = _export_memory()

    if not quick:
        dir_count,  dir_lines  = _export_directives()
        bot_count,  bot_lines  = _export_bots()
        os_count,   os_lines   = _export_sabbo_os_agents()
        cre_count,  cre_lines  = _export_creators()
        ski_count,  ski_lines  = _export_skills()
        scr_count,  scr_lines  = _export_scripts()
        snap_count, snap_lines = _export_snapshots()
    else:
        dir_count = bot_count = os_count = cre_count = ski_count = scr_count = snap_count = 0

    total = mem_count + dir_count + bot_count + os_count + cre_count + ski_count + scr_count + snap_count

    header = [
        f"# CC Knowledge Base",
        f"<!-- auto-generated by export_cc_memory_to_oc.py — {ts} -->",
        f"",
        f"Complete knowledge export from Claude Code. {total} items across memory, directives,",
        f"agents, creator brains, scripts, and skills. Auto-updated every 5 min + on every file change.",
        f"",
        f"**Contents:**",
        f"- Memory: {mem_count} entries (people, decisions, learnings, assets, references, preferences)",
    ]
    if not quick:
        header += [
            f"- Directives: {dir_count} SOPs",
            f"- Bots & Agents: {bot_count} bots + {os_count} SabboOS agents",
            f"- Creator Brains: {cre_count} strategy files",
            f"- Skills: {ski_count} slash commands",
            f"- Scripts: {scr_count} execution scripts",
            f"- Snapshots: {snap_count} recent session summaries",
        ]
    header += ["", "---", ""]

    body = mem_lines[:]
    if not quick:
        body += ["---", ""] + dir_lines
        body += ["---", ""] + bot_lines
        body += ["---", ""] + os_lines
        body += ["---", ""] + cre_lines
        body += ["---", ""] + ski_lines
        body += ["---", ""] + scr_lines
        body += ["---", ""] + snap_lines

    content = "\n".join(header + body)
    OC_WORKSPACE.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    OUTPUT_FILE.chmod(0o664)

    return {"total": total, "memory": mem_count, "directives": dir_count,
            "bots": bot_count, "agents": os_count, "creators": cre_count,
            "skills": ski_count, "scripts": scr_count, "snapshots": snap_count}


def main() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    quick = "--quick" in sys.argv
    stats = export(quick=quick)
    mode  = "quick (memory only)" if quick else "full"
    print(f"✓ CC Knowledge export [{mode}]: {stats['total']} items → {OUTPUT_FILE}")
    if not quick:
        print(f"  memory={stats['memory']} directives={stats['directives']} "
              f"bots={stats['bots']} agents={stats['agents']} "
              f"creators={stats['creators']} skills={stats['skills']} "
              f"scripts={stats['scripts']} snapshots={stats['snapshots']}")


if __name__ == "__main__":
    main()
