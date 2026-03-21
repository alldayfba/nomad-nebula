#!/usr/bin/env python3
"""
Script: generate_business_audit.py

Generates a complete Instant Business Audit package for a prospect:
  1. Research their website (scrape + Claude analysis)
  2. Generate 1-page audit document (markdown → Google Doc)
  3. Generate personalized landing page (HTML → Google Drive)
  4. Generate 3 ad angles (Meta-style)
  5. Generate personalized outreach message
  6. Upload all to a named Google Drive folder
  7. Return shareable folder link

Usage (CLI):
    python execution/generate_business_audit.py \
        --name "Blue Wave Dental" \
        --website "https://example.com" \
        --category "Dental Practice" \
        --phone "(305) 555-1234" \
        --address "Miami, FL" \
        --rating "4.2" \
        --owner "Dr. Smith"

Usage (as module from Flask):
    from execution.generate_business_audit import run_audit
    result = run_audit(business_dict, progress_cb=None)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
TMP_DIR = BASE_DIR / ".tmp"

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

_MODEL = "claude-sonnet-4-6"
_PRICING = {
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
}

# ── Agency Config (update these) ─────────────────────────────────────────────

AGENCY = {
    "name": "Your Agency",
    "offer": "Done-For-You growth operating system",
    "promise": "Install a full-stack growth system in 30 days and run it month-over-month",
    "retainer": "$5K–$25K/mo",
    "differentiator": "Operators embedded in your business — not an account manager and a junior team",
    "cal_link": "https://cal.com/your-link",
    "from_name": "Nick",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

TOTAL_STEPS = 7


def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000


# ── Step 1: Website Research ──────────────────────────────────────────────────

def fetch_and_parse(url: str) -> dict:
    """Fetch website and extract key signals. Returns {'ok': False} on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "noscript", "meta", "link"]):
            tag.decompose()

        lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
        page_text = "\n".join(lines[:300])

        title = (soup.find("title") or soup.new_tag("x")).get_text(strip=True)
        desc_tag = soup.find("meta", {"name": "description"})
        description = desc_tag.get("content", "") if desc_tag else ""

        cta_texts = []
        for el in soup.find_all(["button", "a"], class_=re.compile(r"btn|cta|button", re.I)):
            t = el.get_text(strip=True)
            if t and 2 < len(t) < 80:
                cta_texts.append(t)
        cta_texts = list(dict.fromkeys(cta_texts))[:8]

        social_doms = [
            "instagram.com", "facebook.com", "youtube.com",
            "twitter.com", "x.com", "tiktok.com", "linkedin.com"
        ]
        socials = list({
            a["href"] for a in soup.find_all("a", href=True)
            if any(d in a["href"] for d in social_doms)
        })

        hex_pat = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
        skip = {"#FFFFFF", "#000000", "#FEFEFE", "#010101", "#FFFFFE", "#010100"}
        colors, seen = [], set()
        for h in hex_pat.findall(html):
            c = f"#{(h * 2 if len(h) == 3 else h).upper()}"
            if c not in seen and c not in skip:
                seen.add(c)
                colors.append(c)

        return {
            "ok": True,
            "page_text": page_text[:5000],
            "title": title,
            "description": description,
            "cta_buttons": cta_texts,
            "social_links": socials,
            "brand_colors": colors[:6],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Step 2: Claude Analysis ───────────────────────────────────────────────────

def analyze_business(business: dict, web_data: dict) -> tuple[dict, object]:
    """Use Claude Sonnet to identify marketing gaps and opportunities."""
    if web_data.get("ok"):
        page_content = (
            f"Page Title: {web_data.get('title', 'N/A')}\n"
            f"Meta Description: {web_data.get('description', 'N/A')}\n"
            f"CTAs Found: {', '.join(web_data.get('cta_buttons', [])) or 'None'}\n"
            f"Social Links: {', '.join(web_data.get('social_links', [])) or 'None'}\n\n"
            f"Page Text (excerpt):\n{web_data.get('page_text', '')[:3500]}"
        )
    else:
        page_content = f"Website unavailable: {web_data.get('error', 'No website provided')}"

    prompt = f"""You are a senior growth marketing analyst at a top agency. Analyze this business.

PROSPECT:
- Business: {business.get('business_name', 'Unknown')}
- Industry: {business.get('category', 'Unknown')}
- Location: {business.get('address', 'Unknown')}
- Rating: {business.get('rating', 'N/A')} stars on Google
- Website: {business.get('website', 'None provided')}
- Phone: {business.get('phone', 'N/A')}

WEBSITE DATA:
{page_content}

Return ONLY valid JSON (no markdown fences):
{{
  "funnel_type": "one of: vsl | webinar | application | direct_sales | lead_magnet | brochure_site | no_website | none_detected",
  "current_offer": "1-2 sentence summary of what they sell and how",
  "primary_cta": "main action they want visitors to take",
  "social_proof": ["list", "of", "social proof signals found"],
  "active_platforms": ["platforms from social links or site content"],
  "marketing_gaps": [
    {{"gap": "short gap name", "why_it_hurts": "specific revenue/conversion impact", "fix": "what you'd build to fix it"}}
  ],
  "pain_summary": "2-3 sentences on what problems this owner is likely experiencing",
  "quick_wins": ["top 3 things implementable in under 72 hours for immediate impact"],
  "revenue_opportunity": "1-2 sentences estimating what fixing these gaps could unlock for them",
  "estimated_revenue_stage": "one of: under $1M | $1M-$3M | $3M-$10M | $10M+"
}}"""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content[0].text.strip())
    return json.loads(raw), resp.usage


# ── Step 3: Audit Document ────────────────────────────────────────────────────

def generate_audit_doc(business: dict, analysis: dict) -> tuple[str, object]:
    """Generate a 1-page business audit in markdown."""
    gaps = analysis.get("marketing_gaps", [])[:3]
    gaps_text = "\n\n".join(
        f"### {i+1}. {g['gap']}\n"
        f"**Impact:** {g['why_it_hurts']}\n\n"
        f"**What we'd fix:** {g['fix']}"
        for i, g in enumerate(gaps)
    )
    quick_wins = "\n".join(f"{i+1}. {w}" for i, w in enumerate(analysis.get("quick_wins", [])[:3]))

    prompt = f"""Write a professional 1-page business growth audit for this prospect.

BUSINESS:
- Name: {business.get('business_name')}
- Industry: {business.get('category', 'N/A')}
- Location: {business.get('address', 'N/A')}
- Rating: {business.get('rating', 'N/A')} ⭐ on Google
- Website: {business.get('website', 'N/A')}

ANALYSIS FINDINGS:
- Funnel type: {analysis.get('funnel_type')}
- Current offer: {analysis.get('current_offer')}
- Primary CTA: {analysis.get('primary_cta')}
- Social proof: {', '.join(analysis.get('social_proof', [])) or 'Limited/none detected'}
- Active platforms: {', '.join(analysis.get('active_platforms', [])) or 'Unknown'}
- Estimated revenue stage: {analysis.get('estimated_revenue_stage', 'N/A')}
- Pain summary: {analysis.get('pain_summary')}
- Revenue opportunity: {analysis.get('revenue_opportunity')}

GAPS FOUND:
{gaps_text}

QUICK WINS:
{quick_wins}

AGENCY:
- Name: {AGENCY['name']}
- Offer: {AGENCY['offer']}
- Promise: {AGENCY['promise']}
- Differentiator: {AGENCY['differentiator']}
- Retainer: {AGENCY['retainer']}
- Book a call: {AGENCY['cal_link']}

Write a compelling, specific, personalized 1-page audit. Rules:
- Use their actual business name, industry, and specifics throughout
- Be direct and honest — this is what we actually found, not generic advice
- Position the agency as the obvious solution without being salesy
- 500-700 words total
- End with a soft, high-converting CTA to book a free strategy call

Format with these exact sections using markdown:
# [Business Name] — Free Growth Audit
(prepared by line + date)

## Executive Summary
## Current Marketing Assessment
## Growth Gaps We Found
## Quick Wins (72 Hours)
## Revenue Opportunity
## What We'd Build For You
## Ready to See Your Full Growth Plan?

Write the audit now. Return only the markdown — no commentary."""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip(), resp.usage


# ── Step 4: Landing Page ──────────────────────────────────────────────────────

def generate_landing_page(business: dict, analysis: dict) -> tuple[str, object]:
    """Generate a personalized HTML landing page for the prospect."""
    biz_name = business.get("business_name", "Your Business")
    gaps = analysis.get("marketing_gaps", [])[:3]
    gap_items = "".join(
        f"<li><strong>{g['gap']}</strong> — {g['why_it_hurts']}</li>"
        for g in gaps
    )

    prompt = f"""Generate a complete, self-contained HTML landing page for a personalized business audit delivery.

DETAILS:
- Prospect business: {biz_name}
- Industry: {business.get('category', 'business')}
- Location: {business.get('address', '')}
- Agency name: {AGENCY['name']}
- Agency promise: {AGENCY['promise']}
- Book a call link: {AGENCY['cal_link']}
- Revenue opportunity: {analysis.get('revenue_opportunity', '')}

TOP GAPS FOUND (show these on the page):
{chr(10).join(f"- {g['gap']}: {g['why_it_hurts']}" for g in gaps)}

REQUIREMENTS:
- Headline: "We audited {biz_name}. Here's what we found."
- Subheadline referencing their industry and the opportunity
- A "What We Found" section listing the 3 gaps as cards or list items
- A prominent CTA button: "Book Your Free Strategy Call" linking to {AGENCY['cal_link']}
- Agency credibility line at the bottom
- Modern, professional design — dark background (#0a0f1e), white text, purple accent (#7c3aed)
- Use Inter font from Google Fonts
- Fully mobile-responsive with embedded CSS only (no external CSS files)
- No JavaScript required
- Single HTML file, complete and valid

Return ONLY the complete HTML. No markdown fences, no commentary."""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    html = resp.content[0].text.strip()
    # Strip markdown fences if Claude wraps it
    html = re.sub(r"^```(?:html)?\s*", "", html)
    html = re.sub(r"\s*```$", "", html)
    return html, resp.usage


# ── Step 5: Ad Angles ─────────────────────────────────────────────────────────

def generate_ad_angles(business: dict, analysis: dict) -> tuple[list, object]:
    """Generate 3 distinct Meta ad angles targeting this prospect's niche."""
    prompt = f"""You are a direct response copywriter for a growth marketing agency.

TARGET NICHE: {business.get('category', 'business owners')}
LOCATION: {business.get('address', 'USA')}
OWNER PAIN: {analysis.get('pain_summary', '')}
REVENUE OPPORTUNITY: {analysis.get('revenue_opportunity', '')}

AGENCY:
- Offer: {AGENCY['offer']}
- Promise: {AGENCY['promise']}
- Retainer: {AGENCY['retainer']}
- Differentiator: {AGENCY['differentiator']}

Write 3 distinct Meta ad angles. Different psychological approach each:
1. PAIN — agitate the specific frustration they're feeling RIGHT NOW
2. OPPORTUNITY — paint the picture of what becomes possible
3. CREDIBILITY — use authority and proof to earn trust fast

For each angle:
- Hook: first 2-3 seconds, stops the scroll, pattern interrupt
- Body: 30-45 seconds of spoken content (3-4 punchy sentences)
- CTA: exact closing call to action

Return ONLY valid JSON — no markdown fences:
[
  {{
    "angle": "Pain",
    "emotion": "frustration | fear of loss",
    "hook": "...",
    "body": "...",
    "cta": "..."
  }},
  {{
    "angle": "Opportunity",
    "emotion": "desire | aspiration",
    "hook": "...",
    "body": "...",
    "cta": "..."
  }},
  {{
    "angle": "Credibility",
    "emotion": "trust | confidence",
    "hook": "...",
    "body": "...",
    "cta": "..."
  }}
]"""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content[0].text.strip())
    return json.loads(raw), resp.usage


# ── Step 6: Outreach Message ──────────────────────────────────────────────────

def generate_outreach(business: dict, analysis: dict) -> tuple[str, object]:
    """Generate a personalized cold outreach email."""
    owner = business.get("owner_name", "") or ""
    first_name = owner.split()[0] if owner and owner not in ("N/A", "") else "there"
    gaps = analysis.get("marketing_gaps", [])[:2]
    gap_bullets = "\n".join(f"• {g['gap']}: {g['why_it_hurts']}" for g in gaps)

    prompt = f"""Write a personalized cold outreach email for this prospect.

PROSPECT:
- Business: {business.get('business_name')}
- Owner first name: {first_name}
- Industry: {business.get('category', 'N/A')}
- Location: {business.get('address', 'N/A')}
- Google Rating: {business.get('rating', 'N/A')} stars

TOP GAPS WE FOUND IN THEIR AUDIT:
{gap_bullets}

REVENUE OPPORTUNITY: {analysis.get('revenue_opportunity', '')}

AGENCY:
- Sender: {AGENCY['from_name']} from {AGENCY['name']}
- Offer: {AGENCY['offer']}
- Promise: {AGENCY['promise']}
- Book a call: {AGENCY['cal_link']}

RULES:
- 150-200 words max (short and punchy)
- Include a subject line at the top (format: Subject: ...)
- Open with a specific, genuine observation about THEIR business (not generic)
- Reference 2 specific gaps you found — make it feel like real research
- Tease the audit: "I put together a full audit for [Business Name]"
- Use [DRIVE_LINK] as a placeholder for the Drive folder link
- Soft CTA — offer the audit + a 15-min call, not a sales pitch
- Sound like a human, not a marketing email

Return only the email text (subject + body). No commentary."""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip(), resp.usage


# ── Step 7: Google Drive Upload ───────────────────────────────────────────────

def upload_to_drive(folder_name: str, files: list) -> dict:
    """
    Upload files to a new Google Drive folder.
    files: list of {name, path, mime} dicts
    Returns: {ok, folder_url, files: [{name, url}]} or {ok: False, error}
    """
    sa_file = BASE_DIR / "service_account.json"
    if not sa_file.exists():
        return {"ok": False, "error": "service_account.json not found — Drive upload skipped"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            str(sa_file),
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        drive = build("drive", "v3", credentials=creds)

        folder = drive.files().create(
            body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        ).execute()
        folder_id = folder["id"]

        drive.permissions().create(
            fileId=folder_id,
            body={"type": "anyone", "role": "writer"},
        ).execute()

        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        file_urls = []

        for f in files:
            path = Path(f["path"])
            if not path.exists():
                continue
            mime = f.get("mime", "text/plain")
            body = {"name": f["name"], "parents": [folder_id]}

            # Convert markdown/text → Google Doc
            if mime in ("text/plain", "text/markdown"):
                body["mimeType"] = "application/vnd.google-apps.document"

            media = MediaFileUpload(str(path), mimetype=mime, resumable=False)
            created = drive.files().create(
                body=body, media_body=media, fields="id,webViewLink"
            ).execute()
            url = created.get("webViewLink", f"https://drive.google.com/file/d/{created['id']}/view")
            file_urls.append({"name": f["name"], "url": url})

        return {"ok": True, "folder_url": folder_url, "files": file_urls}

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Main Orchestrator ─────────────────────────────────────────────────────────

def run_audit(business: dict, progress_cb=None) -> dict:
    """
    Run the full audit pipeline.

    Args:
        business: dict with keys: business_name, website, category, phone, address, rating, owner_name
        progress_cb: callable(step: int, total: int, message: str) — optional

    Returns dict with:
        ok, folder_url, files, audit_md, ad_angles, outreach,
        analysis, total_cost_usd, total_tokens, local_dir
        (or ok=False, error on failure)
    """

    def progress(step: int, msg: str):
        if progress_cb:
            progress_cb(step, TOTAL_STEPS, msg)

    total_tokens = {"input": 0, "output": 0}

    def track(usage):
        total_tokens["input"] += usage.input_tokens
        total_tokens["output"] += usage.output_tokens

    biz_name = business.get("business_name", "Business")
    safe_name = re.sub(r"[^\w]", "_", biz_name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_dir = TMP_DIR / f"audit_{safe_name}_{ts}"
    audit_dir.mkdir(parents=True, exist_ok=True)

    # 1 — Research website
    progress(1, f"Fetching {business.get('website', 'website')}...")
    web_data = {}
    website = business.get("website", "")
    if website and website not in ("N/A", ""):
        web_data = fetch_and_parse(website)

    # 2 — Analyze
    progress(2, "Analyzing marketing gaps with Claude...")
    try:
        analysis, usage = analyze_business(business, web_data)
        track(usage)
    except Exception as e:
        return {"ok": False, "error": f"Analysis failed: {e}"}

    # 3 — Audit doc
    progress(3, "Writing 1-page audit document...")
    try:
        audit_md, usage = generate_audit_doc(business, analysis)
        track(usage)
        audit_path = audit_dir / "audit.md"
        audit_path.write_text(audit_md)
    except Exception as e:
        return {"ok": False, "error": f"Audit doc generation failed: {e}"}

    # 4 — Landing page
    progress(4, "Building personalized landing page...")
    landing_path = None
    try:
        landing_html, usage = generate_landing_page(business, analysis)
        track(usage)
        landing_path = audit_dir / "landing.html"
        landing_path.write_text(landing_html)
    except Exception as e:
        landing_html = ""

    # 5 — Ad angles
    progress(5, "Drafting 3 ad angles...")
    ad_angles = []
    angles_path = None
    try:
        ad_angles, usage = generate_ad_angles(business, analysis)
        track(usage)
        angles_path = audit_dir / "ad_angles.json"
        angles_path.write_text(json.dumps(ad_angles, indent=2))
    except Exception as e:
        pass

    # 6 — Outreach message
    progress(6, "Writing personalized outreach message...")
    outreach = ""
    outreach_path = None
    try:
        outreach, usage = generate_outreach(business, analysis)
        track(usage)
        outreach_path = audit_dir / "outreach.md"
        outreach_path.write_text(outreach)
    except Exception as e:
        pass

    # 7 — Upload to Drive
    progress(7, "Uploading to Google Drive...")
    files_to_upload = [
        {"name": f"{biz_name} — Growth Audit", "path": str(audit_path), "mime": "text/plain"},
    ]
    if landing_path and landing_path.exists():
        files_to_upload.append({
            "name": "Personalized Landing Page",
            "path": str(landing_path),
            "mime": "text/html",
        })
    if angles_path and angles_path.exists():
        files_to_upload.append({
            "name": "Ad Angles (3x Meta)",
            "path": str(angles_path),
            "mime": "text/plain",
        })
    if outreach_path and outreach_path.exists():
        files_to_upload.append({
            "name": "Personalized Outreach Email",
            "path": str(outreach_path),
            "mime": "text/plain",
        })

    folder_name = f"Audit — {biz_name}"
    drive_result = upload_to_drive(folder_name, files_to_upload)

    total_cost = _cost(_MODEL, total_tokens["input"], total_tokens["output"])

    result = {
        "ok": True,
        "business_name": biz_name,
        "analysis": analysis,
        "audit_md": audit_md,
        "ad_angles": ad_angles,
        "outreach": outreach,
        "local_dir": str(audit_dir),
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
    }

    if drive_result.get("ok"):
        result["folder_url"] = drive_result["folder_url"]
        result["files"] = drive_result["files"]
    else:
        result["folder_url"] = None
        result["files"] = []
        result["drive_error"] = drive_result.get("error", "Drive upload failed")

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate a full business audit package")
    parser.add_argument("--name", required=True)
    parser.add_argument("--website", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--address", default="")
    parser.add_argument("--rating", default="")
    parser.add_argument("--owner", default="")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    business = {
        "business_name": args.name,
        "website": args.website,
        "category": args.category,
        "phone": args.phone,
        "address": args.address,
        "rating": args.rating,
        "owner_name": args.owner,
    }

    def progress_cb(step, total, msg):
        print(f"[{step}/{total}] {msg}")

    print(f"\n[audit] Generating audit package for: {args.name}\n")
    result = run_audit(business, progress_cb=progress_cb)

    if not result["ok"]:
        print(f"\nERROR: {result['error']}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"AUDIT COMPLETE — {args.name}")
    print(f"{'=' * 60}")
    print(f"Local files: {result['local_dir']}")
    if result.get("folder_url"):
        print(f"Drive folder: {result['folder_url']}")
        for f in result.get("files", []):
            print(f"  {f['name']}: {f['url']}")
    else:
        print(f"Drive: {result.get('drive_error', 'skipped')}")
    print(f"\nCost: ${result['total_cost_usd']:.4f} [{_MODEL}]")
    print(f"Tokens: {result['total_tokens']['input']:,} in / {result['total_tokens']['output']:,} out")
    print(f"Ad angles: {len(result.get('ad_angles', []))}")


if __name__ == "__main__":
    main()
