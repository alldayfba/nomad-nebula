"""
research_prospect.py

Step 1 of the Dream 100 pipeline.

Scrapes a prospect's website to extract:
- Current offer / CTA
- Funnel type (VSL, webinar, application, direct, none)
- Brand colors (hex codes)
- Logo URL
- Social proof signals
- Marketing gaps (missing assets)
- Key copy/headlines

Outputs JSON to .tmp/research_<name>_<ts>.json

Usage:
    python execution/research_prospect.py \
        --name "Alex Hormozi" \
        --website "https://acquisition.com" \
        --niche "business education" \
        --offer "high-ticket business programs"
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Research/analysis → Sonnet
_MODEL = "claude-sonnet-4-6"
_PRICING = {"claude-haiku-4-5-20251001": (0.25, 1.25), "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-6": (15.0, 75.0)}

def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

TIMEOUT = 15


def fetch_page(url: str) -> tuple[str, str]:
    """Fetch a URL, return (html, final_url). Raises on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, resp.url
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e


def extract_text_content(soup: BeautifulSoup) -> str:
    """Extract visible text from page, stripping nav/footer noise."""
    for tag in soup(["script", "style", "nav", "footer", "noscript", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:300])  # Cap at 300 lines to keep token count sane


def extract_colors(html: str) -> list[str]:
    """Pull hex color codes from inline CSS and style blocks."""
    hex_pattern = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
    found = hex_pattern.findall(html)
    # Normalize 3-char hex to 6-char
    normalized = []
    for h in found:
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        normalized.append(f"#{h.upper()}")
    # Deduplicate while preserving order, skip near-white/near-black generics
    skip = {"#FFFFFF", "#000000", "#FEFEFE", "#010101", "#FFF", "#000"}
    seen = set()
    colors = []
    for c in normalized:
        if c not in seen and c not in skip:
            seen.add(c)
            colors.append(c)
    return colors[:8]  # Top 8 brand colors


def extract_logo(soup: BeautifulSoup, base_url: str) -> str:
    """Try to find a logo image URL."""
    candidates = [
        soup.find("img", {"class": re.compile(r"logo", re.I)}),
        soup.find("img", {"id": re.compile(r"logo", re.I)}),
        soup.find("img", {"alt": re.compile(r"logo", re.I)}),
        soup.find("header", {}) and soup.find("header").find("img") if soup.find("header") else None,
    ]
    for img in candidates:
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("http"):
                return src
            return urljoin(base_url, src)
    return ""


def extract_meta(soup: BeautifulSoup) -> dict:
    """Extract title, description, og tags."""
    data = {}
    title = soup.find("title")
    data["title"] = title.get_text(strip=True) if title else ""

    desc = soup.find("meta", {"name": "description"})
    data["description"] = desc.get("content", "") if desc else ""

    og_title = soup.find("meta", {"property": "og:title"})
    data["og_title"] = og_title.get("content", "") if og_title else ""

    og_desc = soup.find("meta", {"property": "og:description"})
    data["og_description"] = og_desc.get("content", "") if og_desc else ""

    return data


def extract_social_links(soup: BeautifulSoup) -> list[str]:
    """Find social media links on the page."""
    social_domains = ["instagram.com", "facebook.com", "youtube.com", "twitter.com", "x.com", "tiktok.com", "linkedin.com"]
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href for d in social_domains):
            links.append(href)
    return list(set(links))


def extract_cta_buttons(soup: BeautifulSoup) -> list[str]:
    """Extract text from buttons and prominent CTA links."""
    cta_texts = []
    for btn in soup.find_all(["button", "a"], class_=re.compile(r"btn|cta|button", re.I)):
        text = btn.get_text(strip=True)
        if text and 2 < len(text) < 80:
            cta_texts.append(text)
    # Also check input[type=submit]
    for inp in soup.find_all("input", {"type": "submit"}):
        val = inp.get("value", "").strip()
        if val:
            cta_texts.append(val)
    return list(dict.fromkeys(cta_texts))[:10]


def analyze_with_claude(
    prospect_name: str,
    niche: str,
    offer: str,
    page_text: str,
    meta: dict,
    cta_buttons: list[str],
    social_links: list[str],
) -> dict:
    """Use Claude to analyze the scraped data and identify gaps."""

    prompt = f"""You are a growth marketing analyst. Analyze this prospect's website data and provide a structured breakdown.

PROSPECT: {prospect_name}
NICHE: {niche}
KNOWN OFFER: {offer}

PAGE TEXT (first 200 lines):
{page_text[:6000]}

PAGE TITLE: {meta.get('title', 'N/A')}
META DESCRIPTION: {meta.get('description', 'N/A')}
CTA BUTTONS FOUND: {', '.join(cta_buttons) or 'None detected'}
SOCIAL LINKS: {', '.join(social_links) or 'None detected'}

Analyze this and return a JSON object with these exact keys:

{{
  "funnel_type": "one of: vsl | webinar | application | direct_sales | lead_magnet | none_detected",
  "current_offer_summary": "1-2 sentence description of what they're selling and at what level",
  "primary_cta": "the main action they want visitors to take",
  "social_proof_signals": ["list", "of", "what", "social", "proof", "they", "have"],
  "marketing_gaps": [
    {{
      "gap": "short name of the gap",
      "why_it_hurts": "1 sentence on what revenue/conversion they're losing",
      "deliverable_fix": "what you'd build for them to fix it"
    }}
  ],
  "prospect_pain_summary": "2-3 sentences on what problems they're likely experiencing based on their funnel and offer",
  "platforms_active_on": ["list", "of", "platforms", "based", "on", "social", "links"],
  "quick_wins": ["top 2-3 things they could implement in under 72 hours for immediate impact"]
}}

Return ONLY the JSON. No markdown fences. No commentary."""

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw), resp.usage


def save_output(data: dict, name: str) -> str:
    """Save research JSON to .tmp/ and return the path."""
    tmp = Path(".tmp")
    tmp.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^\w]", "_", name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = tmp / f"research_{safe_name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Research a Dream 100 prospect's website")
    parser.add_argument("--name", required=True, help="Prospect or business name")
    parser.add_argument("--website", required=True, help="Their website URL")
    parser.add_argument("--niche", required=True, help="Their niche/industry")
    parser.add_argument("--offer", required=True, help="What they sell (known from research)")
    args = parser.parse_args()

    print(f"\n[dream100] Researching: {args.name} ({args.website})\n")

    # --- Fetch ---
    print("[1/4] Fetching website...")
    try:
        html, final_url = fetch_page(args.website)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        print("Tip: If site blocks scrapers, manually provide --gaps to generate_dream100_assets.py")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    # --- Extract ---
    print("[2/4] Extracting signals...")
    meta = extract_meta(soup)
    colors = extract_colors(html)
    logo_url = extract_logo(soup, final_url)
    cta_buttons = extract_cta_buttons(soup)
    social_links = extract_social_links(soup)
    page_text = extract_text_content(soup)

    print(f"    Colors found: {len(colors)}")
    print(f"    Logo URL: {logo_url or 'not found'}")
    print(f"    CTAs found: {len(cta_buttons)}")
    print(f"    Social links: {len(social_links)}")

    # --- Analyze ---
    print("[3/4] Analyzing with Claude (identifying gaps)...")
    try:
        analysis, usage = analyze_with_claude(
            prospect_name=args.name,
            niche=args.niche,
            offer=args.offer,
            page_text=page_text,
            meta=meta,
            cta_buttons=cta_buttons,
            social_links=social_links,
        )
    except (json.JSONDecodeError, Exception) as e:
        print(f"ERROR: Claude analysis failed — {e}")
        sys.exit(1)

    # --- Assemble full research object ---
    research = {
        "prospect_name": args.name,
        "website": args.website,
        "final_url": final_url,
        "niche": args.niche,
        "offer": args.offer,
        "brand": {
            "colors": colors,
            "logo_url": logo_url,
        },
        "meta": meta,
        "cta_buttons": cta_buttons,
        "social_links": social_links,
        "analysis": analysis,
        "researched_at": datetime.now().isoformat(),
    }

    # --- Save ---
    print("[4/4] Saving research...")
    output_path = save_output(research, args.name)

    usd = _cost(_MODEL, usage.input_tokens, usage.output_tokens)
    print(f"\n✓ Research complete: {output_path}")
    print(f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out  |  Cost: ${usd:.4f}  [{_MODEL}]")
    print(f"\nFunnel type: {analysis.get('funnel_type', 'unknown')}")
    print(f"Primary CTA: {analysis.get('primary_cta', 'unknown')}")
    print(f"\nGaps identified ({len(analysis.get('marketing_gaps', []))}):")
    for gap in analysis.get("marketing_gaps", []):
        print(f"  • {gap.get('gap')}: {gap.get('why_it_hurts')}")
    print(f"\nNext: python execution/generate_dream100_assets.py --research {output_path} --prospect-name \"{args.name}\"")


if __name__ == "__main__":
    main()
