#!/usr/bin/env python3
"""
Script: supplier_outreach_engine.py
Purpose: Generate personalized wholesale supplier outreach emails using Claude,
         and send them via SMTP with rate limiting.
Inputs:  CLI subcommands: generate, send, status
Outputs: Draft emails (JSON/CSV), SMTP send results

CLI:
    python execution/supplier_outreach_engine.py generate --suppliers .tmp/suppliers.csv --template intro_inquiry
    python execution/supplier_outreach_engine.py generate --supplier-ids 1,2,3 --template quote_request
    python execution/supplier_outreach_engine.py send --drafts .tmp/outreach/drafts.json --dry-run
    python execution/supplier_outreach_engine.py send --drafts .tmp/outreach/drafts.json --smtp-host smtp.gmail.com --smtp-user user@gmail.com --smtp-pass "apppassword"
    python execution/supplier_outreach_engine.py status

Programmatic:
    from execution.supplier_outreach_engine import generate_supplier_email, send_batch
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import smtplib
import sqlite3
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    anthropic = None

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
TMP_DIR = BASE_DIR / ".tmp" / "outreach"

_MODEL = "claude-sonnet-4-6"
_PRICING = {
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
}

# Rate limits (per Kabrin's safe thresholds)
SMTP_RATE_LIMIT = {
    "per_inbox_max": 25,
    "cooldown_seconds": 10,
    "max_inboxes": 4,
}

TRACKER_FILE = TMP_DIR / "supplier_outreach_tracker.json"

# ── Templates ─────────────────────────────────────────────────────────────────

TEMPLATES = {
    "intro_inquiry": {
        "name": "Introduction & Inquiry",
        "prompt": (
            "Write a professional cold introduction email to this wholesale supplier. "
            "Express genuine interest in their product line for Amazon FBA reselling. "
            "Ask about wholesale pricing, minimum order quantities, and whether they "
            "accept new wholesale accounts. Keep it concise and professional — "
            "no fluff, no buzzwords."
        ),
    },
    "quote_request": {
        "name": "Quote Request",
        "prompt": (
            "Write a professional email requesting a wholesale price quote. "
            "Include specific questions about: bulk pricing tiers, shipping costs "
            "to Amazon FBA warehouses, payment terms (NET30), and MAP policy. "
            "Mention you're an established Amazon seller looking for a reliable supplier."
        ),
    },
    "sample_request": {
        "name": "Sample Request",
        "prompt": (
            "Write a professional email requesting product samples before placing "
            "a bulk order. Express willingness to pay for samples and shipping. "
            "Mention specific product categories of interest based on their catalog. "
            "Keep it brief — show you're a serious buyer, not a tire-kicker."
        ),
    },
    "wholesale_application": {
        "name": "Wholesale Account Application",
        "prompt": (
            "Write a formal wholesale account application email. Express serious "
            "buying intent as an Amazon FBA seller. Mention your business entity, "
            "ask about their authorized dealer/reseller program, and inquire about "
            "the application process. Professional and direct tone."
        ),
    },
}

FBA_SELLER_CONTEXT = """
You are writing outreach emails on behalf of an Amazon FBA seller looking to open
wholesale supplier accounts.

About the sender:
- Professional Amazon FBA seller with an established business
- Looking for reliable wholesale suppliers for profitable product sourcing
- Interested in building long-term supplier relationships, not one-off purchases
- Has proper business entity (LLC) and resale certificate
- Can order in bulk and maintain consistent reorder volume

Email style rules:
- Max 120 words in the body
- Professional but personable — you're a real business owner, not a form letter
- Reference something specific about the supplier (their products, location, categories)
- One clear CTA: request to discuss wholesale pricing or open an account
- No: "I hope this email finds you well", "synergy", "leverage", "reaching out"
- Tone: professional, direct, serious buyer energy
- Sign off with [Your Name] placeholder
"""


# ── Rate Limit Tracking ──────────────────────────────────────────────────────

def _load_tracker() -> dict:
    if TRACKER_FILE.exists():
        data = json.loads(TRACKER_FILE.read_text())
        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return {"date": datetime.now().strftime("%Y-%m-%d"), "sends": {}, "drafts": 0}
        return data
    return {"date": datetime.now().strftime("%Y-%m-%d"), "sends": {}, "drafts": 0}


def _save_tracker(data: dict):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    TRACKER_FILE.write_text(json.dumps(data, indent=2))


def _increment_send(inbox: str):
    tracker = _load_tracker()
    tracker["sends"][inbox] = tracker["sends"].get(inbox, 0) + 1
    _save_tracker(tracker)


def _get_send_count(inbox: str) -> int:
    return _load_tracker().get("sends", {}).get(inbox, 0)


def check_rate_limit(inbox: str) -> dict:
    """Check if we can send from this inbox."""
    count = _get_send_count(inbox)
    limit = SMTP_RATE_LIMIT["per_inbox_max"]
    return {
        "inbox": inbox,
        "sent_today": count,
        "daily_limit": limit,
        "remaining": max(0, limit - count),
        "can_send": count < limit,
    }


# ── Email Generation ─────────────────────────────────────────────────────────

def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000


def generate_supplier_email(
    supplier_data: dict,
    template_type: str = "intro_inquiry",
    sender_context: str = None,
    client: object = None,
) -> dict:
    """
    Generate a personalized outreach email for one supplier.
    Returns {"subject": str, "body": str, "supplier_id": int|None, "template": str}.
    """
    if anthropic is None:
        return {
            "subject": f"Wholesale Inquiry — {supplier_data.get('name', 'Your Company')}",
            "body": f"[Draft placeholder — anthropic SDK not installed]\n\nDear {supplier_data.get('name', 'Supplier')},\n\nI'm an Amazon FBA seller interested in opening a wholesale account...",
            "supplier_id": supplier_data.get("id"),
            "template": template_type,
            "error": "anthropic SDK not installed",
        }

    template = TEMPLATES.get(template_type, TEMPLATES["intro_inquiry"])
    context = sender_context or FBA_SELLER_CONTEXT

    # Build supplier info block
    sup_info = {
        k: v for k, v in supplier_data.items()
        if k in ("name", "website", "email", "phone", "address", "state",
                 "categories", "min_order", "certifications", "notes")
        and v
    }

    prompt = f"""{context}

Supplier data:
{json.dumps(sup_info, indent=2)}

{template['prompt']}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "subject": "<email subject line — reads like a real person, not marketing>",
  "body": "<email body — use \\n for line breaks, max 120 words>"
}}"""

    if client is None:
        client = anthropic.Anthropic()

    message = client.messages.create(
        model=_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON from response
        import re
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            parsed = json.loads(m.group(0))
        else:
            parsed = {"subject": "Wholesale Inquiry", "body": raw}

    return {
        "subject": parsed.get("subject", "Wholesale Inquiry"),
        "body": parsed.get("body", ""),
        "supplier_id": supplier_data.get("id"),
        "supplier_name": supplier_data.get("name"),
        "supplier_email": supplier_data.get("email"),
        "template": template_type,
    }


def generate_batch_emails(
    suppliers: list[dict],
    template_type: str = "intro_inquiry",
    sender_context: str = None,
    progress_cb: Callable = None,
) -> list[dict]:
    """
    Generate outreach emails for a batch of suppliers.
    Returns list of draft dicts.
    """
    if anthropic is None:
        print("ERROR: anthropic SDK required for email generation", file=sys.stderr)
        return []

    client = anthropic.Anthropic()
    drafts = []
    total = len(suppliers)
    total_cost = 0.0

    for i, sup in enumerate(suppliers):
        if progress_cb:
            progress_cb(i + 1, total, sup.get("name", "Unknown"))
        else:
            print(f"  [{i+1}/{total}] Generating email for: {sup.get('name', 'Unknown')}")

        try:
            draft = generate_supplier_email(
                sup, template_type=template_type,
                sender_context=sender_context, client=client,
            )
            drafts.append(draft)
        except Exception as e:
            print(f"  [WARN] Failed for {sup.get('name')}: {e}", file=sys.stderr)
            drafts.append({
                "subject": "",
                "body": "",
                "supplier_id": sup.get("id"),
                "supplier_name": sup.get("name"),
                "supplier_email": sup.get("email"),
                "template": template_type,
                "error": str(e),
            })

    print(f"\nGenerated {len([d for d in drafts if not d.get('error')])} / {total} emails.")
    return drafts


# ── SMTP Sending ─────────────────────────────────────────────────────────────

def send_email_smtp(
    to: str,
    subject: str,
    body: str,
    from_name: str,
    from_email: str,
    smtp_host: str,
    smtp_port: int = 587,
    smtp_user: str = None,
    smtp_pass: str = None,
) -> dict:
    """Send a single email via SMTP. Returns status dict."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to
    msg["Subject"] = subject

    # Plain text body
    msg.attach(MIMEText(body, "plain"))

    # Simple HTML version
    html_body = body.replace("\n", "<br>")
    msg.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user or from_email, smtp_pass)
            server.sendmail(from_email, to, msg.as_string())

        _increment_send(from_email)
        return {"to": to, "status": "sent", "error": None}
    except Exception as e:
        return {"to": to, "status": "failed", "error": str(e)}


def send_batch(
    drafts: list[dict],
    smtp_config: dict,
    dry_run: bool = False,
    progress_cb: Callable = None,
) -> list[dict]:
    """
    Send a batch of draft emails via SMTP with rate limiting.

    smtp_config: {
        "smtp_host": str,
        "smtp_port": int (default 587),
        "smtp_user": str,
        "smtp_pass": str,
        "from_name": str,
        "from_email": str,
    }
    """
    from_email = smtp_config.get("from_email", smtp_config.get("smtp_user", ""))
    rate = check_rate_limit(from_email)

    if not rate["can_send"] and not dry_run:
        print(f"Rate limit reached for {from_email}: {rate['sent_today']}/{rate['daily_limit']}", file=sys.stderr)
        return [{"to": d.get("supplier_email"), "status": "rate_limited"} for d in drafts]

    results = []
    total = len(drafts)

    for i, draft in enumerate(drafts):
        to = draft.get("supplier_email")
        if not to:
            results.append({"to": None, "status": "skipped", "error": "No email address"})
            continue

        # Re-check rate limit
        rate = check_rate_limit(from_email)
        if not rate["can_send"] and not dry_run:
            results.append({"to": to, "status": "rate_limited"})
            continue

        if progress_cb:
            progress_cb(i + 1, total, to)
        else:
            action = "DRY RUN" if dry_run else "Sending"
            print(f"  [{i+1}/{total}] {action}: {to}")

        if dry_run:
            results.append({"to": to, "status": "dry_run", "subject": draft["subject"]})
            continue

        result = send_email_smtp(
            to=to,
            subject=draft["subject"],
            body=draft["body"],
            from_name=smtp_config.get("from_name", ""),
            from_email=from_email,
            smtp_host=smtp_config["smtp_host"],
            smtp_port=smtp_config.get("smtp_port", 587),
            smtp_user=smtp_config.get("smtp_user"),
            smtp_pass=smtp_config.get("smtp_pass"),
        )
        results.append(result)

        # Cooldown between sends
        if not dry_run and i < total - 1:
            time.sleep(SMTP_RATE_LIMIT["cooldown_seconds"])

    sent = len([r for r in results if r["status"] == "sent"])
    failed = len([r for r in results if r["status"] == "failed"])
    print(f"\nBatch complete: {sent} sent, {failed} failed, {total - sent - failed} skipped/limited.")
    return results


# ── DB Integration ────────────────────────────────────────────────────────────

def _get_suppliers_from_db(supplier_ids: list[int]) -> list[dict]:
    """Load suppliers from the wholesale_supplier_finder DB by ID."""
    sys.path.insert(0, str(Path(__file__).parent))
    from wholesale_supplier_finder import get_db, supplier_to_json

    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in supplier_ids)
        rows = conn.execute(
            f"SELECT * FROM wholesale_suppliers WHERE id IN ({placeholders})",
            supplier_ids,
        ).fetchall()
        return [supplier_to_json(dict(r)) for r in rows]
    finally:
        conn.close()


def _update_outreach_status(supplier_ids: list[int], status: str):
    """Update outreach_status for given supplier IDs."""
    sys.path.insert(0, str(Path(__file__).parent))
    from wholesale_supplier_finder import get_db

    conn = get_db()
    try:
        now = datetime.utcnow().isoformat()
        placeholders = ",".join("?" for _ in supplier_ids)
        conn.execute(
            f"""UPDATE wholesale_suppliers
                SET outreach_status = ?, last_outreach_date = ?,
                    outreach_count = outreach_count + 1, updated_at = ?
                WHERE id IN ({placeholders})""",
            [status, now, now] + supplier_ids,
        )
        conn.commit()
    finally:
        conn.close()


def get_outreach_status() -> dict:
    """Return outreach statistics."""
    tracker = _load_tracker()
    total_sends = sum(tracker.get("sends", {}).values())
    return {
        "date": tracker.get("date"),
        "total_sends_today": total_sends,
        "sends_by_inbox": tracker.get("sends", {}),
        "drafts_today": tracker.get("drafts", 0),
        "rate_limits": {
            inbox: check_rate_limit(inbox)
            for inbox in tracker.get("sends", {})
        },
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Supplier Outreach Engine — generate and send wholesale outreach emails"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = sub.add_parser("generate", help="Generate outreach emails for suppliers")
    p_gen.add_argument("--suppliers", help="CSV file with supplier data")
    p_gen.add_argument("--supplier-ids", help="Comma-separated supplier IDs from DB")
    p_gen.add_argument(
        "--template", "-t", default="intro_inquiry",
        choices=list(TEMPLATES.keys()),
        help="Email template type (default: intro_inquiry)"
    )
    p_gen.add_argument("--output", "-o", help="Output JSON file (default: .tmp/outreach/drafts_<ts>.json)")

    # send
    p_send = sub.add_parser("send", help="Send draft emails via SMTP")
    p_send.add_argument("--drafts", required=True, help="JSON file with draft emails")
    p_send.add_argument("--smtp-host", default=os.getenv("SMTP_HOST", "smtp.gmail.com"))
    p_send.add_argument("--smtp-port", type=int, default=int(os.getenv("SMTP_PORT", "587")))
    p_send.add_argument("--smtp-user", default=os.getenv("SMTP_USER"))
    p_send.add_argument("--smtp-pass", default=os.getenv("SMTP_PASS"))
    p_send.add_argument("--from-name", default=os.getenv("SMTP_FROM_NAME", ""))
    p_send.add_argument("--from-email", default=os.getenv("SMTP_FROM_EMAIL"))
    p_send.add_argument("--dry-run", action="store_true", help="Don't actually send")

    # status
    sub.add_parser("status", help="Show outreach rate limit status")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        # Load suppliers
        suppliers = []
        if args.supplier_ids:
            ids = [int(x.strip()) for x in args.supplier_ids.split(",")]
            suppliers = _get_suppliers_from_db(ids)
        elif args.suppliers:
            path = Path(args.suppliers)
            if not path.exists():
                print(f"File not found: {args.suppliers}", file=sys.stderr)
                sys.exit(1)
            with open(path, newline="", encoding="utf-8") as f:
                suppliers = list(csv.DictReader(f))
        else:
            print("Provide --suppliers (CSV) or --supplier-ids (DB IDs)", file=sys.stderr)
            sys.exit(1)

        if not suppliers:
            print("No suppliers to process.", file=sys.stderr)
            sys.exit(1)

        print(f"Generating {args.template} emails for {len(suppliers)} suppliers...")
        drafts = generate_batch_emails(suppliers, template_type=args.template)

        # Save drafts
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = args.output or str(TMP_DIR / f"drafts_{ts}.json")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(drafts, indent=2))
        print(f"Drafts saved to: {out_path}")

        # Update DB outreach status
        ids_with_drafts = [
            d["supplier_id"] for d in drafts
            if d.get("supplier_id") and not d.get("error")
        ]
        if ids_with_drafts:
            _update_outreach_status(ids_with_drafts, "drafted")

    elif args.command == "send":
        drafts_path = Path(args.drafts)
        if not drafts_path.exists():
            print(f"File not found: {args.drafts}", file=sys.stderr)
            sys.exit(1)

        drafts = json.loads(drafts_path.read_text())

        if not args.smtp_user:
            print("SMTP credentials required. Set SMTP_USER/SMTP_PASS env vars or use --smtp-user/--smtp-pass", file=sys.stderr)
            sys.exit(1)

        smtp_config = {
            "smtp_host": args.smtp_host,
            "smtp_port": args.smtp_port,
            "smtp_user": args.smtp_user,
            "smtp_pass": args.smtp_pass,
            "from_name": args.from_name,
            "from_email": args.from_email or args.smtp_user,
        }

        results = send_batch(drafts, smtp_config, dry_run=args.dry_run)

        # Update DB outreach status for sent emails
        sent_ids = [
            d["supplier_id"] for d, r in zip(drafts, results)
            if r["status"] == "sent" and d.get("supplier_id")
        ]
        if sent_ids:
            _update_outreach_status(sent_ids, "sent")

        # Save results
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_path = TMP_DIR / f"send_results_{ts}.json"
        results_path.write_text(json.dumps(results, indent=2))
        print(f"Results saved to: {results_path}")

    elif args.command == "status":
        status = get_outreach_status()
        print(f"\n{'='*50}")
        print(f"  SUPPLIER OUTREACH STATUS — {status['date']}")
        print(f"{'='*50}")
        print(f"  Total sends today:  {status['total_sends_today']}")
        print(f"  Drafts today:       {status['drafts_today']}")
        if status["sends_by_inbox"]:
            print(f"\n  By Inbox:")
            for inbox, count in status["sends_by_inbox"].items():
                limit = SMTP_RATE_LIMIT["per_inbox_max"]
                print(f"    {inbox:<30} {count}/{limit}")
        else:
            print(f"\n  No sends today.")
        print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
