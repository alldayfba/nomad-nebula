#!/usr/bin/env python3
"""
send_morning_briefing.py
Compiles the daily 8am ads briefing from competitor intel and sends it via Telegram or email.

Usage:
  python execution/send_morning_briefing.py
  python execution/send_morning_briefing.py --dry-run   (print only, don't send)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

AGENCY_INTEL_FILE = ".tmp/ads/agency_competitors.json"
COACHING_INTEL_FILE = ".tmp/ads/coaching_competitors.json"
MEMORY_FILE = "bots/ads-copy/memory.md"
HEARTBEAT_FILE = "bots/ads-copy/heartbeat.md"


def parse_args():
    parser = argparse.ArgumentParser(description="Compile and send morning ads briefing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print briefing to stdout instead of sending")
    return parser.parse_args()


def load_intel(filepath: str) -> dict | None:
    """Load competitor intel JSON. Returns None if file doesn't exist."""
    path = Path(filepath)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def format_competitor_section(intel: dict | None, label: str) -> str:
    """Format one business's competitor section for the briefing."""
    if not intel:
        return f"⚠ {label}: No data file found. Run scrape_competitor_ads.py first.\n"

    competitors = intel.get("competitors", [])
    if not competitors:
        return f"⚠ {label}: Competitor list is empty. Add page names to scrape_competitor_ads.py.\n"

    lines = []
    for comp in competitors:
        name = comp.get("page_name", "Unknown")
        total = comp.get("total_ads_found", 0)
        error = comp.get("error")
        longest = comp.get("longest_running_ad")
        newest = comp.get("newest_ads", [])
        fmt = comp.get("format_breakdown", {})

        if error:
            lines.append(f"  [{name}] ⚠ Scrape error: {error}")
            continue

        lines.append(f"  [{name}]")
        lines.append(f"    Active ads: {total}")

        if longest:
            preview = longest.get("text_preview", "")[:120].replace("\n", " ")
            lines.append(f"    Longest-running: {preview}...")

        top_format = max(fmt, key=fmt.get) if fmt else "unknown"
        lines.append(f"    Top format: {top_format} ({fmt.get(top_format, 0)} ads)")

        if newest:
            lines.append(f"    Newest ads ({len(newest)}): {newest[0].get('text_preview', '')[:80]}...")

        lines.append("")

    return "\n".join(lines)


def generate_briefing(agency_intel: dict | None, coaching_intel: dict | None) -> str:
    """Build the full morning briefing string."""
    now = datetime.now()
    weekday = now.strftime("%A").upper()
    date = now.strftime("%B %d, %Y")
    timestamp = now.strftime("%H:%M")

    agency_section = format_competitor_section(agency_intel, "AGENCY")
    coaching_section = format_competitor_section(coaching_intel, "COACHING")

    # Determine top insight
    top_insight = "No new signals detected — review competitor files manually."
    if agency_intel and agency_intel.get("competitors"):
        for comp in agency_intel["competitors"]:
            if comp.get("total_ads_found", 0) > 5 and not comp.get("error"):
                top_insight = (
                    f"{comp['page_name']} has {comp['total_ads_found']} active ads. "
                    f"Check their longest-running creative for the winning angle."
                )
                break

    # Project status section
    project_section = ""
    try:
        from project_manager import briefing_feed
        pm_data = briefing_feed()
        if pm_data and pm_data.get("content"):
            project_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{pm_data['content']}
"""
    except Exception:
        pass

    # Sourcing review queue section
    sourcing_queue_section = ""
    try:
        from sourcing_review_queue import get_db as rq_db, get_status as rq_status
        rq_conn = rq_db()
        stats = rq_status(rq_conn)
        rq_conn.close()
        if stats.get("pending", 0) > 0:
            sourcing_queue_section = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SOURCING REVIEW QUEUE — {stats['pending']} products awaiting QA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Pending:  {stats['pending']}  |  Approved: {stats['approved']}  |  Sent: {stats['sent']}

  Run: python execution/sourcing_review_queue.py review
  Then: approve --all  OR  approve --ids 1,3,5
  Then: send --channel-id <DISCORD_CHANNEL_ID>
"""
    except Exception:
        pass

    briefing = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SABBO ADS BRIEF — {weekday}, {date}  |  {timestamp}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ TOP INSIGHT TODAY
{top_insight}
{sourcing_queue_section}{project_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENCY — COMPETITOR INTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{agency_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COACHING — COMPETITOR INTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{coaching_section}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
End of Brief | Generated {now.isoformat()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    return briefing


def send_telegram(message: str) -> bool:
    """Send message via Telegram bot."""
    import urllib.request
    import urllib.parse

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print("Briefing sent via Telegram.", file=sys.stderr)
                return True
            else:
                print(f"Telegram error: {result}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"ERROR sending Telegram: {e}", file=sys.stderr)
        return False


def send_email(message: str) -> bool:
    """Send message via email (requires SMTP config in .env)."""
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    to_addr = os.getenv("BRIEFING_EMAIL_TO")

    if not all([smtp_user, smtp_pass, to_addr]):
        print("ERROR: SMTP credentials or BRIEFING_EMAIL_TO not set in .env", file=sys.stderr)
        return False

    msg = MIMEText(message)
    msg["Subject"] = f"Sabbo Ads Brief — {datetime.now().strftime('%B %d, %Y')}"
    msg["From"] = smtp_user
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("Briefing sent via email.", file=sys.stderr)
        return True
    except Exception as e:
        print(f"ERROR sending email: {e}", file=sys.stderr)
        return False


def log_to_heartbeat(status: str):
    """Append completion log to heartbeat file."""
    path = Path(HEARTBEAT_FILE)
    if not path.exists():
        return
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"\n{timestamp} — Morning briefing — {status}"
    with open(path, "a") as f:
        f.write(log_line)


def main():
    args = parse_args()

    print("Loading competitor intel...", file=sys.stderr)
    agency_intel = load_intel(AGENCY_INTEL_FILE)
    coaching_intel = load_intel(COACHING_INTEL_FILE)

    if not agency_intel and not coaching_intel:
        print(
            "WARNING: No intel files found. Run scrape_competitor_ads.py first.\n"
            "Generating briefing with placeholder content.",
            file=sys.stderr,
        )

    briefing = generate_briefing(agency_intel, coaching_intel)

    if args.dry_run:
        print(briefing)
        return

    # Determine delivery method
    delivery = os.getenv("BRIEFING_DELIVERY", "telegram").lower()

    success = False
    if delivery == "telegram":
        success = send_telegram(briefing)
    elif delivery == "email":
        success = send_email(briefing)
    else:
        print(f"ERROR: Unknown BRIEFING_DELIVERY '{delivery}'. Use 'telegram' or 'email'.", file=sys.stderr)
        sys.exit(1)

    if success:
        log_to_heartbeat("sent")
        print("Morning briefing delivered.")
    else:
        log_to_heartbeat("FAILED")
        print("Morning briefing FAILED to send.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
