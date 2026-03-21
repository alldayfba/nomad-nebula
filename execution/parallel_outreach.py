#!/usr/bin/env python3
"""
parallel_outreach.py — Parallel Browser Agent Orchestrator.

Takes a CSV of leads with websites, spawns N Playwright browser instances,
each navigating to the contact page and filling out the form dynamically.

Usage:
    # Run outreach on 10 leads, 3 browsers at a time
    python execution/parallel_outreach.py \
        --input .tmp/filtered_leads.csv \
        --max-browsers 3 \
        --message-template "outreach_intro"

    # Dry run (navigates but doesn't submit)
    python execution/parallel_outreach.py \
        --input leads.csv \
        --max-browsers 2 \
        --dry-run

    # With custom message
    python execution/parallel_outreach.py \
        --input leads.csv \
        --max-browsers 5 \
        --message "Hi {first_name}, I noticed {company} doesn't have a growth system in place..."
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

TMP_DIR = Path(".tmp/outreach")
LOG_FILE = TMP_DIR / "outreach_log.json"
SCREENSHOT_DIR = TMP_DIR / "screenshots"
MODEL = "claude-haiku-4-5-20251001"  # Cheap model for form analysis
MAX_TOKENS = 2048

# Default outreach templates
TEMPLATES = {
    "outreach_intro": (
        "Hi {first_name},\n\n"
        "I came across {company} and was impressed by what you've built. "
        "I help businesses like yours install a repeatable growth engine — "
        "not just run campaigns, but build the system that drives leads on autopilot.\n\n"
        "Would you be open to a quick 15-min call this week to see if it's a fit?\n\n"
        "Best,\nSabbo"
    ),
    "outreach_audit": (
        "Hi {first_name},\n\n"
        "I put together a quick growth audit for {company} — "
        "found a few things that could 2-3x your inbound leads with some simple changes.\n\n"
        "Happy to walk you through it on a quick call. No pitch, just insights.\n\n"
        "Best,\nSabbo"
    ),
    "outreach_fba": (
        "Hi {first_name},\n\n"
        "I noticed {company} is in the Amazon space. "
        "I coach sellers to hit their first (or next) $10K month — "
        "not with a course, but with hands-on coaching from someone actively selling.\n\n"
        "Worth a quick chat?\n\n"
        "Best,\nSabbo"
    ),
}

# ── AI Contact Form Analyzer ─────────────────────────────────────────────────

FORM_ANALYSIS_PROMPT = """Analyze this webpage screenshot. I need to fill out a contact form on this page.

Return a JSON object with:
1. "has_contact_form": true/false — is there a visible contact form?
2. "fields": list of form fields found, each with:
   - "label": the field label (e.g., "First Name", "Email", "Message")
   - "field_type": "text", "email", "textarea", "phone", "select", "checkbox"
   - "selector": best CSS selector to target this field
   - "required": true/false
3. "submit_selector": CSS selector for the submit button
4. "contact_page_link": if no form on this page, CSS selector for a "Contact" or "Contact Us" link (or null)

Return ONLY valid JSON, no explanation."""


async def analyze_page_for_form(client: anthropic.Anthropic, screenshot_path: Path) -> dict:
    """Use Claude to analyze a screenshot and find form fields."""
    import base64
    img_data = base64.b64encode(screenshot_path.read_bytes()).decode()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_data}},
                    {"type": "text", "text": FORM_ANALYSIS_PROMPT},
                ],
            }],
        )
        text = response.content[0].text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        return {"error": str(e), "has_contact_form": False}

    return {"has_contact_form": False}


# ── Form Filler ───────────────────────────────────────────────────────────────

def personalize_message(template: str, lead: dict) -> str:
    """Fill in template placeholders with lead data."""
    first_name = lead.get("first_name") or lead.get("owner_name", "").split()[0] if lead.get("owner_name") else "there"
    company = lead.get("business_name") or lead.get("company", "your company")

    return template.format(
        first_name=first_name,
        company=company,
        email=lead.get("email", ""),
        phone=lead.get("phone", ""),
        website=lead.get("website", ""),
        category=lead.get("category", ""),
    )


def map_field_to_value(field_label: str, lead: dict, message: str) -> str:
    """Map a form field label to the right value from the lead data."""
    label_lower = field_label.lower()

    if any(k in label_lower for k in ["first name", "fname", "first"]):
        name = lead.get("owner_name", "Sabbo")
        return name.split()[0] if name else "Sabbo"
    if any(k in label_lower for k in ["last name", "lname", "last", "surname"]):
        name = lead.get("owner_name", "")
        parts = name.split()
        return parts[-1] if len(parts) > 1 else ""
    if any(k in label_lower for k in ["full name", "your name", "name"]):
        return "Sabbo"
    if any(k in label_lower for k in ["email", "e-mail"]):
        return os.environ.get("OUTREACH_FROM_EMAIL", "hello@247growth.org")
    if any(k in label_lower for k in ["phone", "tel", "mobile"]):
        return os.environ.get("OUTREACH_FROM_PHONE", "")
    if any(k in label_lower for k in ["company", "business", "organization"]):
        return "24/7 Growth"
    if any(k in label_lower for k in ["subject", "topic", "regarding"]):
        return f"Quick question for {lead.get('business_name', 'your team')}"
    if any(k in label_lower for k in ["message", "comment", "details", "inquiry", "how can we help"]):
        return message
    if any(k in label_lower for k in ["website", "url"]):
        return "https://247growth.org"

    return ""


# ── Browser Agent ─────────────────────────────────────────────────────────────

async def process_lead(
    lead: dict,
    message: str,
    browser_context,
    ai_client: anthropic.Anthropic,
    lead_index: int,
    dry_run: bool = False,
) -> dict:
    """Process a single lead: navigate to website → find contact form → fill it out."""
    website = lead.get("website", "")
    if not website:
        return {"lead": lead.get("business_name"), "status": "skipped", "reason": "no website"}

    if not website.startswith("http"):
        website = f"https://{website}"

    result = {
        "lead": lead.get("business_name", "unknown"),
        "website": website,
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
    }

    page = await browser_context.new_page()
    try:
        # Step 1: Navigate to website
        await page.goto(website, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Step 2: Screenshot for AI analysis
        ss_path = SCREENSHOT_DIR / f"lead_{lead_index:04d}_page.png"
        await page.screenshot(path=str(ss_path), full_page=False)

        # Step 3: AI analyzes the page
        analysis = await analyze_page_for_form(ai_client, ss_path)

        # Step 4: If no form, try clicking Contact link
        if not analysis.get("has_contact_form") and analysis.get("contact_page_link"):
            try:
                await page.click(analysis["contact_page_link"], timeout=5000)
                await page.wait_for_timeout(2000)
                ss_path2 = SCREENSHOT_DIR / f"lead_{lead_index:04d}_contact.png"
                await page.screenshot(path=str(ss_path2), full_page=False)
                analysis = await analyze_page_for_form(ai_client, ss_path2)
            except Exception:
                pass

        if not analysis.get("has_contact_form"):
            result["status"] = "no_form"
            result["reason"] = "No contact form found on website"
            return result

        # Step 5: Fill out the form
        fields_filled = 0
        for field in analysis.get("fields", []):
            selector = field.get("selector")
            label = field.get("label", "")
            field_type = field.get("field_type", "text")
            value = map_field_to_value(label, lead, message)

            if not value or not selector:
                continue

            try:
                if field_type == "textarea":
                    await page.fill(selector, value, timeout=3000)
                elif field_type in ("text", "email", "phone"):
                    await page.fill(selector, value, timeout=3000)
                elif field_type == "select":
                    await page.select_option(selector, label=value, timeout=3000)
                fields_filled += 1
            except Exception as e:
                result.setdefault("field_errors", []).append(f"{label}: {str(e)[:100]}")

        result["fields_filled"] = fields_filled

        # Step 6: Submit (or screenshot for dry run)
        if dry_run:
            ss_filled = SCREENSHOT_DIR / f"lead_{lead_index:04d}_filled.png"
            await page.screenshot(path=str(ss_filled), full_page=False)
            result["status"] = "dry_run"
            result["screenshot"] = str(ss_filled)
        else:
            submit_selector = analysis.get("submit_selector")
            if submit_selector and fields_filled > 0:
                try:
                    await page.click(submit_selector, timeout=5000)
                    await page.wait_for_timeout(3000)
                    ss_submitted = SCREENSHOT_DIR / f"lead_{lead_index:04d}_submitted.png"
                    await page.screenshot(path=str(ss_submitted), full_page=False)
                    result["status"] = "submitted"
                    result["screenshot"] = str(ss_submitted)
                except Exception as e:
                    result["status"] = "submit_failed"
                    result["reason"] = str(e)[:200]
            else:
                result["status"] = "no_submit_button"

    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)[:300]
    finally:
        await page.close()

    return result


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_parallel_outreach(
    leads: list[dict],
    message_template: str,
    max_browsers: int = 3,
    dry_run: bool = False,
    headless: bool = True,
) -> list[dict]:
    """Run parallel browser agents across leads."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    ai_client = anthropic.Anthropic()
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        # Process in batches of max_browsers
        for batch_start in range(0, len(leads), max_browsers):
            batch = leads[batch_start:batch_start + max_browsers]
            print(f"  Processing batch {batch_start // max_browsers + 1}: "
                  f"leads {batch_start + 1}-{batch_start + len(batch)} of {len(leads)}")

            # Create a browser context per lead in this batch
            tasks = []
            for i, lead in enumerate(batch):
                idx = batch_start + i
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                )
                message = personalize_message(message_template, lead)
                tasks.append(process_lead(lead, message, context, ai_client, idx, dry_run))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, Exception):
                    results.append({"status": "error", "reason": str(r)[:300]})
                else:
                    results.append(r)

            # Close contexts
            for ctx in browser.contexts:
                await ctx.close()

        await browser.close()

    return results


def load_leads(csv_path: str) -> list[dict]:
    """Load leads from CSV file."""
    leads = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("website"):  # Only leads with websites
                leads.append(dict(row))
    return leads


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parallel browser agent outreach")
    parser.add_argument("--input", required=True, help="Input CSV with leads (must have 'website' column)")
    parser.add_argument("--max-browsers", type=int, default=3, help="Max parallel browsers (default: 3)")
    parser.add_argument("--message-template", default="outreach_intro",
                        help=f"Template name ({', '.join(TEMPLATES.keys())}) or 'custom'")
    parser.add_argument("--message", help="Custom message (use {first_name}, {company} placeholders)")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but don't submit")
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    parser.add_argument("--visible", action="store_true", help="Show browser windows")
    parser.add_argument("--limit", type=int, help="Limit number of leads to process")
    args = parser.parse_args()

    # Load leads
    leads = load_leads(args.input)
    if not leads:
        print("No leads with websites found in CSV", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        leads = leads[:args.limit]

    # Get message template
    if args.message:
        template = args.message
    elif args.message_template in TEMPLATES:
        template = TEMPLATES[args.message_template]
    else:
        print(f"Unknown template: {args.message_template}", file=sys.stderr)
        print(f"Available: {', '.join(TEMPLATES.keys())}", file=sys.stderr)
        sys.exit(1)

    headless = not args.visible

    print(f"Parallel Outreach — {len(leads)} leads, {args.max_browsers} browsers, {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Template: {args.message_template}")

    # Run
    results = asyncio.run(run_parallel_outreach(
        leads=leads,
        message_template=template,
        max_browsers=args.max_browsers,
        dry_run=args.dry_run,
        headless=headless,
    ))

    # Summary
    submitted = sum(1 for r in results if r.get("status") == "submitted")
    dry_runs = sum(1 for r in results if r.get("status") == "dry_run")
    no_form = sum(1 for r in results if r.get("status") == "no_form")
    errors = sum(1 for r in results if r.get("status") in ("error", "submit_failed"))
    skipped = sum(1 for r in results if r.get("status") == "skipped")

    print(f"\n{'='*50}")
    print(f"RESULTS: {submitted} submitted, {dry_runs} dry-run, {no_form} no form, {errors} errors, {skipped} skipped")
    print(f"{'='*50}")

    # Save log
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    log_path = TMP_DIR / f"outreach_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(results, indent=2))
    print(f"Log saved: {log_path}")


if __name__ == "__main__":
    main()
