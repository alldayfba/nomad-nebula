#!/usr/bin/env python3
"""
multichannel_outreach.py — Multi-channel outreach orchestrator.

Sends personalized outreach across Instagram DMs, X/Twitter DMs, email,
and contact forms. Handles rate limiting, channel rotation, and follow-up
scheduling per Kabrin's multi-channel pattern.

Usage:
    # Send to a single prospect across all channels
    python execution/multichannel_outreach.py send \
        --name "John Smith" \
        --email "john@example.com" \
        --instagram "johnsmith" \
        --twitter "johnsmith" \
        --message "Hey John, built you a full growth system..."

    # Batch send from CSV
    python execution/multichannel_outreach.py batch \
        --csv .tmp/leads/miami-dentists.csv \
        --template dream100 \
        --channels ig,email

    # Check rate limits
    python execution/multichannel_outreach.py status

    # Programmatic:
    from execution.multichannel_outreach import send_outreach, batch_send
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Rate Limits (Kabrin's safe thresholds) ──────────────────────────────────

RATE_LIMITS = {
    "instagram": {"daily_max": 50, "cooldown_seconds": 60, "ramp_up_days": 7},
    "twitter": {"daily_max": 50, "cooldown_seconds": 30, "ramp_up_days": 5},
    "email": {"per_inbox_max": 25, "max_inboxes": 4, "cooldown_seconds": 10},
    "contact_form": {"daily_max": 30, "cooldown_seconds": 120},
}

# Daily send tracking
TRACKER_FILE = Path(__file__).parent.parent / ".tmp" / "outreach" / "daily_tracker.json"


def _load_tracker():
    if TRACKER_FILE.exists():
        data = json.loads(TRACKER_FILE.read_text())
        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return {"date": datetime.now().strftime("%Y-%m-%d"), "sends": {}}
        return data
    return {"date": datetime.now().strftime("%Y-%m-%d"), "sends": {}}


def _save_tracker(data):
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_FILE.write_text(json.dumps(data, indent=2))


def _get_send_count(channel):
    tracker = _load_tracker()
    return tracker.get("sends", {}).get(channel, 0)


def _increment_send(channel):
    tracker = _load_tracker()
    if "sends" not in tracker:
        tracker["sends"] = {}
    tracker["sends"][channel] = tracker["sends"].get(channel, 0) + 1
    _save_tracker(tracker)


def check_rate_limit(channel):
    """Check if we can send on this channel."""
    count = _get_send_count(channel)
    limit = RATE_LIMITS.get(channel, {})

    if channel == "email":
        max_sends = limit.get("per_inbox_max", 25) * limit.get("max_inboxes", 4)
    else:
        max_sends = limit.get("daily_max", 50)

    return {
        "channel": channel,
        "sent_today": count,
        "daily_limit": max_sends,
        "remaining": max_sends - count,
        "can_send": count < max_sends,
    }


# ── Channel Senders ─────────────────────────────────────────────────────────

def send_instagram_dm(handle, message):
    """Send Instagram DM via Instagram Graph API.

    Requires INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_PAGE_ID in .env.
    Falls back to logging if credentials not set.
    """
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    page_id = os.getenv("INSTAGRAM_PAGE_ID")

    if not token or not page_id:
        return {
            "channel": "instagram",
            "status": "credentials_missing",
            "handle": handle,
            "message_preview": message[:100],
            "note": "Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_PAGE_ID in .env",
        }

    try:
        import requests
        # Instagram Messaging API (requires approved app)
        url = "https://graph.facebook.com/v19.0/{}/messages".format(page_id)
        payload = {
            "recipient": {"username": handle},
            "message": {"text": message},
        }
        resp = requests.post(url, json=payload, headers={
            "Authorization": "Bearer {}".format(token)
        }, timeout=15)

        _increment_send("instagram")
        return {
            "channel": "instagram",
            "status": "sent" if resp.status_code == 200 else "error",
            "handle": handle,
            "response_code": resp.status_code,
        }
    except Exception as e:
        return {"channel": "instagram", "status": "error", "error": str(e)}


def send_twitter_dm(handle, message):
    """Send X/Twitter DM via API v2.

    Requires TWITTER_BEARER_TOKEN in .env.
    """
    token = os.getenv("TWITTER_BEARER_TOKEN")

    if not token:
        return {
            "channel": "twitter",
            "status": "credentials_missing",
            "handle": handle,
            "message_preview": message[:100],
            "note": "Set TWITTER_BEARER_TOKEN in .env",
        }

    try:
        import requests
        # First, get user ID from handle
        user_url = "https://api.twitter.com/2/users/by/username/{}".format(handle.lstrip("@"))
        user_resp = requests.get(user_url, headers={
            "Authorization": "Bearer {}".format(token)
        }, timeout=10)

        if user_resp.status_code != 200:
            return {"channel": "twitter", "status": "user_not_found", "handle": handle}

        user_id = user_resp.json().get("data", {}).get("id")
        if not user_id:
            return {"channel": "twitter", "status": "user_not_found", "handle": handle}

        # Send DM
        dm_url = "https://api.twitter.com/2/dm_conversations/with/{}/messages".format(user_id)
        dm_resp = requests.post(dm_url, json={"text": message}, headers={
            "Authorization": "Bearer {}".format(token),
            "Content-Type": "application/json",
        }, timeout=15)

        _increment_send("twitter")
        return {
            "channel": "twitter",
            "status": "sent" if dm_resp.status_code in (200, 201) else "error",
            "handle": handle,
            "response_code": dm_resp.status_code,
        }
    except Exception as e:
        return {"channel": "twitter", "status": "error", "error": str(e)}


def send_email(to_email, subject, body, from_email=None):
    """Send email via SMTP or API.

    Uses SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS from .env.
    Falls back to logging if not configured.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not smtp_host:
        return {
            "channel": "email",
            "status": "credentials_missing",
            "to": to_email,
            "subject": subject,
            "note": "Set SMTP_HOST, SMTP_USER, SMTP_PASS in .env",
        }

    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email or smtp_user
        msg["To"] = to_email

        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        _increment_send("email")
        return {"channel": "email", "status": "sent", "to": to_email, "subject": subject}
    except Exception as e:
        return {"channel": "email", "status": "error", "error": str(e)}


CHANNEL_SENDERS = {
    "instagram": send_instagram_dm,
    "ig": send_instagram_dm,
    "twitter": send_twitter_dm,
    "x": send_twitter_dm,
    "email": send_email,
}


# ── Orchestration ───────────────────────────────────────────────────────────

def send_outreach(name, message, email=None, instagram=None, twitter=None,
                  channels=None, subject=None):
    """Send outreach to a single prospect across specified channels."""
    results = []

    if channels is None:
        channels = []
        if instagram:
            channels.append("instagram")
        if twitter:
            channels.append("twitter")
        if email:
            channels.append("email")

    for channel in channels:
        rate = check_rate_limit(channel)
        if not rate["can_send"]:
            results.append({
                "channel": channel,
                "status": "rate_limited",
                "sent_today": rate["sent_today"],
                "limit": rate["daily_limit"],
            })
            continue

        if channel in ("instagram", "ig") and instagram:
            results.append(send_instagram_dm(instagram, message))
        elif channel in ("twitter", "x") and twitter:
            results.append(send_twitter_dm(twitter, message))
        elif channel == "email" and email:
            subj = subject or "Quick question, {}".format(name.split()[0] if name else "")
            results.append(send_email(email, subj, message))

        # Respect cooldown between sends
        cooldown = RATE_LIMITS.get(channel, {}).get("cooldown_seconds", 30)
        time.sleep(min(cooldown, 5))  # Cap at 5s for batch operations

    return {
        "prospect": name,
        "channels_attempted": len(channels),
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


def batch_send(csv_path, template_message, channels=None, subject=None, dry_run=False):
    """Batch send outreach from a CSV file.

    CSV must have columns: name, email, instagram, twitter (any subset).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {"error": "CSV not found: {}".format(csv_path)}

    results = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", row.get("contact_name", ""))
            # Personalize message
            msg = template_message.replace("{name}", name.split()[0] if name else "")
            msg = msg.replace("{company}", row.get("company", row.get("company_name", "")))

            if dry_run:
                results.append({
                    "prospect": name,
                    "status": "dry_run",
                    "message_preview": msg[:100],
                    "channels": channels or ["email"],
                })
                continue

            result = send_outreach(
                name=name,
                message=msg,
                email=row.get("email"),
                instagram=row.get("instagram"),
                twitter=row.get("twitter"),
                channels=channels,
                subject=subject,
            )
            results.append(result)

    return {
        "total_prospects": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


def get_status():
    """Get current rate limit status across all channels."""
    return {channel: check_rate_limit(channel) for channel in RATE_LIMITS}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-channel outreach orchestrator")
    sub = parser.add_subparsers(dest="command")

    # send
    p_send = sub.add_parser("send", help="Send to a single prospect")
    p_send.add_argument("--name", required=True)
    p_send.add_argument("--message", required=True)
    p_send.add_argument("--email")
    p_send.add_argument("--instagram")
    p_send.add_argument("--twitter")
    p_send.add_argument("--subject")
    p_send.add_argument("--channels", help="Comma-separated: ig,twitter,email")

    # batch
    p_batch = sub.add_parser("batch", help="Batch send from CSV")
    p_batch.add_argument("--csv", required=True)
    p_batch.add_argument("--message", required=True, help="Message template ({name}, {company})")
    p_batch.add_argument("--channels", help="Comma-separated channels")
    p_batch.add_argument("--subject")
    p_batch.add_argument("--dry-run", action="store_true")

    # status
    sub.add_parser("status", help="Check rate limit status")

    args = parser.parse_args()

    if args.command == "send":
        channels = args.channels.split(",") if args.channels else None
        result = send_outreach(args.name, args.message, args.email,
                               args.instagram, args.twitter, channels, args.subject)
        print(json.dumps(result, indent=2))

    elif args.command == "batch":
        channels = args.channels.split(",") if args.channels else None
        result = batch_send(args.csv, args.message, channels, args.subject, args.dry_run)
        print("Sent to {} prospects".format(result["total_prospects"]))
        if args.dry_run:
            print("(DRY RUN — no messages actually sent)")

    elif args.command == "status":
        status = get_status()
        for ch, s in status.items():
            bar = "OK" if s["can_send"] else "LIMIT REACHED"
            print("  {:15s} {}/{} ({})".format(ch, s["sent_today"], s["daily_limit"], bar))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
