#!/usr/bin/env python3
"""
Script: refresh_nova_knowledge.py
Purpose: Autonomous pipeline to scrape Sabbo's YouTube channel, synthesize a
         comprehensive brain doc, ingest into Nova's knowledge base, and restart
         the bot. Designed to run unattended via cron/launchd.

Flow:
  1. Scrape all YouTube videos from @alldayfba (transcripts)
  2. Check if we got meaningful new data (vs previous run)
  3. If yes → run build_creator_brain.py (Sonnet+Opus synthesis)
  4. Parse brain into Nova FAQ entries
  5. Restart Nova via launchctl

Usage:
  python execution/refresh_nova_knowledge.py
  python execution/refresh_nova_knowledge.py --skip-synthesis  # scrape only, no API calls
  python execution/refresh_nova_knowledge.py --force            # run synthesis even if no new data
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = "/Users/sabbojb/.gemini/antigravity/playground/nomad-nebula/.venv/bin/python"
RAW_JSON = PROJECT_ROOT / ".tmp" / "creators" / "sabbo-alldayfba-raw.json"
BRAIN_FILE = PROJECT_ROOT / "bots" / "creators" / "sabbo-alldayfba-brain.md"
LOG_FILE = PROJECT_ROOT / ".tmp" / "discord" / "knowledge-refresh.log"

LAUNCHD_LABEL = "com.sabbo.nova-discord-bot"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_previous_transcript_count():
    """Check how many transcripts we had from the last scrape."""
    if not RAW_JSON.exists():
        return 0
    try:
        with open(RAW_JSON) as f:
            data = json.load(f)
        yt = data.get("youtube")
        if not yt:
            return 0
        videos = yt.get("videos", [])
        return sum(1 for v in videos if v.get("transcript"))
    except Exception:
        return 0


def scrape_youtube():
    """Run scrape_creator_intel.py for YouTube. Returns (success_count, total_count)."""
    log("Starting YouTube scrape for @alldayfba...")
    cmd = [
        VENV_PYTHON,
        str(PROJECT_ROOT / "execution" / "scrape_creator_intel.py"),
        "--name", "sabbo-alldayfba",
        "--youtube", "https://youtube.com/@alldayfba",
        "--max-videos", "0",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                cwd=str(PROJECT_ROOT))
        if result.stderr:
            # Parse success count from output
            for line in result.stderr.split("\n"):
                if "YouTube done:" in line:
                    log(line.strip())
                    # Extract "X transcripts pulled"
                    match = re.search(r"(\d+) transcripts pulled", line)
                    if match:
                        success = int(match.group(1))
                        total_match = re.search(r"(\d+) total", line)
                        total = int(total_match.group(1)) if total_match else 0
                        return success, total

        if result.returncode != 0:
            log(f"Scrape failed (exit {result.returncode}): {result.stderr[-300:]}")
            return 0, 0

    except subprocess.TimeoutExpired:
        log("Scrape timed out after 600s")
        return 0, 0
    except Exception as e:
        log(f"Scrape error: {e}")
        return 0, 0

    return 0, 0


def run_brain_synthesis():
    """Run build_creator_brain.py to synthesize the brain doc. Costs ~$1-2 in API calls."""
    log("Running brain synthesis (Sonnet extraction + Opus synthesis)...")
    cmd = [
        VENV_PYTHON,
        str(PROJECT_ROOT / "execution" / "build_creator_brain.py"),
        "--name", "sabbo-alldayfba",
        "--focus", "Amazon FBA sourcing methods, OA/RA/wholesale strategies, ungating techniques, "
                   "Keepa reading, product research, student coaching framework, scaling roadmap, "
                   "profitability math, tool recommendations, common mistakes, brand watchlist, "
                   "multi-pack arbitrage, storefront stalking, 3-stack protocol, growth arbitrage, "
                   "prep centers, repricing, seasonal strategy, business credit funding",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                cwd=str(PROJECT_ROOT))
        if result.returncode == 0:
            log("Brain synthesis complete.")
            return True
        else:
            log(f"Brain synthesis failed (exit {result.returncode}): {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        log("Brain synthesis timed out after 600s")
        return False
    except Exception as e:
        log(f"Brain synthesis error: {e}")
        return False


def ingest_brain_into_nova():
    """Parse the brain file and update Nova's knowledge base with FAQ entries."""
    log("Ingesting brain into Nova knowledge base...")

    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from execution.discord_bot.database import BotDatabase
        db = BotDatabase()

        # Read the brain file
        if not BRAIN_FILE.exists():
            log(f"Brain file not found: {BRAIN_FILE}")
            return False

        brain_content = BRAIN_FILE.read_text(encoding="utf-8")

        # Extract sections with ## headers as potential FAQ topics
        sections = re.split(r'\n## ', brain_content)
        new_entries = 0

        for section in sections[1:]:  # skip header
            lines = section.strip().split("\n")
            if not lines:
                continue

            title = lines[0].strip()
            content = "\n".join(lines[1:]).strip()

            if len(content) < 50:
                continue

            # Create a question from the section title
            question = title
            if not question.endswith("?"):
                question = f"What is {title}?" if not any(
                    title.lower().startswith(w) for w in ["how", "why", "what", "when", "the "]
                ) else title

            # Truncate answer to 2000 chars for Discord
            answer = content[:2000]

            # Check if similar entry already exists
            existing = db.get_approved_knowledge(
                ",".join(re.findall(r"[a-z0-9]+", title.lower())[:5]),
                limit=1
            )
            if existing and any(e["question"].lower() == question.lower() for e in existing):
                continue

            db.add_knowledge_entry(
                question=question,
                answer=answer,
                source="auto-brain",
                approved=True,
                approved_by="refresh-pipeline",
            )
            new_entries += 1

        stats = db.get_stats()
        log(f"Ingested {new_entries} new entries. Total FAQ: {stats['faq_entries']}")
        return True

    except Exception as e:
        log(f"Ingestion error: {e}")
        return False


def restart_nova():
    """Restart Nova via launchctl."""
    log("Restarting Nova...")
    try:
        subprocess.run(["launchctl", "unload",
                        os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist")],
                       capture_output=True, timeout=10)
        import time
        time.sleep(2)
        subprocess.run(["launchctl", "load",
                        os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist")],
                       capture_output=True, timeout=10)
        time.sleep(5)

        # Verify Nova is running
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        if LAUNCHD_LABEL in result.stdout:
            log("Nova restarted successfully.")
            return True
        else:
            log("WARNING: Nova may not have restarted. Check manually.")
            return False
    except Exception as e:
        log(f"Restart error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Refresh Nova's knowledge base from YouTube")
    parser.add_argument("--skip-synthesis", action="store_true",
                        help="Scrape only, don't run brain synthesis (no API cost)")
    parser.add_argument("--force", action="store_true",
                        help="Run synthesis even if no new transcripts found")
    args = parser.parse_args()

    log("=" * 60)
    log("NOVA KNOWLEDGE REFRESH — starting autonomous pipeline")
    log("=" * 60)

    prev_count = get_previous_transcript_count()
    log(f"Previous transcript count: {prev_count}")

    # Step 1: Scrape YouTube
    success, total = scrape_youtube()
    log(f"Scrape result: {success}/{total} transcripts")

    if success == 0 and not args.force:
        log("No transcripts retrieved (rate limit likely still active). Will retry next run.")
        log("Pipeline aborted — no changes made.")
        return

    if success <= prev_count and not args.force:
        log(f"No new transcripts ({success} <= {prev_count}). Skipping synthesis.")
        log("Pipeline complete — no changes needed.")
        return

    log(f"New transcripts found: {success} (was {prev_count})")

    # Step 2: Brain synthesis (costs ~$1-2)
    if not args.skip_synthesis:
        synthesis_ok = run_brain_synthesis()
        if not synthesis_ok:
            log("Brain synthesis failed. Keeping existing brain file.")
            # Still try to ingest what we have
    else:
        log("Skipping synthesis (--skip-synthesis flag)")

    # Step 3: Ingest into Nova
    ingest_brain_into_nova()

    # Step 4: Restart Nova
    restart_nova()

    log("=" * 60)
    log("NOVA KNOWLEDGE REFRESH — pipeline complete")
    log("=" * 60)


if __name__ == "__main__":
    main()
