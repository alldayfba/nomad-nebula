#!/usr/bin/env python3
"""
extract_brand_voice.py — Auto-extract brand voice from a prospect's online presence.

Scrapes YouTube, Instagram, LinkedIn, and website content, then generates
a structured brand voice markdown file that other agents use to match
the prospect's tone, language, and personality.

Based on Kabrin Johal's brand voice extraction pattern:
Agent scrapes all channels → builds markdown → all future outputs match their voice.

Usage:
    python execution/extract_brand_voice.py \
        --name "John Smith" \
        --youtube "@johnsmith" \
        --instagram "johnsmith" \
        --website "johnsmith.com" \
        --output .tmp/brand-voices/john-smith.md

    python execution/extract_brand_voice.py \
        --name "Acme Corp" \
        --website "acmecorp.com" \
        --linkedin "company/acme-corp"

    # Programmatic:
    from execution.extract_brand_voice import extract_brand_voice
    result = extract_brand_voice(name="John Smith", youtube="@johnsmith")
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


# ── Web Scraping Helpers ────────────────────────────────────────────────────

def scrape_website_text(url):
    """Scrape visible text from a website."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return {"error": "pip install requests beautifulsoup4"}

    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines[:200])  # Cap at 200 lines

        # Extract meta
        title = soup.title.string if soup.title else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "text": text[:5000],
            "word_count": len(text.split()),
        }
    except Exception as e:
        return {"error": str(e), "url": url}


def scrape_youtube_about(channel_handle):
    """Get YouTube channel info via yt-dlp."""
    try:
        import subprocess
        handle = channel_handle if channel_handle.startswith("@") else "@" + channel_handle
        url = "https://www.youtube.com/{}".format(handle)

        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json", "--playlist-end", "5", url],
            capture_output=True, text=True, timeout=30
        )

        videos = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    data = json.loads(line)
                    videos.append({
                        "title": data.get("title", ""),
                        "url": data.get("url", ""),
                        "duration": data.get("duration"),
                        "view_count": data.get("view_count"),
                    })
                except json.JSONDecodeError:
                    pass

        return {
            "channel": handle,
            "recent_videos": videos[:5],
            "video_count": len(videos),
        }
    except Exception as e:
        return {"error": str(e), "channel": channel_handle}


def scrape_youtube_transcript(video_url):
    """Extract transcript from a YouTube video."""
    try:
        import subprocess
        result = subprocess.run(
            ["yt-dlp", "--write-auto-sub", "--sub-lang", "en",
             "--skip-download", "--print", "%(subtitles)j", video_url],
            capture_output=True, text=True, timeout=30
        )
        # Fallback: just get title + description
        result2 = subprocess.run(
            ["yt-dlp", "--print", "%(title)s|||%(description)s", "--skip-download", video_url],
            capture_output=True, text=True, timeout=15
        )
        if result2.stdout:
            parts = result2.stdout.strip().split("|||")
            return {
                "title": parts[0] if parts else "",
                "description": parts[1] if len(parts) > 1 else "",
            }
        return {"error": "Could not extract info"}
    except Exception as e:
        return {"error": str(e)}


# ── Brand Voice Analysis ────────────────────────────────────────────────────

def analyze_voice_with_claude(name, scraped_data):
    """Use Claude to analyze scraped data and produce a brand voice profile."""
    try:
        import anthropic
    except ImportError:
        return {"error": "pip install anthropic"}

    client = anthropic.Anthropic()

    # Build context from scraped data
    context_parts = ["# Scraped Data for: {}\n".format(name)]

    if "website" in scraped_data and "error" not in scraped_data["website"]:
        w = scraped_data["website"]
        context_parts.append("## Website ({})".format(w.get("url", "")))
        context_parts.append("Title: {}".format(w.get("title", "")))
        context_parts.append("Meta: {}".format(w.get("meta_description", "")))
        context_parts.append("Content:\n{}".format(w.get("text", "")[:3000]))

    if "youtube" in scraped_data and "error" not in scraped_data["youtube"]:
        yt = scraped_data["youtube"]
        context_parts.append("\n## YouTube ({})".format(yt.get("channel", "")))
        for v in yt.get("recent_videos", []):
            context_parts.append("- {} ({}views)".format(
                v.get("title", ""), v.get("view_count", "?")))

    if "youtube_transcripts" in scraped_data:
        for t in scraped_data["youtube_transcripts"][:3]:
            if "error" not in t:
                context_parts.append("\n## Video: {}".format(t.get("title", "")))
                context_parts.append(t.get("description", "")[:1000])

    if "instagram" in scraped_data:
        context_parts.append("\n## Instagram: @{}".format(scraped_data["instagram"]))

    if "linkedin" in scraped_data:
        context_parts.append("\n## LinkedIn: {}".format(scraped_data["linkedin"]))

    context = "\n".join(context_parts)

    prompt = """Analyze the following scraped data about "{name}" and produce a comprehensive brand voice profile.

{context}

Generate a structured brand voice analysis in this exact format:

## Brand Voice Profile: {name}

### Personality & Tone
- **Primary tone:** (e.g., authoritative-casual, professional-warm, edgy-direct)
- **Energy level:** (e.g., high-energy motivational, calm analytical, urgent)
- **Formality:** (e.g., conversational, semi-formal, street-smart)
- **Humor style:** (e.g., self-deprecating, none, dry wit, meme-heavy)

### Language Patterns
- **Sentence structure:** (short punchy vs long flowing vs mixed)
- **Vocabulary level:** (simple/everyday vs technical/jargon-heavy vs mixed)
- **Signature phrases:** (any recurring phrases, catchphrases, or verbal tics)
- **Words they overuse:** (list 5-10 words they use frequently)
- **Words they never use:** (list words that would feel off-brand)

### Communication Style
- **How they open:** (how they typically start messages/content)
- **How they close:** (typical CTAs, sign-offs)
- **Storytelling:** (do they use stories? what kind?)
- **Data usage:** (do they cite numbers? vague or specific?)
- **Emotional appeals:** (fear, aspiration, logic, urgency?)

### Content Themes
- **Primary topics:** (what they talk about most)
- **Positioning:** (how they position themselves — expert, peer, rebel, etc.)
- **Target audience:** (who they speak to based on their content)
- **Unique angle:** (what makes their perspective different)

### Writing Rules (for matching their voice)
1. DO: [specific instruction]
2. DO: [specific instruction]
3. DO: [specific instruction]
4. DON'T: [specific instruction]
5. DON'T: [specific instruction]

### Example Phrases (in their voice)
- "[example sentence they would say]"
- "[example sentence they would say]"
- "[example sentence they would say]"
""".format(name=name, context=context)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"text": response.content[0].text, "model": "claude-sonnet-4-6"}
    except Exception as e:
        return {"error": str(e)}


# ── Main Pipeline ───────────────────────────────────────────────────────────

def extract_brand_voice(
    name,
    website=None,
    youtube=None,
    instagram=None,
    linkedin=None,
    output_path=None,
):
    """Full brand voice extraction pipeline."""
    print("Extracting brand voice for: {}".format(name))
    scraped_data = {}

    # Scrape website
    if website:
        print("  Scraping website: {}...".format(website))
        scraped_data["website"] = scrape_website_text(website)

    # Scrape YouTube
    if youtube:
        print("  Scraping YouTube: {}...".format(youtube))
        scraped_data["youtube"] = scrape_youtube_about(youtube)

        # Get transcripts from recent videos
        yt_data = scraped_data["youtube"]
        if "error" not in yt_data and yt_data.get("recent_videos"):
            scraped_data["youtube_transcripts"] = []
            for vid in yt_data["recent_videos"][:3]:
                if vid.get("url"):
                    print("    Extracting video info: {}...".format(vid["title"][:40]))
                    t = scrape_youtube_transcript(vid["url"])
                    scraped_data["youtube_transcripts"].append(t)

    # Store social handles for reference
    if instagram:
        scraped_data["instagram"] = instagram
    if linkedin:
        scraped_data["linkedin"] = linkedin

    # Analyze with Claude
    print("  Analyzing voice with Claude...")
    analysis = analyze_voice_with_claude(name, scraped_data)

    if "error" in analysis:
        print("  ERROR: {}".format(analysis["error"]))
        return analysis

    # Build output
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not output_path:
        output_path = Path(__file__).parent.parent / ".tmp" / "brand-voices" / "{}.md".format(slug)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = """<!-- Brand Voice Profile — Auto-generated by extract_brand_voice.py -->
<!-- Last Updated: {} -->
<!-- Sources: {} -->

# Brand Voice: {}

""".format(
        datetime.now().strftime("%Y-%m-%d"),
        ", ".join(s for s in [website, youtube, instagram, linkedin] if s),
        name,
    )

    full_content = header + analysis["text"]
    output_path.write_text(full_content, encoding="utf-8")
    print("  Saved: {}".format(output_path))

    return {
        "name": name,
        "output_path": str(output_path),
        "sources_scraped": list(scraped_data.keys()),
        "analysis_model": analysis.get("model", "unknown"),
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract brand voice from online presence")
    parser.add_argument("--name", required=True, help="Person or company name")
    parser.add_argument("--website", help="Website URL")
    parser.add_argument("--youtube", help="YouTube channel handle (e.g., @nicksaraev)")
    parser.add_argument("--instagram", help="Instagram handle")
    parser.add_argument("--linkedin", help="LinkedIn profile/company URL")
    parser.add_argument("--output", help="Output file path (default: .tmp/brand-voices/{slug}.md)")
    args = parser.parse_args()

    if not any([args.website, args.youtube, args.instagram, args.linkedin]):
        parser.error("At least one source required (--website, --youtube, --instagram, --linkedin)")

    result = extract_brand_voice(
        name=args.name,
        website=args.website,
        youtube=args.youtube,
        instagram=args.instagram,
        linkedin=args.linkedin,
        output_path=args.output,
    )

    if "error" in result:
        print("FAILED: {}".format(result["error"]))
        sys.exit(1)
    else:
        print("\nBrand voice extracted: {}".format(result["output_path"]))
        print("Sources: {}".format(", ".join(result["sources_scraped"])))


if __name__ == "__main__":
    main()
