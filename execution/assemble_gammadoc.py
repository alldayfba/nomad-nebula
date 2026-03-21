"""
assemble_gammadoc.py

Step 3 of the Dream 100 pipeline.

Takes research + assets JSON files and assembles a GammaDoc-ready markdown file.

Correct GammaDoc structure (per Kabrin's framework):
  1. Branded header (their logo + brand colors noted)
  2. System overview (short — what you built and why)
  3. FREE DELIVERABLES (main section — reached fast, all in one block)
     - Meta Ad Hooks (3x)
     - YouTube Ad Script
     - Email Sequence (3 emails)
     - Landing Page Headlines
     - VSL Hook + Problem Section
     - Confirmation Page Copy
  4. Results / Case Studies (proof — "not making this up")
  5. Booking CTA (one action only)

Output: .tmp/gammadoc_<name>_<ts>.md — paste into Gamma.app

Usage:
    python execution/assemble_gammadoc.py \
        --research .tmp/research_Alex_Hormozi_20260220.json \
        --assets .tmp/assets_Alex_Hormozi_20260220.json \
        --prospect-name "Alex Hormozi"

    # Without research file:
    python execution/assemble_gammadoc.py \
        --assets .tmp/assets_Alex_Hormozi_20260220.json \
        --prospect-name "Alex Hormozi" \
        --their-offer "high-ticket business programs"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ─── Case studies from your own results (update these as you get more) ─────────
YOUR_CASE_STUDIES = [
    {
        "client_type": "Online coaching client",
        "before": "36% show rate on sales calls",
        "after": "72-80% show rate after implementing confirmation page nurture sequence",
        "timeframe": "30 days",
    },
    {
        "client_type": "Info product business",
        "before": "Cold traffic converting at 0.8% on VSL page",
        "after": "2.4% conversion after rewriting hook and problem section",
        "timeframe": "2 weeks",
    },
]

YOUR_BOOKING_LINK = "https://cal.com/[YOUR-LINK]"  # Update this


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    return json.loads(p.read_text())


def get_brand_note(research: dict | None) -> str:
    """Generate a brand-matching note for the GammaDoc header."""
    if not research:
        return ""
    brand = research.get("brand", {})
    colors = brand.get("colors", [])
    logo = brand.get("logo_url", "")
    lines = []
    if logo:
        lines.append(f"> **Logo:** {logo}")
    if colors:
        lines.append(f"> **Brand colors:** {', '.join(colors[:4])}")
    if lines:
        return "\n".join(["> *[When building in Gamma: match these brand elements]*"] + lines)
    return ""


def format_meta_hooks(hooks: list) -> str:
    if not hooks or isinstance(hooks, dict) and "error" in hooks:
        return "_Meta ad hooks not generated._"
    lines = []
    for h in hooks:
        lines.append(f"**Hook {h.get('hook_number', '?')} — {h.get('formula', '')}**")
        lines.append(f"> {h.get('hook_text', '')}")
        lines.append(f"*Why it works: {h.get('why_it_works', '')}*")
        lines.append("")
    return "\n".join(lines)


def format_youtube_ad(ad: dict) -> str:
    if not ad or "error" in ad:
        return "_YouTube ad not generated._"
    return f"""**Full Script:**

> {ad.get('full_script', '').replace(chr(10), chr(10) + '> ')}

---
*Estimated runtime: ~{ad.get('estimated_runtime_seconds', 75)} seconds*"""


def format_email_sequence(emails: list) -> str:
    if not emails or (isinstance(emails, dict) and "error" in emails):
        return "_Email sequence not generated._"
    lines = []
    for e in emails:
        lines.append(f"**Email {e.get('email_number', '?')} — Send: {e.get('send_timing', '')}**")
        lines.append(f"Subject: `{e.get('subject', '')}`")
        lines.append(f"Preview: *{e.get('preview_text', '')}*")
        lines.append("")
        lines.append(e.get("body", ""))
        lines.append("")
        lines.append(f"**CTA:** {e.get('cta', '')}")
        ps = e.get("ps_line", "")
        if ps:
            lines.append(f"**P.S.** {ps}")
        lines.append("\n---\n")
    return "\n".join(lines)


def format_headlines(headlines: list) -> str:
    if not headlines or (isinstance(headlines, dict) and "error" in headlines):
        return "_Headlines not generated._"
    lines = []
    for h in headlines:
        lines.append(f"**Option {h.get('option', '?')} — {h.get('angle', '')}**")
        lines.append(f"# {h.get('headline', '')}")
        lines.append(f"*{h.get('subheadline', '')}*")
        lines.append("")
    return "\n".join(lines)


def format_vsl_hook(vsl: dict) -> str:
    if not vsl or "error" in vsl:
        return "_VSL hook not generated._"
    sections = []
    for section_key in ["hook", "problem", "agitation"]:
        s = vsl.get(section_key, {})
        if s:
            ts = s.get("timestamp", "")
            script = s.get("script", "")
            label = section_key.upper()
            sections.append(f"**{label}** _{ts}_\n\n> {script}")
    return "\n\n---\n\n".join(sections)


def format_confirmation_page(page: dict) -> str:
    if not page or "error" in page:
        return "_Confirmation page not generated._"
    bullets = "\n".join(f"- {b}" for b in page.get("what_to_expect", []))
    return f"""**Headline:** {page.get('headline', '')}

**Subheadline:** {page.get('subheadline', '')}

**What to expect on the call:**
{bullets}

**Before the call:** {page.get('before_the_call', '')}

**One thing to do right now:** {page.get('micro_commitment_cta', '')}

**{page.get('reminder_copy', '')}**

_P.S. {page.get('ps_line', '')}_"""


def format_case_studies() -> str:
    lines = []
    for i, cs in enumerate(YOUR_CASE_STUDIES, 1):
        lines.append(f"**Result {i} — {cs['client_type']}**")
        lines.append(f"Before: {cs['before']}")
        lines.append(f"After: {cs['after']}")
        lines.append(f"Timeframe: {cs['timeframe']}")
        lines.append("")
    return "\n".join(lines)


def assemble(
    prospect_name: str,
    their_offer: str,
    research: dict | None,
    assets: dict,
) -> str:
    """Build the full GammaDoc markdown string."""

    brand_note = get_brand_note(research)
    gaps = []
    if research:
        gaps = research.get("analysis", {}).get("marketing_gaps", [])

    # Pull assets
    meta_hooks = assets.get("meta_ad_hooks", [])
    youtube_ad = assets.get("youtube_ad", {})
    email_seq = assets.get("email_sequence", [])
    headlines = assets.get("landing_page_headlines", [])
    vsl_hook = assets.get("vsl_hook", {})
    confirmation = assets.get("confirmation_page", {})

    gap_summary = ""
    if gaps:
        gap_lines = [f"- **{g.get('gap')}:** {g.get('why_it_hurts')}" for g in gaps[:3]]
        gap_summary = "\n".join(gap_lines)

    doc = f"""# Built Exclusively for {prospect_name}

{brand_note}

---

## What We Built & Why

{their_offer} is a strong offer. After spending time reviewing your current setup, we spotted a few gaps that are likely leaving real revenue on the table:

{gap_summary if gap_summary else "_(gaps identified from website research)_"}

We built everything below to address these gaps directly. You can take any of these assets and implement them into your business within the next 72 hours.

No pitch. Just the work.

---

## Your Free Deliverables

> *Everything below was built specifically for your business. Take it, use it, implement it.*

---

### Meta Ad Hooks (3x) — Ready to Record

These hooks are written for talking-head or UGC-style Meta ads targeting your audience. Use them as openers for new ad creative.

{format_meta_hooks(meta_hooks)}

---

### YouTube Pre-Roll Ad Script

A full 60-75 second pre-roll script for YouTube ads. Written to hook before the skip button appears (first 5 seconds are critical).

{format_youtube_ad(youtube_ad)}

---

### Email Welcome Sequence (3 Emails)

Drop these into your email platform as an automated sequence after someone opts in. Built to convert subscribers into buyers.

{format_email_sequence(email_seq)}

---

### Landing Page Headlines (5 Options)

Five tested headline frameworks for your main offer page. Each uses a different conversion angle. A/B test 2 of them.

{format_headlines(headlines)}

---

### VSL Hook + Problem Section

The opening 2.5 minutes of a VSL is where 80% of viewers drop off. This is the section we rewrote for your offer.

{format_vsl_hook(vsl_hook)}

---

### Confirmation Page Copy

Most funnels have a broken confirmation page. This is why show rates average 36% industry-wide. Implement this and expect 70-80%+.

{format_confirmation_page(confirmation)}

---

## Results — Not Making These Up

{format_case_studies()}

---

## Ready to Implement All of This in 72 Hours?

Everything above can be live in your business within 3 days.

If you want us to handle the implementation — not just hand you assets but actually plug everything in — we can do that for a one-time fee. No retainer commitment. Just see the work.

[**Book a 15-Minute Call →**]({YOUR_BOOKING_LINK})

*We'll show you exactly how each asset fits into your current funnel and what to expect from implementing it.*

---

_Built by [Your Name/Agency] — {datetime.now().strftime('%B %Y')}_
"""

    return doc.strip()


def save_output(content: str, name: str) -> str:
    tmp = Path(".tmp")
    tmp.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^\w]", "_", name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = tmp / f"gammadoc_{safe_name}_{ts}.md"
    path.write_text(content)
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Assemble a GammaDoc from research + assets")
    parser.add_argument("--assets", required=True, help="Path to assets JSON from generate_dream100_assets.py")
    parser.add_argument("--research", help="Path to research JSON from research_prospect.py (optional)")
    parser.add_argument("--prospect-name", required=True, help="Prospect name")
    parser.add_argument("--their-offer", help="Their offer description (overrides research file)")
    args = parser.parse_args()

    print(f"\n[dream100] Assembling GammaDoc for: {args.prospect_name}\n")

    assets = load_json(args.assets)
    research = load_json(args.research) if args.research else None

    # Resolve offer description
    their_offer = args.their_offer
    if not their_offer and research:
        their_offer = research.get("offer", "your business")
    if not their_offer:
        their_offer = "your business"

    doc = assemble(
        prospect_name=args.prospect_name,
        their_offer=their_offer,
        research=research,
        assets=assets,
    )

    output_path = save_output(doc, args.prospect_name)

    print(f"✓ GammaDoc assembled: {output_path}")
    print(f"\nWord count: ~{len(doc.split())} words")
    print(f"\nNext steps:")
    print(f"  1. Open {output_path}")
    print(f"  2. Paste into Gamma.app (gamma.app/new)")
    print(f"  3. Match their brand colors + add their logo to the header")
    print(f"  4. Turn on open tracking in Gamma settings")
    print(f"  5. Publish → send the link")
    print(f"\nRemember: Update YOUR_BOOKING_LINK in assemble_gammadoc.py before sending.")


if __name__ == "__main__":
    main()
