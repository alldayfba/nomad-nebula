"""
Import Discord course content into Supabase academy tables.

Usage:
    python execution/import_discord_to_academy.py                 # DRY RUN (default)
    python execution/import_discord_to_academy.py --live          # LIVE — actually insert into Supabase
    python execution/import_discord_to_academy.py --module "Keepa Course"  # Only import one module

Input:  .tmp/discord-course-content.json
Target: Supabase academy_modules + academy_lessons tables (fba-saas project)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_FILE = Path(__file__).resolve().parent.parent / ".tmp" / "discord-course-content.json"
_env_primary = Path("/Users/SabboOpenClawAI/Documents/fba-saas/.env.local")
ENV_FILE = _env_primary if _env_primary.exists() else Path("/Users/sabbojb/Documents/fba-saas/.env.local")

# Modules to import (Discord module name -> academy config)
# sort_order starts at 100 to avoid colliding with the 7 existing seed modules (sort 1-7)
MODULE_MAP = {
    "Core Course Videos": {
        "title": "Core Course Videos",
        "slug": "core-course-videos",
        "description": "70+ video lessons covering the full AllDayFBA system — from shorts to deep dives.",
        "sort_order": 100,
        "week_start": 1, "week_end": 12,
    },
    "Seller Central Course": {
        "title": "Seller Central Course",
        "slug": "seller-central-course",
        "description": "Step-by-step Seller Central walkthroughs — FBM listings, FBA listings, and dashboard navigation.",
        "sort_order": 101,
        "week_start": 1, "week_end": 2,
    },
    "Online Arbitrage Course": {
        "title": "Online Arbitrage Course",
        "slug": "online-arbitrage-course",
        "description": "Complete OA workflow — finding deals, sourcing from retailers, and flipping on Amazon.",
        "sort_order": 102,
        "week_start": 2, "week_end": 4,
    },
    "Keepa Course": {
        "title": "Keepa Course",
        "slug": "keepa-course",
        "description": "Master Keepa charts, Product Finder, and data-driven product validation.",
        "sort_order": 103,
        "week_start": 2, "week_end": 3,
    },
    "Google Ads Course": {
        "title": "Google Ads Course",
        "slug": "google-ads-course",
        "description": "Google Ads for Amazon sellers — account setup, campaign types, and optimization.",
        "sort_order": 104,
        "week_start": 5, "week_end": 8,
    },
    "Lead Gen Ads Course": {
        "title": "Lead Gen Ads Course",
        "slug": "lead-gen-ads-course",
        "description": "Lead generation ad strategies — funnels, targeting, and conversion optimization.",
        "sort_order": 105,
        "week_start": 5, "week_end": 8,
    },
    "Facebook Ads Course": {
        "title": "Facebook Ads Course",
        "slug": "facebook-ads-course",
        "description": "Facebook & Instagram ads for Amazon product launches and brand building.",
        "sort_order": 106,
        "week_start": 5, "week_end": 8,
    },
    "TikTok Ads Course": {
        "title": "TikTok Ads Course",
        "slug": "tiktok-ads-course",
        "description": "TikTok advertising for ecommerce — creative strategy, targeting, and scaling.",
        "sort_order": 107,
        "week_start": 5, "week_end": 8,
    },
    "Sales Course": {
        "title": "Sales Course",
        "slug": "sales-course",
        "description": "Sales fundamentals — closing, objection handling, and consultative selling.",
        "sort_order": 108,
        "week_start": 3, "week_end": 6,
    },
    "B2B Outreach Course": {
        "title": "B2B Outreach Course",
        "slug": "b2b-outreach-course",
        "description": "B2B outreach for wholesale and brand partnerships — cold email, follow-ups, and deal structure.",
        "sort_order": 109,
        "week_start": 4, "week_end": 6,
    },
    "Mindset Course": {
        "title": "Mindset Course",
        "slug": "mindset-course",
        "description": "Entrepreneurial mindset — discipline, focus, and mental frameworks for long-term success.",
        "sort_order": 110,
        "week_start": 1, "week_end": 12,
    },
    "Funding Course": {
        "title": "Funding Course",
        "slug": "funding-course",
        "description": "Business credit cards, funding options, and capital strategies for Amazon sellers.",
        "sort_order": 111,
        "week_start": 1, "week_end": 2,
    },
    "Coaching Call Library": {
        "title": "Coaching Call Library",
        "slug": "coaching-call-library",
        "description": "Recorded coaching calls — real student questions, live product reviews, and strategy sessions.",
        "sort_order": 112,
        "week_start": 1, "week_end": 12,
    },
    "Alex Hormozi Gems": {
        "title": "Alex Hormozi Gems",
        "slug": "alex-hormozi-gems",
        "description": "Curated Hormozi playbooks and resources — offers, closing, hooks, lead nurture, and more.",
        "sort_order": 113,
        "week_start": 1, "week_end": 12,
    },
    "Amazon Resources": {
        "title": "Amazon Resources",
        "slug": "amazon-resources",
        "description": "Guides, checklists, supplier lists, and reference documents for Amazon sellers.",
        "sort_order": 114,
        "week_start": 1, "week_end": 12,
    },
}

# Modules to SKIP (not course material)
SKIP_MODULES = {
    "Community Content",
    "Inner Circle Student Channels",
    "Student Wins",
    "Product Leads",
    "Announcements",
    "Coaching Resources",
    "Supplementary Materials",
}

# Resource types that become video lessons vs attached resources
VIDEO_TYPES = {"video"}
RESOURCE_TYPES = {"document", "file", "link", "image"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    text = text.lower().strip()
    # Remove emoji and special unicode
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    # Remove leading markers like "Lesson 1:" or numbering
    text = re.sub(r'^\s*lesson\s*\d+\s*[:.-]\s*', '', text, flags=re.IGNORECASE)
    # Replace non-alphanum with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    # Collapse multiple hyphens
    text = re.sub(r'-+', '-', text)
    # Truncate to 80 chars
    if len(text) > 80:
        text = text[:80].rsplit('-', 1)[0]
    return text or 'untitled'


def clean_title(title: str) -> str:
    """Clean up Discord message titles for display."""
    title = title.strip()
    # Remove @everyone mentions
    title = re.sub(r'@everyone\s*', '', title).strip()
    # If title is just hashtags (shorts), make it more descriptive
    if title.startswith('#') and all(c in '#abcdefghijklmnopqrstuvwxyz ' for c in title.lower()):
        return title  # Keep hashtag titles as-is, they'll get numbered later
    # Remove leading emoji sequences
    title = re.sub(r'^[\U0001F300-\U0001FAD6\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0000200D]+\s*', '', title)
    # Truncate very long titles
    if len(title) > 150:
        title = title[:147] + '...'
    return title if title else 'Untitled'


def classify_resource(resource: dict) -> str:
    """Map Discord resource type to LessonResource type."""
    rtype = resource.get('type', '')
    filename = resource.get('filename', '').lower()
    url = resource.get('url', '').lower()

    if rtype == 'document' or filename.endswith('.pdf'):
        return 'pdf'
    if filename.endswith(('.xlsx', '.xls', '.csv', '.gsheet')):
        return 'spreadsheet'
    if filename.endswith(('.doc', '.docx', '.txt')):
        return 'template'
    if rtype == 'link':
        return 'link'
    if rtype == 'file':
        if filename.endswith('.mp3'):
            return 'link'  # Audio files as links
        return 'link'
    return 'link'


def is_video_url(url: str) -> bool:
    """Check if URL is a video (YouTube, Loom, or video file)."""
    url_lower = url.lower()
    if any(domain in url_lower for domain in ['youtube.com', 'youtu.be', 'loom.com']):
        return True
    if any(url_lower.endswith(ext) or f'.{ext}?' in url_lower for ext in ['mp4', 'mov', 'webm', 'avi']):
        return True
    # Discord CDN video attachments
    if 'cdn.discordapp.com' in url_lower and any(ext in url_lower for ext in ['.mp4', '.mov']):
        return True
    return False


def build_lessons_from_resources(resources: list[dict], module_slug: str) -> list[dict]:
    """
    Convert Discord resources into academy lesson records.

    Strategy:
    - Video resources become lessons (one lesson per video)
    - Non-video resources (docs, links, images) get grouped as attachments
      to the nearest preceding video lesson, OR become standalone resource lessons
    """
    # Sort by timestamp
    sorted_resources = sorted(resources, key=lambda r: r.get('timestamp', ''))

    lessons = []
    pending_attachments = []  # Non-video resources waiting to attach to a lesson
    slug_counter = {}  # Track slug usage for dedup

    for res in sorted_resources:
        rtype = res.get('type', '')
        url = res.get('url', '')
        title = clean_title(res.get('title', 'Untitled'))
        filename = res.get('filename', '')

        is_vid = rtype == 'video' or is_video_url(url)

        if is_vid:
            # Flush pending attachments to previous lesson or create resource lesson
            if pending_attachments and lessons:
                # Attach to previous lesson
                lessons[-1]['resources'].extend(pending_attachments)
                pending_attachments = []
            elif pending_attachments and not lessons:
                # No video lesson yet — create a "Resources" intro lesson
                res_lesson = _make_resource_lesson(
                    pending_attachments, module_slug, len(lessons) + 1, slug_counter
                )
                if res_lesson:
                    lessons.append(res_lesson)
                pending_attachments = []

            # Create video lesson
            display_title = title
            if not display_title or display_title == 'Untitled':
                display_title = filename or f'Video {len(lessons) + 1}'
                # Clean filename into title
                display_title = re.sub(r'\.[^.]+$', '', display_title)  # Remove extension
                display_title = display_title.replace('_', ' ').replace('-', ' ')
                display_title = re.sub(r'\s+', ' ', display_title).strip()

            slug = slugify(display_title)
            # Ensure unique slug within module
            if slug in slug_counter:
                slug_counter[slug] += 1
                slug = f'{slug}-{slug_counter[slug]}'
            else:
                slug_counter[slug] = 1

            lessons.append({
                'title': display_title,
                'slug': slug,
                'description': None,
                'video_url': url,
                'video_duration_seconds': None,
                'content_md': None,
                'resources': [],
                'tool_link': None,
                'sort_order': len(lessons) + 1,
                'min_tier': 'tier_a',
                'is_published': True,
                'allowed_roles': ['admin', 'student', 'viewer'],
            })

        else:
            # Non-video resource — queue as attachment
            if rtype == 'image' and not filename:
                continue  # Skip random images with no context

            resource_entry = {
                'name': title if title != 'Untitled' else (filename or 'Resource'),
                'url': url,
                'type': classify_resource(res),
            }
            pending_attachments.append(resource_entry)

    # Flush remaining attachments
    if pending_attachments:
        if lessons:
            lessons[-1]['resources'].extend(pending_attachments)
        else:
            # Module has NO videos — create lessons from resources
            for i, att in enumerate(pending_attachments, 1):
                slug = slugify(att['name'])
                if slug in slug_counter:
                    slug_counter[slug] += 1
                    slug = f'{slug}-{slug_counter[slug]}'
                else:
                    slug_counter[slug] = 1

                lessons.append({
                    'title': att['name'],
                    'slug': slug,
                    'description': None,
                    'video_url': att['url'] if att['type'] == 'link' else None,
                    'video_duration_seconds': None,
                    'content_md': None,
                    'resources': [att] if att['type'] != 'link' else [],
                    'tool_link': att['url'] if att['type'] == 'link' else None,
                    'sort_order': i,
                    'min_tier': 'tier_a',
                    'is_published': True,
                    'allowed_roles': ['admin', 'student', 'viewer'],
                })

    return lessons


def _make_resource_lesson(
    attachments: list[dict], module_slug: str, sort_order: int, slug_counter: dict
) -> dict | None:
    """Create a lesson from a batch of non-video resources."""
    if not attachments:
        return None
    slug = f'{module_slug}-resources'
    if slug in slug_counter:
        slug_counter[slug] += 1
        slug = f'{slug}-{slug_counter[slug]}'
    else:
        slug_counter[slug] = 1

    return {
        'title': 'Course Resources & Materials',
        'slug': slug,
        'description': 'Documents, links, and supplementary materials for this module.',
        'video_url': None,
        'video_duration_seconds': None,
        'content_md': None,
        'resources': attachments,
        'tool_link': None,
        'sort_order': sort_order,
        'min_tier': 'tier_a',
        'is_published': True,
        'allowed_roles': ['admin', 'student', 'viewer'],
    }


def load_env(env_path: Path) -> dict[str, str]:
    """Load .env.local vars."""
    env = {}
    if not env_path.exists():
        return env
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env


# ---------------------------------------------------------------------------
# Supabase API
# ---------------------------------------------------------------------------

def supabase_request(
    method: str,
    table: str,
    data: dict | list | None = None,
    params: dict | None = None,
    supabase_url: str = '',
    service_key: str = '',
    prefer: str | None = None,
) -> dict | list | None:
    """Make a Supabase REST API request."""
    import httpx

    url = f'{supabase_url}/rest/v1/{table}'
    headers = {
        'apikey': service_key,
        'Authorization': f'Bearer {service_key}',
        'Content-Type': 'application/json',
    }
    if prefer:
        headers['Prefer'] = prefer

    response = httpx.request(
        method, url, json=data, params=params, headers=headers, timeout=30
    )
    if response.status_code >= 400:
        print(f'  ERROR {response.status_code}: {response.text}')
        return None
    if response.content:
        return response.json()
    return None


def upsert_module(module_config: dict, supabase_url: str, service_key: str) -> str | None:
    """Upsert a module and return its UUID."""
    payload = {
        'title': module_config['title'],
        'slug': module_config['slug'],
        'description': module_config['description'],
        'sort_order': module_config['sort_order'],
        'week_start': module_config['week_start'],
        'week_end': module_config['week_end'],
        'min_tier': 'tier_a',
        'is_published': True,
    }
    result = supabase_request(
        'POST', 'academy_modules', data=payload,
        supabase_url=supabase_url, service_key=service_key,
        prefer='return=representation,resolution=merge-duplicates',
    )
    if result and isinstance(result, list) and len(result) > 0:
        return result[0].get('id')
    return None


def upsert_lesson(lesson: dict, module_id: str, supabase_url: str, service_key: str) -> bool:
    """Upsert a lesson."""
    payload = {
        'module_id': module_id,
        'title': lesson['title'],
        'slug': lesson['slug'],
        'description': lesson.get('description'),
        'video_url': lesson.get('video_url'),
        'video_duration_seconds': lesson.get('video_duration_seconds'),
        'content_md': lesson.get('content_md'),
        'resources': json.dumps(lesson.get('resources', [])),
        'tool_link': lesson.get('tool_link'),
        'sort_order': lesson['sort_order'],
        'min_tier': lesson.get('min_tier', 'tier_a'),
        'is_published': lesson.get('is_published', True),
    }
    result = supabase_request(
        'POST', 'academy_lessons', data=payload,
        supabase_url=supabase_url, service_key=service_key,
        # Upsert on (module_id, slug) unique constraint
        prefer='return=representation,resolution=merge-duplicates',
    )
    return result is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Import Discord course content into Supabase academy')
    parser.add_argument('--live', action='store_true', help='Actually insert into Supabase (default: dry run)')
    parser.add_argument('--module', type=str, help='Only import a specific module by Discord name')
    args = parser.parse_args()

    dry_run = not args.live

    # Load data
    if not INPUT_FILE.exists():
        print(f'ERROR: Input file not found: {INPUT_FILE}')
        sys.exit(1)

    with open(INPUT_FILE) as f:
        data = json.load(f)

    print(f'Loaded {data["total_resources"]} total resources from {data["channels_processed"]} channels')
    print(f'Mode: {"DRY RUN" if dry_run else "LIVE (writing to Supabase)"}\n')

    # Load Supabase credentials (needed for live mode)
    supabase_url = ''
    service_key = ''
    if not dry_run:
        env = load_env(ENV_FILE)
        supabase_url = env.get('NEXT_PUBLIC_SUPABASE_URL', '')
        service_key = env.get('SUPABASE_SERVICE_ROLE_KEY', '')
        if not supabase_url or not service_key:
            print('ERROR: Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env.local')
            sys.exit(1)
        print(f'Supabase: {supabase_url}\n')

    # Process modules
    total_modules = 0
    total_lessons = 0
    total_resources_attached = 0
    skipped_modules = []
    summary = []

    for discord_name, mod_resources in data['modules'].items():
        # Filter to single module if requested
        if args.module and discord_name != args.module:
            continue

        # Skip non-course modules
        if discord_name in SKIP_MODULES:
            skipped_modules.append(f'  SKIP: {discord_name} ({len(mod_resources["resources"])} resources — not course material)')
            continue

        # Check if we have a mapping for this module
        if discord_name not in MODULE_MAP:
            skipped_modules.append(f'  SKIP: {discord_name} ({len(mod_resources["resources"])} resources — no mapping configured)')
            continue

        config = MODULE_MAP[discord_name]
        resources = mod_resources['resources']

        print(f'--- {discord_name} ---')
        print(f'  Discord resources: {len(resources)}')

        # Build lessons
        lessons = build_lessons_from_resources(resources, config['slug'])
        total_attached = sum(len(l['resources']) for l in lessons)

        print(f'  Lessons to create: {len(lessons)}')
        print(f'  Attached resources: {total_attached}')

        # Print lesson details
        for lesson in lessons:
            vid_marker = 'VIDEO' if lesson.get('video_url') else 'RESOURCES'
            res_count = len(lesson.get('resources', []))
            res_str = f' (+{res_count} resources)' if res_count > 0 else ''
            print(f'    [{lesson["sort_order"]:>3}] [{vid_marker:>9}] {lesson["title"][:80]}{res_str}')
            print(f'           slug: {lesson["slug"]}')
            if lesson.get('video_url'):
                print(f'           url:  {lesson["video_url"][:100]}')

        # Live insert
        if not dry_run:
            module_id = upsert_module(config, supabase_url, service_key)
            if not module_id:
                print(f'  FAILED to upsert module {config["slug"]}')
                continue
            print(f'  Module ID: {module_id}')

            success = 0
            for lesson in lessons:
                if upsert_lesson(lesson, module_id, supabase_url, service_key):
                    success += 1
            print(f'  Inserted: {success}/{len(lessons)} lessons')

        total_modules += 1
        total_lessons += len(lessons)
        total_resources_attached += total_attached
        summary.append({
            'module': config['title'],
            'slug': config['slug'],
            'lessons': len(lessons),
            'resources': total_attached,
        })
        print()

    # Print skipped
    if skipped_modules:
        print('\n--- Skipped ---')
        for s in skipped_modules:
            print(s)

    # Summary
    print(f'\n{"=" * 60}')
    print(f'SUMMARY {"(DRY RUN)" if dry_run else "(LIVE)"}')
    print(f'{"=" * 60}')
    print(f'Modules:    {total_modules}')
    print(f'Lessons:    {total_lessons}')
    print(f'Resources:  {total_resources_attached} (attached to lessons)')
    print()
    print(f'{"Module":<35} {"Lessons":>8} {"Resources":>10}')
    print(f'{"-" * 35} {"-" * 8} {"-" * 10}')
    for s in summary:
        print(f'{s["module"]:<35} {s["lessons"]:>8} {s["resources"]:>10}')
    print()

    if dry_run:
        print('This was a DRY RUN. Run with --live to insert into Supabase.')


if __name__ == '__main__':
    main()
