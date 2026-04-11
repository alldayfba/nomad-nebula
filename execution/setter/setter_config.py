"""
Setter configuration — offers, ICP definitions, rate limits, safety rules.

All tunable constants live here. No business logic.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula",
))

# ── Offer Definitions ────────────────────────────────────────────────────────

OFFERS = {
    "amazon_os": {
        "name": "Amazon OS (24/7 Profits)",
        "price_range": "$3K–$10K",
        "calendar_url": os.getenv("GHL_CALENDAR_URL_AMAZON", ""),
        "pipeline_id": os.getenv("GHL_PIPELINE_ID_AMAZON", ""),
        "stage_id_new": os.getenv("GHL_STAGE_NEW_AMAZON", ""),
        "stage_id_booked": os.getenv("GHL_STAGE_BOOKED_AMAZON", ""),
        "closer_names": ["Sabbo"],
        "dm_tone": "casual",  # text like a friend, short sentences
        "cta_keyword": "AMAZON",
        "tags": ["ig-ai-setter", "amazon-os"],
        "icp": {
            "description": "People with $5K-$20K capital motivated by income replacement or building a real asset",
            "tiers": {
                "A": "Complete beginner, $5K-$20K capital, wants financial freedom / income replacement",
                "B": "Existing Amazon seller doing <$50K/mo, plateaued, wants to break through",
                "C": "Business owner or investor adding Amazon as a cash-flowing asset",
            },
            "signals": [
                "Bio mentions: entrepreneur, side hustle, Amazon, ecommerce, FBA, passive income, financial freedom",
                "Follows Amazon coaching/FBA accounts",
                "Engages with business/ecommerce content",
                "Age 22-45, US/Canada/UK/Australia",
                "Has a 9-5 and posts about wanting more",
            ],
            "disqualify": [
                "Under $3K capital (if mentioned in bio)",
                "Pure passive income seeker with no action signals",
                "No specific goal or ambition visible",
                "Already in a competing coaching program (visible in bio/follows)",
            ],
        },
        "knowledge_files": [
            "clients/kd-amazon-fba/scripts/setter-outreach-script.md",
            ".tmp/creators/hormozi-docx-extractions/dm-setting-breakdown.md",
            ".tmp/creators/hormozi-docx-extractions/setting-scripts-1.md",
        ],
    },
    "agency_os": {
        "name": "Growth Agency (Agency OS)",
        "price_range": "$5K–$25K/mo retainer",
        "calendar_url": os.getenv("GHL_CALENDAR_URL_AGENCY", ""),
        "pipeline_id": os.getenv("GHL_PIPELINE_ID_AGENCY", ""),
        "stage_id_new": os.getenv("GHL_STAGE_NEW_AGENCY", ""),
        "stage_id_booked": os.getenv("GHL_STAGE_BOOKED_AGENCY", ""),
        "closer_names": ["Sabbo"],
        "dm_tone": "professional",  # direct, respectful, value-forward
        "cta_keyword": "GROWTH",
        "tags": ["ig-ai-setter", "agency-os"],
        "icp": {
            "description": "7-8 figure founder with product-market fit but no repeatable acquisition engine",
            "tiers": {
                "A": "Founder-led service business $50K+/mo, has real website/team, bottleneck is lead gen or conversion",
                "B": "SaaS or ecom founder $100K+/mo, burning ad spend without systems",
            },
            "signals": [
                "Bio mentions: CEO, Founder, Owner + a real business name",
                "Has a real website (not just a link tree)",
                "Posts about business challenges, team, growth",
                "Follower count 1K-50K (real business, not influencer)",
                "B2B or high-ticket service company",
            ],
            "disqualify": [
                "Pre-revenue startup",
                "Solo freelancer with no team",
                "Already working with a growth agency (visible in bio/posts)",
                "Under $50K/mo revenue signals",
            ],
        },
        "knowledge_files": [
            "SabboOS/Agency_OS_DM_Scripts.md",
            "SabboOS/Agency_OS_Objection_Battle_Cards.md",
        ],
    },
}

# ── Rate Limits ──────────────────────────────────────────────────────────────

RATE_LIMITS = {
    # DM sending
    "dm_daily_max": 1000,         # Total DMs per day — Sabbo's account is seasoned, no issues
    "dm_cold_max": 400,           # New follower openers per day
    "dm_warm_max": 300,           # Story viewers + engager re-engages per day
    "dm_followup_max": 200,       # Follow-up messages per day (old leads)
    "dm_story_max": 100,          # Story viewer re-engages per day
    "dm_cooldown_min": 30,        # Minimum seconds between DMs
    "dm_cooldown_max": 90,        # Maximum seconds between DMs (randomized)
    # Profile scanning
    "profile_views_daily": 500,
    "profile_views_hourly": 100,
    # Warm-up ramp (day number → max DMs that day)
    "ramp_up": {
        1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000, 6: 1000, 7: 1000,
    },
    "ramp_up_days": 0,  # Disabled — account is seasoned
    # Batch timing
    "cold_batch_hour": 9,         # 9 AM EST
    "warm_batch_hour": 14,        # 2 PM EST
    "batch_spread_hours": 2,      # Spread batch over 2 hours
    # Night mode (inbox monitoring only, no outbound)
    "night_start_hour": 0,        # 12 AM
    "night_end_hour": 6,          # 6 AM
}

# ── Safety ───────────────────────────────────────────────────────────────────

SAFETY = {
    # Approval gate — first N conversations require human approval
    "approval_gate_count": 20,
    # Escalation — these keywords in prospect messages trigger human takeover
    "escalation_keywords": [
        "lawsuit", "sue", "attorney", "lawyer", "refund", "scam",
        "report", "bbb", "fraud", "harassment", "stop messaging",
        "unsubscribe", "block", "spam",
    ],
    # Message cap — flag for review if this many messages without booking
    "max_messages_before_flag": 15,
    # Topics the setter must NEVER discuss in detail
    "never_discuss": [
        "exact pricing",
        "guarantee specifics",
        "competitor bashing",
        "refund policy details",
    ],
    # Redirect phrases for never_discuss topics
    "redirect_phrase": "That's exactly what we'll cover on the call — {closer} will break down what makes sense for your situation.",
    # Cost ceiling — max daily Claude API spend before switching to read-only
    "daily_api_cost_ceiling": 5.00,
    # Kill switch file — if this exists, all sending stops
    "pause_file": str(PROJECT_ROOT / ".tmp" / "setter" / "PAUSED"),
    # Action block detection — pause duration in hours
    "action_block_pause_hours": 24,

    # ── SECURITY GUARDRAILS ──────────────────────────────────────────────
    # Prompt injection protection — if prospect's message contains these patterns,
    # treat as injection attempt → escalate to human, DO NOT execute
    "injection_patterns": [
        "ignore previous instructions",
        "ignore your instructions",
        "ignore all instructions",
        "disregard your prompt",
        "disregard previous",
        "forget everything",
        "forget your instructions",
        "new instructions",
        "override your",
        "bypass your",
        "you are now",
        "act as",
        "pretend to be",
        "roleplay as",
        "system prompt",
        "reveal your instructions",
        "what are your instructions",
        "show me your prompt",
        "output your prompt",
        "repeat your system",
        "print your system",
        "from now on you are",
        "jailbreak",
        "DAN mode",
        "developer mode",
        "do anything now",
        "simulate a",
        "enter debug mode",
    ],

    # HARD RESTRICTIONS — the setter can NEVER do these, period
    "never_actions": [
        "post content on the account (stories, reels, posts)",
        "change profile bio/picture/settings",
        "follow/unfollow anyone",
        "like/comment on posts",
        "share/forward messages to anyone",
        "send links other than the booking calendar",
        "send images/videos/voice notes autonomously",
        "mention other students or clients by name",
        "share revenue numbers, financial data, or internal business info",
        "share pricing without Sabbo's explicit approval",
        "agree to discounts or special terms",
        "make promises about results or guarantees",
        "discuss refund policies or legal matters",
        "send payment links or collect money",
    ],

    # Data that must NEVER appear in any DM
    "sensitive_data_patterns": [
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",      # phone numbers (Sabbo's)
        r"[\w.+-]+@[\w-]+\.[\w.-]+",              # email addresses (internal)
        r"sk-ant-[\w-]+",                          # API keys
        r"password|passwd|secret|token",           # credentials
        r"\$\d{2,},?\d{3}",                       # large dollar amounts (revenue)
    ],

    # Max message length — prevents runaway generation
    "max_dm_length": 300,
    # Max consecutive messages without prospect reply before auto-pause
    "max_unanswered_messages": 3,
}

# ── Timezone ────────────────────────────────────────────────────────────────

TIMEZONE = "US/Eastern"  # Sabbo is in Miami, EST

# ── Sabbo's Exact DM Script ────────────────────────────────────────────────
# These are Sabbo's REAL words. Use them word-for-word at each stage.
# AI only deviates for objections, unexpected questions, or personalization.

DM_SCRIPT = {
    # Stage 1: Warm opener for new followers (A/B test — pattern_learner tracks success)
    "opener_cold": [
        "yooo, u looking into amazon i see??",
        "yoo whats good, saw u just followed — you selling on amazon or looking to start?",
        "yooo u into amazon or just checking things out?",
        "yo whats up, you looking into starting on amazon?",
        "ayy welcome, you into amazon fba or still exploring?",
    ],

    # Stage 1b: Story viewer who never DM'd
    "opener_story_new": "noticed you been watching my stuff, hows amazon been or have you started at all??",

    # Stage 1c: Story viewer who we spoke to before (re-engage)
    "opener_story_reengage": "noticed you been watching my stuff, hows amazon been since we last spoke?",

    # Stage 2: Qualify interest (after they reply to opener)
    "qualify_interest": "gotcha, u ever tried online biz before? what makes you want to get into it?",

    # Stage 2b: Clarify (if they're vague/unclear early on)
    "clarify": "What are you looking for specifically just to see if I can help you In any way?",

    # Stage 3: Resources check (after they share motivation)
    "resources_check": "gotcha, i have some things that may be able to help you out, If you started today how much would you say you have to invest into this and really get the ball rolling with your biz and what does your credit look like so i can best guide you in which path to take",

    # Stage 3c: Trigger / need amplification (before close)
    "trigger": "is that also the reason why you followed — because you were looking for some help with this?",

    # Stage 4: Close (after resources + trigger confirmed)
    "close": "are you looking for more just basic info and do trial and error on your own or just have 1on1 guidance and do it right the first time??",

    # Stage 4b: Reclose (if they say "on my own")
    "reclose": "if you're starting a new business and planning to invest $$$ and time wouldn't u want to do it right the first time",

    # Stage 5: Booking (they pick 1on1) — send them to GHL booking form
    "booking_ask": "bet lets get you locked in then, go ahead and book a time here that works for you 👇\nhttps://api.leadconnectorhq.com/widget/booking/9fL4lUjdONSbW0oJ419Y",

    # Stage 5b: Timezone context
    "timezone": "i'm in miami so im EST",

    # Stage 6: After they book — send call prep
    "post_booking": "gotcha just locked you in 🔥\nhttps://alldayfba.com/call-prep\n\ngo thru this it will give you a full clarity on what I do and about my program and how i can help you scale this up",
}

# ── Reply Delay (don't look like a bot) ─────────────────────────────────────

REPLY_DELAY = {
    "min_seconds": 30,   # Min wait before replying (don't look instant = bot)
    "max_seconds": 90,   # Max wait (always under 2 min total with processing time)
}

REPLY_DELAY_INBOUND = {
    "min_seconds": 10,   # Faster for inbound — they're hot
    "max_seconds": 30,   # Still under 30s (Hormozi: 60s response time target)
}

# ── Comment Keywords (trigger auto-DM when someone comments these) ──────────

COMMENT_KEYWORDS = {
    "amazon_os": [
        "AI", "AMZ", "AMAZON", "SCALE", "FBA", "SOURCING", "INFO", "HOW",
        "MONEY", "SIDE HUSTLE", "PASSIVE", "INCOME", "SELL", "PRODUCT",
        "WHOLESALE", "PROFIT", "COACH", "MENTOR", "HELP",
    ],
    "agency_os": [
        "GROWTH", "LEADS", "PIPELINE", "AUDIT", "MARKETING", "ADS",
        "FUNNEL", "AGENCY",
    ],
}

# ── Conversation Stages ──────────────────────────────────────────────────────

STAGES = [
    "new",               # Prospect identified, not yet contacted
    "opener_sent",       # First DM sent, waiting for reply
    "replied",           # Prospect replied, not yet qualifying
    "qualifying",        # In qualification flow
    "qualified",         # All 3 qualifiers confirmed
    "booking",           # Calendar link sent, waiting for booking
    "booked",            # Call booked
    "show",              # Showed up to call
    "no_show",           # Did not show
    "nurture",           # Not ready now, in nurture sequence
    "disqualified",      # Does not meet ICP
    "dead",              # No response after full follow-up sequence
    "escalated",         # Requires human intervention
]

# ── Follow-Up Cadence ────────────────────────────────────────────────────────

FOLLOW_UP_SEQUENCE = [
    {"number": 0, "delay_hours": 5, "type": "still_with_me",
     "template": "still with me?"},
    {"number": 1, "delay_days": 1, "type": "text_bump",
     "template": "Hey — just making sure this didn't get buried. {original_reference}"},
    {"number": 2, "delay_days": 3, "type": "voice_memo",
     "template": "Send a 15-20 sec personalized voice memo style message, no ask"},
    {"number": 3, "delay_days": 7, "type": "value_share",
     "template": "Share a relevant reel/case study/resource, no ask attached"},
    {"number": 4, "delay_days": 14, "type": "final_touch",
     "template": "If {topic} ever becomes a focus, hit me up. Here if you need anything."},
]

# ── Model Routing ────────────────────────────────────────────────────────────

MODELS = {
    "icp_scoring": "claude-haiku-4-5-20251001",
    "opener": "claude-haiku-4-5-20251001",
    "qualification": "claude-sonnet-4-6",
    "objection": "claude-sonnet-4-6",
    "escalation": "claude-sonnet-4-6",
    "pattern_analysis": "claude-haiku-4-5-20251001",
}

MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (0.80, 4.0),   # input, output per 1M tokens
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
}

# ── Prospect Sources ─────────────────────────────────────────────────────────

PROSPECT_SOURCES = [
    "new_follower",       # Someone who just followed the account
    "story_reply",        # Replied to a story
    "post_comment",       # Commented on a post
    "post_like",          # Liked a post (lower intent)
    "hashtag",            # Found via hashtag search
    "competitor_follower",# Follows a competitor account
    "manychat_keyword",   # Triggered a ManyChat keyword
    "ad_lead",            # Came from an ad funnel
    "referral",           # Referred by another lead
    "manual",             # Added manually
]

# ── Own Account (scan new followers for outbound) ────────────────────────────

OWN_IG_HANDLE = os.getenv("SETTER_IG_HANDLE", "allday.fba")

# ── Competitor Accounts to Scan ──────────────────────────────────────────────

COMPETITOR_ACCOUNTS = {
    "amazon_os": [
        # Add competitor FBA coaching IG handles here
        # Example: "competitor_fba_coach_1",
    ],
    "agency_os": [],
}

# ── Hashtags to Monitor ──────────────────────────────────────────────────────

HASHTAGS = {
    "amazon_os": [
        "amazonfba", "amazonseller", "fbacoaching", "amazonfbaseller",
        "amazonfbatips", "sidehustleideas", "ecommercebusiness",
        "passiveincomeideas", "quitmy9to5", "financialfreedom",
    ],
    "agency_os": [
        "businessgrowth", "scaleyourbusiness", "growthmarketing",
        "founderstory", "businessowner", "entrepreneurlife",
        "marketingagency", "b2bmarketing", "leadgeneration",
    ],
}

# ── ManyChat Keywords ────────────────────────────────────────────────────────

MANYCHAT_KEYWORDS = {
    "AMAZON": {"offer": "amazon_os", "warmth": "high"},
    "FBA": {"offer": "amazon_os", "warmth": "high"},
    "COACHING": {"offer": "amazon_os", "warmth": "high"},
    "SOURCING": {"offer": "amazon_os", "warmth": "medium"},
    "GROWTH": {"offer": "agency_os", "warmth": "high"},
    "AUDIT": {"offer": "agency_os", "warmth": "high"},
    "PIPELINE": {"offer": "agency_os", "warmth": "medium"},
}

# ── Chrome Config ────────────────────────────────────────────────────────────

CHROME_PORT = int(os.getenv("SETTER_CHROME_PORT", "9222"))
CHROME_LAUNCH_SCRIPT = str(PROJECT_ROOT / "execution" / "launch_chrome.sh")

# ── Discord Notifications ────────────────────────────────────────────────────

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_SETTER_WEBHOOK", "")
DISCORD_ESCALATION_WEBHOOK = os.getenv("DISCORD_ESCALATION_WEBHOOK", "")

# ── Database ─────────────────────────────────────────────────────────────────

DB_PATH = PROJECT_ROOT / ".tmp" / "setter" / "setter.db"
LOG_PATH = PROJECT_ROOT / ".tmp" / "setter" / "setter.log"

# ── Dashboard Auth ──────────────────────────────────────────────────────────

DASHBOARD_TOKEN = os.getenv("SETTER_DASHBOARD_TOKEN", "")

# ── Calendar Booking (Auto-Book via GHL) ────────────────────────────────────

GHL_CALENDAR_ID_AMAZON = os.getenv("GHL_CALENDAR_ID_AMAZON", "9fL4lUjdONSbW0oJ419Y")
GHL_CALENDAR_ID_AGENCY = os.getenv("GHL_CALENDAR_ID_AGENCY", "")

BOOKING = {
    "buffer_hours": 2,           # Minimum hours from now before booking
    "default_duration": 30,      # Minutes per call
    "timezone": "America/New_York",
    "calendar_ids": {
        "amazon_os": GHL_CALENDAR_ID_AMAZON,
        "agency_os": GHL_CALENDAR_ID_AGENCY,
    },
}
