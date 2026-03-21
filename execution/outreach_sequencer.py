#!/usr/bin/env python3
"""
Script: outreach_sequencer.py
Purpose: Create and manage multi-touch outreach sequences.
         Takes qualified leads, generates personalized multi-touch sequences
         (email → LinkedIn → follow-up → breakup). Tracks sequence progress.
Inputs:  CLI subcommands
Outputs: Sequence touchpoints, status reports, JSON export

CLI:
    python execution/outreach_sequencer.py create-sequence --leads .tmp/filtered_leads.csv --template dream100
    python execution/outreach_sequencer.py next-touches --due today
    python execution/outreach_sequencer.py mark-sent --touch-id 5
    python execution/outreach_sequencer.py mark-replied --prospect-id 3 --notes "Interested"
    python execution/outreach_sequencer.py mark-booked --prospect-id 3
    python execution/outreach_sequencer.py stats
    python execution/outreach_sequencer.py list-sequences
    python execution/outreach_sequencer.py export --format json
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.environ.get("NOMAD_NEBULA_ROOT",
                                    "/Users/Shared/antigravity/projects/nomad-nebula"))
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / ".tmp" / "outreach" / "sequences.db"
_MODEL = "claude-sonnet-4-6"
_PRICING = {"claude-sonnet-4-6": (3.0, 15.0)}

def _cost(model, inp, out):
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000


# ── Sequence Templates ───────────────────────────────────────────────────────

TEMPLATES = {
    "dream100": [
        {"touch": 1, "day": 0, "type": "email", "desc": "GammaDoc + personalized context — show you've done homework"},
        {"touch": 2, "day": 1, "type": "linkedin_dm", "desc": "Connection request + specific value hook from their content"},
        {"touch": 3, "day": 3, "type": "followup_email", "desc": "New insight or relevant stat about their industry"},
        {"touch": 4, "day": 7, "type": "email", "desc": "Similar client result / mini case study"},
        {"touch": 5, "day": 14, "type": "email", "desc": "Quick question about their biggest growth challenge"},
        {"touch": 6, "day": 21, "type": "email", "desc": "Full case study with specific numbers and timeline"},
        {"touch": 7, "day": 30, "type": "breakup_email", "desc": "Final touch — leave door open, no pressure"},
    ],
    "cold_email": [
        {"touch": 1, "day": 0, "type": "email", "desc": "Personalized cold email — one observation about their business"},
        {"touch": 2, "day": 3, "type": "followup_email", "desc": "Value-add follow-up — share a relevant resource"},
        {"touch": 3, "day": 7, "type": "email", "desc": "Social proof email — client result that's relevant to them"},
        {"touch": 4, "day": 14, "type": "breakup_email", "desc": "Break-up email — last touch, keep it brief"},
    ],
    "warm_followup": [
        {"touch": 1, "day": 0, "type": "email", "desc": "Re-engage with new context — something changed since last touch"},
        {"touch": 2, "day": 5, "type": "linkedin_dm", "desc": "Comment on their recent post + soft ask"},
        {"touch": 3, "day": 10, "type": "email", "desc": "Offer something free (audit, template, checklist)"},
    ],
}


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    business TEXT DEFAULT 'agency',
    status TEXT DEFAULT 'active',
    prospect_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    business_name TEXT,
    website TEXT,
    niche TEXT,
    data_json TEXT,
    status TEXT DEFAULT 'pending',
    current_touch INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (sequence_id) REFERENCES sequences(id)
);

CREATE TABLE IF NOT EXISTS touches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    sequence_id INTEGER NOT NULL,
    touch_number INTEGER NOT NULL,
    touch_type TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    scheduled_date TEXT NOT NULL,
    sent_date TEXT,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id),
    FOREIGN KEY (sequence_id) REFERENCES sequences(id)
);

CREATE INDEX IF NOT EXISTS idx_touches_scheduled ON touches(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_touches_status ON touches(status);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
"""


# ── Database ─────────────────────────────────────────────────────────────────

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Voice Context ────────────────────────────────────────────────────────────

def _load_sender_context(business="agency"):
    if business == "agency":
        os_path = PROJECT_ROOT / "SabboOS" / "Agency_OS.md"
    else:
        os_path = PROJECT_ROOT / "SabboOS" / "Amazon_OS.md"
    context = ""
    if os_path.exists():
        context = os_path.read_text()[:2000]
    return context


# ── Core Functions ───────────────────────────────────────────────────────────

def create_sequence(leads_csv, template, business="agency", name=None):
    """Create a new outreach sequence from a leads CSV."""
    if template not in TEMPLATES:
        raise ValueError(f"Invalid template '{template}'. Available: {list(TEMPLATES.keys())}")

    csv_path = Path(leads_csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"Leads CSV not found: {leads_csv}")

    # Read leads
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    if not leads:
        raise ValueError("No leads found in CSV.")

    if name is None:
        name = f"{template}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"

    conn = get_db()
    try:
        # Create sequence
        conn.execute("""
            INSERT INTO sequences (name, template, business, prospect_count, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, template, business, len(leads), datetime.utcnow().isoformat()))
        seq_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        template_touches = TEMPLATES[template]
        today = datetime.utcnow()

        # Generate copy for each lead
        client = None
        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        except Exception:
            pass

        sender_context = _load_sender_context(business)
        total_cost = 0

        for lead in leads:
            lead_name = lead.get("owner_name", lead.get("name", lead.get("business_name", "Unknown")))
            lead_email = lead.get("email", "")
            lead_biz = lead.get("business_name", "")
            lead_website = lead.get("website", "")
            lead_niche = lead.get("category", lead.get("niche", ""))

            # Insert prospect
            conn.execute("""
                INSERT INTO prospects (sequence_id, name, email, business_name, website, niche, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (seq_id, lead_name, lead_email, lead_biz, lead_website, lead_niche,
                  json.dumps(lead), datetime.utcnow().isoformat()))
            prospect_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Create touches
            for t in template_touches:
                scheduled = (today + timedelta(days=t["day"])).strftime("%Y-%m-%d")

                subject = ""
                body = ""

                # Generate copy via LLM if available
                if client:
                    try:
                        subject, body, cost = _generate_touch_copy(
                            client, lead, t, sender_context, business
                        )
                        total_cost += cost
                    except Exception as e:
                        print(f"[outreach_sequencer] Copy gen failed for {lead_name} touch {t['touch']}: {e}",
                              file=sys.stderr)
                        subject = f"Touch {t['touch']}: {t['desc']}"
                        body = f"[DRAFT] {t['desc']} — personalize for {lead_biz}"
                else:
                    subject = f"Touch {t['touch']}: {t['desc']}"
                    body = f"[DRAFT] {t['desc']} — personalize for {lead_biz}"

                conn.execute("""
                    INSERT INTO touches (prospect_id, sequence_id, touch_number, touch_type,
                                        subject, body, scheduled_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
                """, (prospect_id, seq_id, t["touch"], t["type"], subject, body, scheduled))

            conn.execute("UPDATE prospects SET status = 'in_sequence', current_touch = 1 WHERE id = ?",
                         (prospect_id,))

        conn.commit()
        print(f"[outreach_sequencer] Created sequence '{name}': {len(leads)} prospects, "
              f"{len(leads) * len(template_touches)} touches")
        if total_cost > 0:
            print(f"[outreach_sequencer] Copy generation cost: ${total_cost:.4f}")

        return {
            "sequence_id": seq_id,
            "name": name,
            "template": template,
            "prospects": len(leads),
            "touches": len(leads) * len(template_touches),
            "cost": round(total_cost, 4),
        }
    finally:
        conn.close()


def _generate_touch_copy(client, lead, touch_spec, sender_context, business):
    """Generate personalized copy for a single touch."""
    lead_context = json.dumps({k: v for k, v in lead.items()
                               if k in ["business_name", "owner_name", "category",
                                        "website", "rating", "review_count", "address"]},
                              indent=2)

    prompt = f"""Write a {touch_spec['type']} for outreach touch #{touch_spec['touch']}.

Purpose: {touch_spec['desc']}

About the sender:
{sender_context[:1000]}

About the prospect:
{lead_context}

Rules:
- Max 120 words for emails, 300 chars for LinkedIn DMs
- Written operator-to-operator — direct, no corporate fluff
- Reference something specific about their business
- Sound like a real person, not a template
- No: "I hope this finds you well", "synergy", "leverage"

Output format:
SUBJECT: [subject line]
BODY:
[email body]"""

    response = client.messages.create(
        model=_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    cost = _cost(_MODEL, response.usage.input_tokens, response.usage.output_tokens)

    subject = ""
    body = text
    if "SUBJECT:" in text:
        parts = text.split("BODY:", 1)
        subject_part = parts[0].replace("SUBJECT:", "").strip()
        subject = subject_part.split("\n")[0].strip()
        body = parts[1].strip() if len(parts) > 1 else text

    return subject, body, cost


def get_next_touches(due_date=None):
    """Get touches due on a given date."""
    if due_date is None or due_date == "today":
        due_date = datetime.utcnow().strftime("%Y-%m-%d")

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT t.*, p.name AS prospect_name, p.email, p.business_name,
                   s.name AS sequence_name, s.template
            FROM touches t
            JOIN prospects p ON p.id = t.prospect_id
            JOIN sequences s ON s.id = t.sequence_id
            WHERE t.scheduled_date <= ? AND t.status IN ('draft', 'scheduled')
            ORDER BY t.scheduled_date ASC, t.touch_number ASC
        """, (due_date,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_sent(touch_id):
    conn = get_db()
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        conn.execute("UPDATE touches SET status = 'sent', sent_date = ? WHERE id = ?",
                     (today, touch_id))

        # Update prospect's current_touch
        touch = conn.execute("SELECT prospect_id, touch_number FROM touches WHERE id = ?",
                             (touch_id,)).fetchone()
        if touch:
            conn.execute("UPDATE prospects SET current_touch = ? WHERE id = ?",
                         (touch["touch_number"], touch["prospect_id"]))
        conn.commit()
        return {"touch_id": touch_id, "status": "sent", "date": today}
    finally:
        conn.close()


def mark_replied(prospect_id, notes=None):
    conn = get_db()
    try:
        conn.execute("UPDATE prospects SET status = 'replied' WHERE id = ?", (prospect_id,))
        # Cancel remaining unsent touches
        conn.execute("""
            UPDATE touches SET status = 'cancelled'
            WHERE prospect_id = ? AND status IN ('draft', 'scheduled')
        """, (prospect_id,))
        if notes:
            conn.execute("UPDATE prospects SET data_json = json_set(COALESCE(data_json, '{}'), '$.reply_notes', ?) WHERE id = ?",
                         (notes, prospect_id))
        conn.commit()
        return {"prospect_id": prospect_id, "status": "replied"}
    finally:
        conn.close()


def mark_booked(prospect_id, notes=None):
    conn = get_db()
    try:
        conn.execute("UPDATE prospects SET status = 'booked' WHERE id = ?", (prospect_id,))
        conn.execute("""
            UPDATE touches SET status = 'cancelled'
            WHERE prospect_id = ? AND status IN ('draft', 'scheduled')
        """, (prospect_id,))
        conn.commit()
        return {"prospect_id": prospect_id, "status": "booked"}
    finally:
        conn.close()


def get_stats():
    conn = get_db()
    try:
        # Prospect stats
        prospect_stats = conn.execute("""
            SELECT status, COUNT(*) as cnt FROM prospects GROUP BY status
        """).fetchall()
        by_status = {r["status"]: r["cnt"] for r in prospect_stats}
        total = sum(by_status.values())

        # Touch stats
        touch_stats = conn.execute("""
            SELECT status, COUNT(*) as cnt FROM touches GROUP BY status
        """).fetchall()
        touches_by_status = {r["status"]: r["cnt"] for r in touch_stats}

        # Rates
        replied = by_status.get("replied", 0) + by_status.get("booked", 0)
        booked = by_status.get("booked", 0)
        sent_count = touches_by_status.get("sent", 0)

        return {
            "total_prospects": total,
            "by_status": by_status,
            "response_rate": round(replied / total * 100, 1) if total > 0 else 0,
            "book_rate": round(booked / total * 100, 1) if total > 0 else 0,
            "touches_sent": sent_count,
            "touches_pending": touches_by_status.get("draft", 0) + touches_by_status.get("scheduled", 0),
            "touches_cancelled": touches_by_status.get("cancelled", 0),
        }
    finally:
        conn.close()


def list_sequences():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT s.*,
                COUNT(DISTINCT p.id) as prospect_count,
                SUM(CASE WHEN p.status = 'replied' THEN 1 ELSE 0 END) as replied,
                SUM(CASE WHEN p.status = 'booked' THEN 1 ELSE 0 END) as booked
            FROM sequences s
            LEFT JOIN prospects p ON p.sequence_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_json():
    stats = get_stats()
    seqs = list_sequences()
    return {
        "stats": stats,
        "sequences": seqs,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_create_sequence(args):
    try:
        result = create_sequence(args.leads, args.template, args.business, args.name)
        print(json.dumps(result, indent=2))
    except (ValueError, FileNotFoundError) as e:
        print(f"[outreach_sequencer] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_next_touches(args):
    touches = get_next_touches(args.due)
    if not touches:
        print("[outreach_sequencer] No touches due.")
        return
    for t in touches:
        print(f"  #{t['id']} [{t['touch_type']}] {t['prospect_name']} ({t['business_name']}) — touch {t['touch_number']}")
        if t.get("subject"):
            print(f"    Subject: {t['subject'][:80]}")
    print(f"\n  Total: {len(touches)} touches due")


def cli_mark_sent(args):
    result = mark_sent(args.touch_id)
    print(f"[outreach_sequencer] Touch {result['touch_id']} marked as sent.")


def cli_mark_replied(args):
    result = mark_replied(args.prospect_id, args.notes)
    print(f"[outreach_sequencer] Prospect {result['prospect_id']} marked as replied.")


def cli_mark_booked(args):
    result = mark_booked(args.prospect_id, args.notes)
    print(f"[outreach_sequencer] Prospect {result['prospect_id']} marked as booked!")


def cli_stats(args):
    stats = get_stats()
    print(json.dumps(stats, indent=2))


def cli_list_sequences(args):
    seqs = list_sequences()
    if not seqs:
        print("[outreach_sequencer] No sequences found.")
        return
    for s in seqs:
        print(f"  [{s['id']}] {s['name']} ({s['template']}) — {s['prospect_count']} prospects, "
              f"{s.get('replied', 0)} replied, {s.get('booked', 0)} booked")


def cli_export(args):
    result = export_json()
    print(json.dumps(result, indent=2))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Outreach Sequencer — multi-touch personalized outreach sequences"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # create-sequence
    p_create = subparsers.add_parser("create-sequence", help="Create a new sequence from leads CSV")
    p_create.add_argument("--leads", required=True, help="Path to leads CSV")
    p_create.add_argument("--template", required=True, choices=list(TEMPLATES.keys()), help="Sequence template")
    p_create.add_argument("--business", default="agency", choices=["agency", "coaching"])
    p_create.add_argument("--name", default=None, help="Sequence name (auto-generated if omitted)")
    p_create.set_defaults(func=cli_create_sequence)

    # next-touches
    p_next = subparsers.add_parser("next-touches", help="View touches due")
    p_next.add_argument("--due", default="today", help="Due date (YYYY-MM-DD or 'today')")
    p_next.set_defaults(func=cli_next_touches)

    # mark-sent
    p_sent = subparsers.add_parser("mark-sent", help="Mark a touch as sent")
    p_sent.add_argument("--touch-id", type=int, required=True, help="Touch ID")
    p_sent.set_defaults(func=cli_mark_sent)

    # mark-replied
    p_replied = subparsers.add_parser("mark-replied", help="Mark a prospect as replied")
    p_replied.add_argument("--prospect-id", type=int, required=True, help="Prospect ID")
    p_replied.add_argument("--notes", default=None, help="Reply notes")
    p_replied.set_defaults(func=cli_mark_replied)

    # mark-booked
    p_booked = subparsers.add_parser("mark-booked", help="Mark a prospect as booked")
    p_booked.add_argument("--prospect-id", type=int, required=True, help="Prospect ID")
    p_booked.add_argument("--notes", default=None, help="Booking notes")
    p_booked.set_defaults(func=cli_mark_booked)

    # stats
    p_stats = subparsers.add_parser("stats", help="Sequence statistics")
    p_stats.set_defaults(func=cli_stats)

    # list-sequences
    p_list = subparsers.add_parser("list-sequences", help="List all sequences")
    p_list.set_defaults(func=cli_list_sequences)

    # export
    p_export = subparsers.add_parser("export", help="Export as JSON")
    p_export.add_argument("--format", default="json", choices=["json"])
    p_export.set_defaults(func=cli_export)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
