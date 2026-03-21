#!/usr/bin/env python3
"""
Script: brand_outreach.py
Purpose: Automates direct-to-brand sourcing outreach — find brand contact info,
         generate personalized outreach emails, track conversations, and manage
         the pipeline from cold outreach to approved reseller.
Inputs:  CLI subcommands (discover, email, send, reply, status, followups, pipeline, list, export)
Outputs: Brand contact info, outreach emails, pipeline stats (stdout or CSV)

CLI:
    python execution/brand_outreach.py discover --brand "Anker"
    python execution/brand_outreach.py discover --brands-file brands.txt
    python execution/brand_outreach.py discover --from-results results.json
    python execution/brand_outreach.py email --brand-id 5 --template cold_intro
    python execution/brand_outreach.py send --brand-id 5 --template cold_intro
    python execution/brand_outreach.py reply --brand-id 5 --notes "They have a form..."
    python execution/brand_outreach.py status --brand-id 5 --set approved --notes "40% off MSRP"
    python execution/brand_outreach.py followups --days 7
    python execution/brand_outreach.py pipeline
    python execution/brand_outreach.py list --status contacted
    python execution/brand_outreach.py export --output brands.csv
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    print("Install with: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / ".tmp" / "sourcing" / "price_tracker.db"
REQUEST_DELAY = 3  # seconds between web requests
REQUEST_TIMEOUT = 15  # seconds per request

VALID_STATUSES = [
    "discovered", "contacted", "replied",
    "application_sent", "approved", "rejected", "active",
]

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Email Templates ──────────────────────────────────────────────────────────

TEMPLATES = {
    "cold_intro": {
        "subject": "Wholesale / Authorized Reseller Inquiry — {company_name}",
        "body": (
            "Hi {brand_name} Team,\n\n"
            "My name is {sender_name} with {company_name}. We're an Amazon seller\n"
            "specializing in {categories} and are interested in becoming an authorized\n"
            "reseller of {brand_name} products.\n\n"
            "We maintain a professional Amazon storefront ({store_url}) and handle all\n"
            "FBA logistics, ensuring your products are properly represented on the platform.\n\n"
            "Could you point me to your wholesale or authorized reseller program?\n"
            "I'd love to learn about your requirements, minimum orders, and pricing tiers.\n\n"
            "Best regards,\n"
            "{sender_name}\n"
            "{company_name}"
        ),
    },
    "followup_1": {
        "subject": "Following Up — Wholesale Inquiry for {brand_name}",
        "body": (
            "Hi {brand_name} Team,\n\n"
            "I wanted to follow up on my previous email regarding becoming an authorized\n"
            "reseller of {brand_name} products on Amazon.\n\n"
            "We at {company_name} are genuinely interested in carrying your products and\n"
            "believe we can help expand your Amazon presence professionally.\n\n"
            "Would you be able to share information about your wholesale program or\n"
            "point me to the right person to speak with?\n\n"
            "Thank you for your time,\n"
            "{sender_name}\n"
            "{company_name}\n"
            "{store_url}"
        ),
    },
    "followup_2": {
        "subject": "Final Follow-Up — {brand_name} Wholesale Partnership",
        "body": (
            "Hi {brand_name} Team,\n\n"
            "I understand you're busy, so I'll keep this brief. This is my final\n"
            "follow-up regarding becoming an authorized Amazon reseller for {brand_name}.\n\n"
            "If there's a wholesale application or distributor program I should apply\n"
            "through instead, I'm happy to go that route.\n\n"
            "If now isn't a good time, no worries at all — feel free to reach out\n"
            "whenever you're open to new retail partners.\n\n"
            "Best,\n"
            "{sender_name}\n"
            "{company_name}\n"
            "{store_url}"
        ),
    },
    "application_reply": {
        "subject": "Re: Wholesale Application — {company_name}",
        "body": (
            "Hi {brand_name} Team,\n\n"
            "Thank you for pointing me to your wholesale application. I've completed\n"
            "and submitted it.\n\n"
            "For reference, here's a quick overview of our operation:\n"
            "- Company: {company_name}\n"
            "- Amazon Store: {store_url}\n"
            "- Estimated Monthly Volume: {monthly_volume}\n"
            "- Primary Categories: {categories}\n\n"
            "Please let me know if you need any additional information to process\n"
            "the application.\n\n"
            "Best regards,\n"
            "{sender_name}\n"
            "{company_name}"
        ),
    },
}

# ── Database ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS brand_outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name TEXT NOT NULL,
    website TEXT,
    contact_email TEXT,
    contact_page_url TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    wholesale_url TEXT,
    min_order TEXT,
    discount_tier TEXT,
    notes TEXT,
    discovered_at TEXT NOT NULL,
    last_contact_at TEXT,
    next_followup TEXT,
    UNIQUE(brand_name)
);

CREATE TABLE IF NOT EXISTS outreach_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    template_used TEXT NOT NULL,
    email_subject TEXT NOT NULL,
    email_body TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    response_received INTEGER NOT NULL DEFAULT 0,
    response_notes TEXT,
    FOREIGN KEY (brand_id) REFERENCES brand_outreach(id)
);
"""


def get_db():
    """Get a database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Web Discovery ────────────────────────────────────────────────────────────

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Emails to filter out (generic/useless)
JUNK_EMAIL_PATTERNS = [
    r".*@example\.com$",
    r".*@sentry\.io$",
    r".*\.png$",
    r".*\.jpg$",
    r".*\.gif$",
    r".*@.*wixpress.*",
    r"^noreply@",
    r"^no-reply@",
    r"^donotreply@",
]


def _is_junk_email(email: str) -> bool:
    """Filter out obviously non-useful emails."""
    email_lower = email.lower()
    for pattern in JUNK_EMAIL_PATTERNS:
        if re.match(pattern, email_lower):
            return True
    return False


def _extract_emails(html: str) -> List[str]:
    """Extract valid emails from HTML content."""
    raw = EMAIL_REGEX.findall(html)
    seen = set()
    result = []
    for email in raw:
        email_lower = email.lower()
        if email_lower not in seen and not _is_junk_email(email):
            seen.add(email_lower)
            result.append(email)
    return result


def _fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch a page, return HTML or None on failure."""
    try:
        resp = session.get(
            url, headers=DEFAULT_HEADERS,
            timeout=REQUEST_TIMEOUT, allow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.text
        return None
    except (requests.RequestException, Exception):
        return None


def _guess_brand_domain(brand_name: str) -> str:
    """Guess the brand domain from its name."""
    slug = re.sub(r"[^a-z0-9]", "", brand_name.lower())
    return f"https://www.{slug}.com"


def _find_contact_pages(base_url: str, html: str) -> List[str]:
    """Find links that look like contact/wholesale pages."""
    keywords = [
        "contact", "wholesale", "distributor", "retailer",
        "reseller", "dealer", "partner", "become-a",
        "authorized", "bulk", "b2b", "trade",
    ]
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for link in soup.find_all("a", href=True):
        href = link["href"].lower()
        text = link.get_text(strip=True).lower()
        combined = href + " " + text
        if any(kw in combined for kw in keywords):
            full_url = urljoin(base_url, link["href"])
            if full_url not in found:
                found.append(full_url)
    return found


WHOLESALE_PATHS = [
    "/wholesale", "/distributors", "/contact", "/become-a-retailer",
    "/reseller", "/contact-us", "/dealer", "/partner",
    "/authorized-reseller", "/bulk-orders", "/b2b", "/trade",
]


def find_brand_contacts(brand_name: str) -> Dict:
    """
    Search for brand website, find contact/wholesale/distributor pages.
    Returns dict with: website, emails, contact_pages, wholesale_url
    """
    result = {
        "brand_name": brand_name,
        "website": None,
        "emails": [],
        "contact_pages": [],
        "wholesale_url": None,
    }

    session = requests.Session()
    base_url = _guess_brand_domain(brand_name)

    # Try the main page
    print(f"  Checking {base_url} ...")
    html = _fetch_page(base_url, session)
    if html is None:
        # Try with hyphens for multi-word brands
        slug = re.sub(r"[^a-z0-9]+", "-", brand_name.lower()).strip("-")
        base_url = f"https://www.{slug}.com"
        print(f"  Trying {base_url} ...")
        html = _fetch_page(base_url, session)

    if html is None:
        print(f"  Could not reach website for {brand_name}")
        return result

    result["website"] = base_url
    result["emails"].extend(_extract_emails(html))

    # Find contact-like links on the home page
    contact_pages = _find_contact_pages(base_url, html)
    result["contact_pages"] = contact_pages

    # Try common wholesale/contact paths
    for path in WHOLESALE_PATHS:
        url = base_url.rstrip("/") + path
        time.sleep(REQUEST_DELAY)
        print(f"  Trying {url} ...")
        page_html = _fetch_page(url, session)
        if page_html:
            emails = _extract_emails(page_html)
            result["emails"].extend(emails)
            if any(kw in path for kw in ["wholesale", "distributor", "reseller", "dealer", "b2b", "trade"]):
                result["wholesale_url"] = url
            if url not in result["contact_pages"]:
                result["contact_pages"].append(url)

    # Crawl discovered contact pages
    for page_url in contact_pages[:5]:  # limit to 5 pages
        if page_url.startswith(base_url):
            time.sleep(REQUEST_DELAY)
            print(f"  Crawling {page_url} ...")
            page_html = _fetch_page(page_url, session)
            if page_html:
                result["emails"].extend(_extract_emails(page_html))
                if any(kw in page_url.lower() for kw in ["wholesale", "distributor", "reseller"]):
                    result["wholesale_url"] = page_url

    # Deduplicate emails
    seen = set()
    unique = []
    for e in result["emails"]:
        if e.lower() not in seen:
            seen.add(e.lower())
            unique.append(e)
    result["emails"] = unique

    return result


def enrich_from_amazon(asin: str) -> Optional[str]:
    """Given an ASIN, try to extract the brand name from sourcing results."""
    results_dir = Path(__file__).parent.parent / ".tmp" / "sourcing"
    if not results_dir.exists():
        return None

    for json_file in results_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            items = data if isinstance(data, list) else data.get("results", [])
            for item in items:
                if item.get("asin") == asin:
                    return item.get("brand") or item.get("brand_name")
        except (json.JSONDecodeError, KeyError):
            continue
    return None


# ── Pipeline Management ──────────────────────────────────────────────────────

def discover_brand(brand_name: str) -> Dict:
    """Find contacts for a brand, store in DB, return info."""
    db = get_db()
    now = datetime.utcnow().isoformat()

    # Check if already in DB
    existing = db.execute(
        "SELECT * FROM brand_outreach WHERE LOWER(brand_name) = LOWER(?)",
        (brand_name,),
    ).fetchone()

    if existing:
        print(f"  Brand '{brand_name}' already in DB (id={existing['id']}, status={existing['status']})")
        return dict(existing)

    print(f"Discovering brand: {brand_name}")
    info = find_brand_contacts(brand_name)

    contact_email = info["emails"][0] if info["emails"] else None
    contact_page = info["contact_pages"][0] if info["contact_pages"] else None
    all_emails = ", ".join(info["emails"]) if len(info["emails"]) > 1 else None

    notes_parts = []
    if all_emails:
        notes_parts.append(f"All emails found: {all_emails}")
    if info["contact_pages"]:
        notes_parts.append(f"Contact pages: {', '.join(info['contact_pages'][:5])}")

    db.execute(
        """INSERT INTO brand_outreach
           (brand_name, website, contact_email, contact_page_url, status,
            wholesale_url, notes, discovered_at)
           VALUES (?, ?, ?, ?, 'discovered', ?, ?, ?)""",
        (
            brand_name,
            info["website"],
            contact_email,
            contact_page,
            info["wholesale_url"],
            "; ".join(notes_parts) if notes_parts else None,
            now,
        ),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM brand_outreach WHERE LOWER(brand_name) = LOWER(?)",
        (brand_name,),
    ).fetchone()
    db.close()

    print(f"  Stored: id={row['id']}, email={contact_email}, wholesale={info['wholesale_url']}")
    return dict(row)


def batch_discover(brand_names: List[str]) -> List[Dict]:
    """Discover multiple brands, with delay between each."""
    results = []
    for i, name in enumerate(brand_names):
        name = name.strip()
        if not name:
            continue
        print(f"\n[{i+1}/{len(brand_names)}] {name}")
        result = discover_brand(name)
        results.append(result)
        if i < len(brand_names) - 1:
            time.sleep(REQUEST_DELAY)
    return results


def generate_email(brand_id: int, template: str = "cold_intro") -> Dict:
    """Generate an outreach email for a brand from a template."""
    if template not in TEMPLATES:
        print(f"ERROR: Unknown template '{template}'. Available: {', '.join(TEMPLATES.keys())}")
        sys.exit(1)

    db = get_db()
    brand = db.execute("SELECT * FROM brand_outreach WHERE id = ?", (brand_id,)).fetchone()
    db.close()

    if not brand:
        print(f"ERROR: No brand found with id={brand_id}")
        sys.exit(1)

    sender_name = os.getenv("OUTREACH_SENDER_NAME", "Your Name")
    company_name = os.getenv("OUTREACH_COMPANY", "Your Company")
    store_url = os.getenv("OUTREACH_STORE_URL", "https://amazon.com/shops/yourstore")

    context = {
        "brand_name": brand["brand_name"],
        "sender_name": sender_name,
        "company_name": company_name,
        "store_url": store_url,
        "monthly_volume": os.getenv("OUTREACH_MONTHLY_VOLUME", "200+ units"),
        "categories": os.getenv("OUTREACH_CATEGORIES", "consumer electronics and home goods"),
    }

    tmpl = TEMPLATES[template]
    subject = tmpl["subject"].format(**context)
    body = tmpl["body"].format(**context)

    return {"subject": subject, "body": body, "template": template, "brand_id": brand_id}


def mark_sent(brand_id: int, template: str, subject: str, body: str) -> None:
    """Log that an outreach email was sent (user sends manually)."""
    db = get_db()
    now = datetime.utcnow().isoformat()

    # Calculate next followup based on template
    if template == "cold_intro":
        next_followup = (datetime.utcnow() + timedelta(days=5)).isoformat()
    elif template == "followup_1":
        next_followup = (datetime.utcnow() + timedelta(days=5)).isoformat()
    elif template == "followup_2":
        next_followup = (datetime.utcnow() + timedelta(days=14)).isoformat()
    else:
        next_followup = (datetime.utcnow() + timedelta(days=7)).isoformat()

    db.execute(
        """INSERT INTO outreach_emails
           (brand_id, template_used, email_subject, email_body, sent_at)
           VALUES (?, ?, ?, ?, ?)""",
        (brand_id, template, subject, body, now),
    )
    db.execute(
        """UPDATE brand_outreach
           SET status = CASE WHEN status = 'discovered' THEN 'contacted' ELSE status END,
               last_contact_at = ?,
               next_followup = ?
           WHERE id = ?""",
        (now, next_followup, brand_id),
    )
    db.commit()
    db.close()
    print(f"  Logged email (template={template}) for brand_id={brand_id}. Next followup: {next_followup[:10]}")


def mark_replied(brand_id: int, notes: str) -> None:
    """Log that a brand replied to outreach."""
    db = get_db()
    now = datetime.utcnow().isoformat()

    # Mark latest email as having a response
    db.execute(
        """UPDATE outreach_emails
           SET response_received = 1, response_notes = ?
           WHERE brand_id = ? AND id = (
               SELECT MAX(id) FROM outreach_emails WHERE brand_id = ?
           )""",
        (notes, brand_id, brand_id),
    )
    db.execute(
        """UPDATE brand_outreach
           SET status = 'replied', notes = COALESCE(notes || '; ', '') || ?,
               next_followup = NULL
           WHERE id = ?""",
        (f"Reply ({now[:10]}): {notes}", brand_id),
    )
    db.commit()
    db.close()
    print(f"  Marked brand_id={brand_id} as replied.")


def update_status(brand_id: int, status: str, notes: Optional[str] = None) -> None:
    """Update pipeline status for a brand."""
    if status not in VALID_STATUSES:
        print(f"ERROR: Invalid status '{status}'. Valid: {', '.join(VALID_STATUSES)}")
        sys.exit(1)

    db = get_db()
    now = datetime.utcnow().isoformat()

    if notes:
        db.execute(
            """UPDATE brand_outreach
               SET status = ?, notes = COALESCE(notes || '; ', '') || ?
               WHERE id = ?""",
            (status, f"Status→{status} ({now[:10]}): {notes}", brand_id),
        )
    else:
        db.execute(
            "UPDATE brand_outreach SET status = ? WHERE id = ?",
            (status, brand_id),
        )

    # Clear followup if terminal status
    if status in ("approved", "rejected", "active"):
        db.execute(
            "UPDATE brand_outreach SET next_followup = NULL WHERE id = ?",
            (brand_id,),
        )

    db.commit()
    db.close()
    print(f"  Updated brand_id={brand_id} → status={status}")


def get_followups(days: int = 7) -> List[Dict]:
    """Get brands due for followup within the next N days."""
    db = get_db()
    cutoff = (datetime.utcnow() + timedelta(days=days)).isoformat()
    rows = db.execute(
        """SELECT * FROM brand_outreach
           WHERE next_followup IS NOT NULL
             AND next_followup <= ?
             AND status IN ('contacted', 'application_sent')
           ORDER BY next_followup ASC""",
        (cutoff,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_pipeline_summary() -> Dict:
    """Get counts by pipeline status."""
    db = get_db()
    rows = db.execute(
        "SELECT status, COUNT(*) as count FROM brand_outreach GROUP BY status ORDER BY status",
    ).fetchall()
    total = db.execute("SELECT COUNT(*) as count FROM brand_outreach").fetchone()["count"]
    db.close()
    summary = {r["status"]: r["count"] for r in rows}
    summary["_total"] = total
    return summary


def list_brands(status: Optional[str] = None) -> List[Dict]:
    """List brands, optionally filtered by status."""
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM brand_outreach WHERE status = ? ORDER BY discovered_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM brand_outreach ORDER BY discovered_at DESC",
        ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def import_brands_from_results(results_path: str) -> List[str]:
    """Extract unique brand names from sourcing results JSON, auto-discover."""
    path = Path(results_path)
    if not path.exists():
        print(f"ERROR: File not found: {results_path}")
        sys.exit(1)

    data = json.loads(path.read_text())
    items = data if isinstance(data, list) else data.get("results", [])

    brands = set()
    for item in items:
        brand = item.get("brand") or item.get("brand_name")
        if brand and brand.strip():
            brands.add(brand.strip())

    brand_list = sorted(brands)
    print(f"Found {len(brand_list)} unique brands in {results_path}")

    if brand_list:
        batch_discover(brand_list)

    return brand_list


def export_pipeline(output_path: str) -> None:
    """Export the full pipeline to CSV."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM brand_outreach ORDER BY status, brand_name",
    ).fetchall()
    db.close()

    if not rows:
        print("Pipeline is empty — nothing to export.")
        return

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    columns = rows[0].keys()
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    print(f"Exported {len(rows)} brands → {output_path}")


# ── Display Helpers ──────────────────────────────────────────────────────────

def _print_brand(brand: dict, verbose: bool = False) -> None:
    """Print a brand record in a readable format."""
    print(f"  [{brand['id']}] {brand['brand_name']}  ({brand['status']})")
    if brand.get("website"):
        print(f"      Website: {brand['website']}")
    if brand.get("contact_email"):
        print(f"      Email:   {brand['contact_email']}")
    if brand.get("wholesale_url"):
        print(f"      Wholesale: {brand['wholesale_url']}")
    if brand.get("next_followup"):
        print(f"      Next followup: {brand['next_followup'][:10]}")
    if verbose and brand.get("notes"):
        print(f"      Notes: {brand['notes'][:200]}")


def _print_pipeline(summary: dict) -> None:
    """Print pipeline summary."""
    total = summary.pop("_total", 0)
    print(f"\n  Pipeline Summary ({total} total brands)")
    print("  " + "─" * 40)
    for status in VALID_STATUSES:
        count = summary.get(status, 0)
        bar = "█" * count
        print(f"  {status:<18} {count:>4}  {bar}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Brand outreach pipeline — discover contacts, generate emails, track status.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p_disc = sub.add_parser("discover", help="Find brand contact info")
    disc_group = p_disc.add_mutually_exclusive_group(required=True)
    disc_group.add_argument("--brand", help="Single brand name to discover")
    disc_group.add_argument("--brands-file", help="File with one brand per line")
    disc_group.add_argument("--from-results", help="Extract brands from sourcing results JSON")

    # email
    p_email = sub.add_parser("email", help="Generate outreach email (print to stdout)")
    p_email.add_argument("--brand-id", type=int, required=True)
    p_email.add_argument("--template", default="cold_intro",
                         choices=list(TEMPLATES.keys()))

    # send
    p_send = sub.add_parser("send", help="Generate email and mark as sent (manual send)")
    p_send.add_argument("--brand-id", type=int, required=True)
    p_send.add_argument("--template", default="cold_intro",
                        choices=list(TEMPLATES.keys()))

    # reply
    p_reply = sub.add_parser("reply", help="Log that a brand replied")
    p_reply.add_argument("--brand-id", type=int, required=True)
    p_reply.add_argument("--notes", required=True, help="Details of the reply")

    # status
    p_status = sub.add_parser("status", help="Update brand pipeline status")
    p_status.add_argument("--brand-id", type=int, required=True)
    p_status.add_argument("--set", required=True, dest="new_status",
                          choices=VALID_STATUSES)
    p_status.add_argument("--notes", default=None)

    # followups
    p_follow = sub.add_parser("followups", help="Show brands due for followup")
    p_follow.add_argument("--days", type=int, default=7)

    # pipeline
    sub.add_parser("pipeline", help="Show pipeline summary")

    # list
    p_list = sub.add_parser("list", help="List brands by status")
    p_list.add_argument("--status", default=None, choices=VALID_STATUSES)

    # export
    p_export = sub.add_parser("export", help="Export pipeline to CSV")
    p_export.add_argument("--output", required=True, help="Output CSV path")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "discover":
        if args.brand:
            result = discover_brand(args.brand)
            _print_brand(result, verbose=True)
        elif args.brands_file:
            path = Path(args.brands_file)
            if not path.exists():
                print(f"ERROR: File not found: {args.brands_file}")
                sys.exit(1)
            names = [line.strip() for line in path.read_text().splitlines() if line.strip()]
            print(f"Batch discovering {len(names)} brands...")
            batch_discover(names)
        elif args.from_results:
            import_brands_from_results(args.from_results)

    elif args.command == "email":
        email = generate_email(args.brand_id, args.template)
        print(f"\nSubject: {email['subject']}\n")
        print(email["body"])

    elif args.command == "send":
        email = generate_email(args.brand_id, args.template)
        print(f"\nSubject: {email['subject']}\n")
        print(email["body"])
        print("\n" + "─" * 60)
        mark_sent(args.brand_id, args.template, email["subject"], email["body"])
        print("  (Copy the email above and send it manually.)")

    elif args.command == "reply":
        mark_replied(args.brand_id, args.notes)

    elif args.command == "status":
        update_status(args.brand_id, args.new_status, args.notes)

    elif args.command == "followups":
        brands = get_followups(args.days)
        if not brands:
            print(f"No followups due in the next {args.days} days.")
        else:
            print(f"\nFollowups due within {args.days} days ({len(brands)} brands):\n")
            for b in brands:
                _print_brand(b)

    elif args.command == "pipeline":
        summary = get_pipeline_summary()
        _print_pipeline(summary)

    elif args.command == "list":
        brands = list_brands(args.status)
        label = args.status or "all"
        if not brands:
            print(f"No brands with status '{label}'.")
        else:
            print(f"\n{len(brands)} brands ({label}):\n")
            for b in brands:
                _print_brand(b, verbose=True)

    elif args.command == "export":
        export_pipeline(args.output)


if __name__ == "__main__":
    main()
