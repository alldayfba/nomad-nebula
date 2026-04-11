"""
Setter brain — Claude API conversation engine with stage-aware knowledge loading.

Generates contextual DM responses by assembling a system prompt from:
- Setter identity (bots/setter/identity.md)
- Offer-specific knowledge files
- Conversation history + state
- Objection battle cards (when qualifying)
- Winning patterns (from DB)

Model routing: Haiku for openers, Sonnet for qualification/objections.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import subprocess
from dotenv import load_dotenv

from .setter_config import (
    DM_SCRIPT,
    MODELS,
    OFFERS,
    PROJECT_ROOT,
    SAFETY,
)
from . import setter_db as db

load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("setter.brain")

# ── File Loading ─────────────────────────────────────────────────────────────

def _load_file(path: Path, max_chars: int = 0) -> str:
    """Load file contents. Truncate if max_chars > 0."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n\n[... truncated for token efficiency ...]"
        return text
    except (FileNotFoundError, OSError):
        return ""


def _load_section(path: Path, section_header: str, max_chars: int = 5000) -> str:
    """Load a specific section from a markdown file by header.

    Captures everything from the matched header until the next header
    of the SAME level or higher (fewer #), so sub-headers are included.
    """
    text = _load_file(path)
    if not text:
        return ""
    # Find the header and determine its level (number of #)
    header_pattern = rf"(#{{1,6}})\s*{re.escape(section_header)}"
    header_match = re.search(header_pattern, text, re.IGNORECASE)
    if not header_match:
        return ""
    level = len(header_match.group(1))  # e.g. "##" → 2
    start = header_match.start()
    # Stop at the next header of same level or higher (≤ level #s)
    # e.g. for ##, stop at # or ## but NOT ### or ####
    end_pattern = rf"\n#{{1,{level}}}\s"
    end_match = re.search(end_pattern, text[header_match.end():])
    if end_match:
        end = header_match.end() + end_match.start()
    else:
        end = len(text)
    content = text[start:end].strip()
    return content[:max_chars] if max_chars else content


# ── Knowledge Paths ──────────────────────────────────────────────────────────

IDENTITY_PATH = PROJECT_ROOT / "bots" / "setter" / "identity.md"

# Core DM frameworks (always loaded for qualification+)
DM_FRAMEWORKS = [
    PROJECT_ROOT / "SabboOS" / "Agency_OS_DM_Scripts.md",
    PROJECT_ROOT / ".tmp" / "creators" / "hormozi-docx-extractions" / "dm-setting-breakdown.md",
    PROJECT_ROOT / ".tmp" / "creators" / "hormozi-docx-extractions" / "setting-scripts-1.md",
]

# Objection handling (loaded only when qualifying)
OBJECTION_FILES = [
    PROJECT_ROOT / "SabboOS" / "Agency_OS_Objection_Battle_Cards.md",
]

# Mentor brains — Nik Setting's DM frameworks are the primary setting playbook
MENTOR_SECTIONS = {
    # Core DM frameworks from Nik (loaded for qualification+)
    "nik_dm_framework": (
        PROJECT_ROOT / "bots" / "creators" / "nik-setting-brain.md",
        "3.14 Full DM Framework (8 Steps)",
        8000,
    ),
    "nik_conversation_structure": (
        PROJECT_ROOT / "bots" / "creators" / "nik-setting-brain.md",
        "3.15 Conversation Structure (Every Single Text Message)",
        5000,
    ),
    "nik_dm_closing": (
        PROJECT_ROOT / "bots" / "creators" / "nik-setting-brain.md",
        "3.16 DM Closing Framework (No Sales Call)",
        5000,
    ),
    "nik_setter_management": (
        PROJECT_ROOT / "bots" / "creators" / "nik-setting-brain.md",
        "3.13 Setter Management SOP",
        5000,
    ),
    "nik_profile_funnel": (
        PROJECT_ROOT / "bots" / "creators" / "nik-setting-brain.md",
        "2.1 The Profile Funnel",
        5000,
    ),
    "johnny_mau_preframe": (
        PROJECT_ROOT / "bots" / "creators" / "johnny-mau-brain.md",
        "Pre-Frame",
        5000,
    ),
}

# Sales Trainer — stage-specific knowledge files
SALES_TRAINER_FILES = {
    "objection_battle_card": (
        PROJECT_ROOT / ".tmp" / "24-7-profits-sales-optimization.md",
        "DELIVERABLE 2: OBJECTION HANDLING",
        6000,
    ),
    "five_tones": (
        PROJECT_ROOT / ".tmp" / "24-7-profits-sales-optimization.md",
        "The 5 Tones",
        1500,
    ),
    "financial_tiedown": (
        PROJECT_ROOT / ".tmp" / "creators" / "hormozi-docx-extractions" / "tie-downs-1.md",
        "Financial Qualifications",
        3000,
    ),
    "dm_setting_breakdown": (
        PROJECT_ROOT / ".tmp" / "creators" / "hormozi-docx-extractions" / "dm-setting-breakdown.md",
        None,  # Load whole file
        5000,
    ),
}

# ── Claude CLI (Max plan — no API credits needed) ───────────────────────────

def _claude_cli(system: str, user_msg: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 300) -> str:
    """Call Claude via the CLI using the Max subscription.

    Uses `claude -p` (print mode) which reads from stdin and writes to stdout.
    System prompt is prepended to the user message since CLI doesn't have a
    separate system param.
    """
    full_prompt = f"{system}\n\n---\n\n{user_msg}"
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            logger.error("Claude CLI error (rc=%d): %s", proc.returncode, proc.stderr[:200])
            return ""
        return proc.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timeout (30s)")
        return ""
    except FileNotFoundError:
        logger.error("claude CLI not found — install Claude Code or add to PATH")
        return ""


# ── System Prompt Builder ────────────────────────────────────────────────────

def build_system_prompt(
    conversation: Dict,
    prospect: Dict,
    messages: List[Dict],
    offer_key: str = "amazon_os",
) -> str:
    """Build a stage-aware system prompt for the setter.

    Loads knowledge progressively — openers get minimal context,
    qualification gets frameworks, objection handling gets battle cards.
    """
    offer = OFFERS.get(offer_key, OFFERS["amazon_os"])
    stage = conversation.get("stage", "new")
    parts = []

    # ── Block 1: Identity (always loaded, ~2K tokens) ────────────────────
    identity = _load_file(IDENTITY_PATH, max_chars=8000)
    parts.append(f"# YOUR IDENTITY\n\n{identity}")

    # ── Block 2: Offer Context (always loaded, ~1K tokens) ───────────────
    offer_block = f"""# CURRENT OFFER

You are setting for: **{offer['name']}**
Price range: {offer['price_range']}
Closer(s): {', '.join(offer['closer_names'])}
Tone: {offer['dm_tone']}

## ICP (Ideal Customer Profile)
{offer['icp']['description']}

### Tiers:
{chr(10).join(f"- **Tier {k}:** {v}" for k, v in offer['icp']['tiers'].items())}

### Positive Signals:
{chr(10).join(f"- {s}" for s in offer['icp']['signals'])}

### Disqualifiers:
{chr(10).join(f"- {d}" for d in offer['icp']['disqualify'])}
"""
    parts.append(offer_block)

    # ── Block 3: Prospect Profile (always loaded, ~500 tokens) ───────────
    prospect_block = f"""# PROSPECT PROFILE

Handle: @{prospect.get('ig_handle', 'unknown')}
Name: {prospect.get('full_name', 'Unknown')}
Bio: {prospect.get('bio', 'No bio')}
Followers: {prospect.get('follower_count', 0):,}
Following: {prospect.get('following_count', 0):,}
Business account: {'Yes' if prospect.get('is_business') else 'No'}
Category: {prospect.get('category', 'N/A')}
Website: {prospect.get('website', 'N/A')}
Source: {prospect.get('source', 'unknown')} ({prospect.get('source_detail', '')})
ICP Score: {prospect.get('icp_score', 0)}/10
ICP Reasoning: {prospect.get('icp_reasoning', 'Not scored yet')}
"""
    parts.append(prospect_block)

    # ── Block 4: Conversation State (always loaded, ~300 tokens) ─────────
    heat = conversation.get('heat_score', 0)
    state_block = f"""# CONVERSATION STATE

Stage: {stage}
Type: {conversation.get('conversation_type', 'cold_outbound')}
Messages sent: {conversation.get('messages_sent', 0)}
Messages received: {conversation.get('messages_received', 0)}
Heat Score: {heat}/100
Qualification status:
  - Commitment: {'Confirmed' if conversation.get('qual_commitment') else 'Unknown'}
  - Urgency: {'Confirmed' if conversation.get('qual_urgency') else 'Unknown'}
  - Resources: {'Confirmed' if conversation.get('qual_resources') else 'Unknown'}

Heat Score Guide: 0-20 = cold (be casual, low pressure), 21-50 = warming (qualify actively), 51-80 = hot (push toward booking), 81-100 = closing (get them on the calendar NOW).
"""
    parts.append(state_block)

    # ── Block 5: Conversation History (always loaded, smart truncation) ──
    if messages:
        history_lines = ["# CONVERSATION HISTORY\n"]
        total = len(messages)

        if total <= 30:
            # Load everything
            for msg in messages:
                direction = "YOU" if msg["direction"] == "out" else "PROSPECT"
                history_lines.append(f"**{direction}:** {msg['content']}")
        else:
            # First 5 + gap + last 25
            for msg in messages[:5]:
                direction = "YOU" if msg["direction"] == "out" else "PROSPECT"
                history_lines.append(f"**{direction}:** {msg['content']}")
            history_lines.append(f"\n... ({total - 30} earlier messages omitted) ...\n")
            for msg in messages[-25:]:
                direction = "YOU" if msg["direction"] == "out" else "PROSPECT"
                history_lines.append(f"**{direction}:** {msg['content']}")

        parts.append("\n".join(history_lines))

        # ── Block 5b: DO NOT REPEAT list ────────────────────────────
        our_messages = [m['content'] for m in messages if m['direction'] == 'out']
        if our_messages:
            repeat_block = "# DO NOT REPEAT (you already sent these exact messages)\n\n"
            for msg_text in our_messages[-10:]:  # Last 10 outbound
                repeat_block += f"- \"{msg_text[:100]}\"\n"
            repeat_block += "\nNEVER send the same message twice. Always write something fresh."
            parts.append(repeat_block)

    # ── Block 6: DM Frameworks (loaded for qualification+, ~3K tokens) ───
    if stage in ("replied", "qualifying", "qualified", "booking", "nurture"):
        for path in DM_FRAMEWORKS:
            content = _load_file(path, max_chars=5000)
            if content:
                parts.append(f"# DM FRAMEWORK REFERENCE\n\n{content}")
                break  # Load first available framework

    # ── Block 7: Objection Battle Cards (loaded for qualifying+, ~8K) ────
    if stage in ("qualifying", "qualified", "booking"):
        for path in OBJECTION_FILES:
            content = _load_file(path, max_chars=15000)
            if content:
                parts.append(f"# OBJECTION HANDLING REFERENCE\n\n{content}")

        # Load mentor sections — Nik's DM frameworks + Johnny Mau pre-frame
        for key, (path, section, max_chars) in MENTOR_SECTIONS.items():
            section_content = _load_section(path, section, max_chars)
            if section_content:
                parts.append(f"# MENTOR REFERENCE: {key}\n\n{section_content}")

    # ── Block 7b: Nik Setting DM frameworks (loaded for replied+) ───────
    # These load at replied stage too (before qualifying) so the setter
    # knows the full DM flow from first reply onward
    if stage in ("replied", "nurture"):
        for key in ("nik_dm_framework", "nik_conversation_structure"):
            path, section, max_chars = MENTOR_SECTIONS[key]
            section_content = _load_section(path, section, max_chars)
            if section_content:
                parts.append(f"# SETTING FRAMEWORK: {key}\n\n{section_content}")

    # ── Block 7c: Johnny Mau Pre-Frame (loaded for replied stage) ───────
    if stage == "replied":
        path, section, max_chars = MENTOR_SECTIONS["johnny_mau_preframe"]
        section_content = _load_section(path, section, max_chars)
        if section_content:
            parts.append(f"# SALES TRAINER: Pre-Frame Psychology\n\n{section_content}")

    # ── Block 7d: Sales Trainer deep knowledge (qualifying+) ───────────
    if stage in ("qualifying", "qualified", "booking"):
        # Objection battle card + 5 tones
        for key in ("objection_battle_card", "five_tones"):
            path, section, max_chars = SALES_TRAINER_FILES[key]
            if section:
                content = _load_section(path, section, max_chars)
            else:
                content = _load_file(path, max_chars)
            if content:
                parts.append(f"# SALES TRAINER: {key.replace('_', ' ').title()}\n\n{content}")

    # ── Block 7e: Tie-downs (loaded for qualified/booking) ─────────────
    if stage in ("qualified", "booking"):
        path, section, max_chars = SALES_TRAINER_FILES["financial_tiedown"]
        if section:
            content = _load_section(path, section, max_chars)
        else:
            content = _load_file(path, max_chars)
        if content:
            parts.append(f"# SALES TRAINER: Financial Tie-Down\n\n{content}")

    # ── Block 7f: Re-engagement strategies (nurture) ───────────────────
    if stage == "nurture":
        nurture_prompt = """# SALES TRAINER: Re-Engagement Strategies

When a lead goes cold, use ONE of these approaches (rotate, don't repeat):

1. **Value Share** — Send a specific, relevant insight with NO ask attached.
   Example: "saw this and thought of you — [relevant tip about Amazon/their niche]"

2. **Curiosity Hook** — Reference something new or time-sensitive without pitching.
   Example: "we just had a student hit their first $10K month doing [thing relevant to their situation] — crazy stuff"

3. **Direct Check-In** — Casual, no pressure, acknowledge the gap.
   Example: "hey been a min — you still looking into the amazon thing or nah?"

Rules:
- NEVER re-pitch or re-qualify. They already know what you do.
- NEVER guilt trip ("I noticed you didn't respond...")
- Keep it to ONE sentence max. Less is more for re-engagement.
- If they reply → go back to qualification flow from where you left off.
- If no reply after 2 re-engagements → mark dead, revisit in 90 days."""
        parts.append(nurture_prompt)

    # ── Block 8: Winning Patterns (loaded when available, ~500 tokens) ───
    pattern_type_map = {
        "new": "opener",
        "opener_sent": "opener",
        "replied": "qualifier",
        "qualifying": "qualifier",
        "qualified": "booking_bridge",
        "booking": "booking_bridge",
    }
    pt = pattern_type_map.get(stage)
    if pt:
        patterns = db.get_top_patterns(pt, offer=offer_key, limit=3)
        if patterns:
            pattern_block = f"# WINNING PATTERNS ({pt})\n\nThese have the highest success rates:\n"
            for p in patterns:
                pattern_block += f"- (success: {p['success_rate']:.0%}) {p['content']}\n"
            parts.append(pattern_block)

    # ── Block 8b: Sales Trainer Coaching Notes (from audits) ──────────────
    try:
        from .sales_auditor import get_improvement_report
        coaching = get_improvement_report()
        if coaching and len(coaching) > 50:
            parts.append(f"# SALES TRAINER COACHING NOTES (from recent conversation audits)\n\n{coaching}")
    except Exception:
        pass  # Auditor not available, skip

    # ── Block 9: Safety Rules (always loaded, ~300 tokens) ───────────────
    safety_block = f"""# SAFETY RULES

## NEVER discuss these topics in detail — always redirect to the call:
{chr(10).join(f"- {t}" for t in SAFETY['never_discuss'])}

Redirect phrase: "{SAFETY['redirect_phrase'].format(closer=offer['closer_names'][0])}"

## ESCALATE immediately if the prospect mentions any of these:
{chr(10).join(f"- {k}" for k in SAFETY['escalation_keywords'][:8])}

If escalating, respond with: "I appreciate you sharing that — let me connect you with someone who can help with that directly."
Then set requires_human = true.
"""
    parts.append(safety_block)

    # ── Block 10: Sabbo's Exact Script + Instructions ───────────────────── ─────────────────────
    script_block = f"""# SABBO'S DM SCRIPT (use these EXACT words when the conversation reaches each stage)

Stage 1 — Opener (warm new follower — they followed us, rotate these):
{chr(10).join(f'- "{o}"' for o in DM_SCRIPT['opener_cold']) if isinstance(DM_SCRIPT['opener_cold'], list) else f'"{DM_SCRIPT["opener_cold"]}"'}

Stage 1b — Story viewer (never spoken):
"{DM_SCRIPT['opener_story_new']}"

Stage 1c — Story viewer (spoke before / re-engage):
"{DM_SCRIPT['opener_story_reengage']}"

Stage 2 — Qualify interest (after they reply):
"{DM_SCRIPT['qualify_interest']}"

Stage 2b — Clarify (if vague/unclear):
"{DM_SCRIPT['clarify']}"

Stage 3 — Resources check (after they share motivation):
"{DM_SCRIPT['resources_check']}"

Stage 3c — Trigger (amplify need before close):
"{DM_SCRIPT['trigger']}"

Stage 4 — Close (after trigger confirmed):
"{DM_SCRIPT['close']}"

Stage 4b — Reclose (if they say "on my own"):
"{DM_SCRIPT['reclose']}"

Stage 5 — Booking (they pick 1on1):
"{DM_SCRIPT['booking_ask']}"

Stage 5b — Timezone:
"{DM_SCRIPT['timezone']}"

Stage 6 — After they book (send call prep):
"{DM_SCRIPT['post_booking']}"

# YOUR TASK

Generate the next DM message. Current stage: {stage}

## Rules:
- Use the EXACT script above when the conversation naturally reaches that stage.
- Only deviate from the script if: the prospect asks a question, raises an objection, or says something unexpected.
- When deviating: answer briefly in Sabbo's casual tone, then steer back to the next script stage.
- Max 2-3 sentences. This is DM, not email. Sound like a real person texting.
- If the prospect gives their name + email + phone → the conversation is BOOKED. Respond with confirmation.
- If the prospect says "on my own" or "basic info" → use the reclose script.
- If unclear what stage we're at → use the clarify script.
- NEVER pitch, explain the program, or discuss pricing in detail. Redirect to the call.
- NEVER repeat a message you already sent (check the DO NOT REPEAT list above).
- If you're at a stage where the script says to send a specific message but you already sent it — acknowledge their response and move to the NEXT stage naturally.
- EVERY reply MUST end with a question. Acknowledge → answer briefly → ask a follow-up question. If you just answer without asking something back, they'll leave you on seen. You must always lead the conversation.
- {"Generate a personalized opener based on their profile." if stage == "new" else "Continue the conversation using the script flow."}

## Output format:
Return ONLY the DM message text. No explanation, no JSON, no quotes. Just the message.
"""
    parts.append(script_block)

    return "\n\n---\n\n".join(parts)


# ── Response Generation ──────────────────────────────────────────────────────

def generate_response(
    conversation: Dict,
    prospect: Dict,
    messages: List[Dict],
    offer_key: str = "amazon_os",
) -> Dict:
    """Generate a setter response using Claude.

    Returns: {
        content: str,       # The DM text
        model: str,         # Model used
        tokens_in: int,
        tokens_out: int,
        cost: float,
        stage_suggestion: str,  # Suggested next stage
        requires_human: bool,
        human_reason: str,
    }
    """
    stage = conversation.get("stage", "new")
    result = {
        "content": "",
        "model": "",
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0.0,
        "stage_suggestion": stage,
        "requires_human": False,
        "human_reason": "",
        "qual_updates": {},
    }

    # Select model based on stage
    if stage in ("new", "opener_sent"):
        model = MODELS["opener"]
    elif stage in ("qualifying", "qualified", "booking"):
        model = MODELS["qualification"]
    else:
        model = MODELS["qualification"]

    # Check for escalation keywords AND prompt injection in last inbound message
    last_inbound = None
    for msg in reversed(messages):
        if msg["direction"] == "in":
            last_inbound = msg
            break

    if last_inbound:
        raw_content = last_inbound["content"]
        # Normalize unicode: strip zero-width chars, NFKD normalize
        import unicodedata
        normalized = unicodedata.normalize("NFKD", raw_content)
        # Strip zero-width characters and control chars (common injection evasion)
        normalized = re.sub(r'[\u200b-\u200f\u2028-\u202f\ufeff\u00ad]', '', normalized)
        content_lower = normalized.lower()

        # SECURITY: Check for prompt injection attempts
        for pattern in SAFETY.get("injection_patterns", []):
            if pattern.lower() in content_lower:
                result["requires_human"] = True
                result["human_reason"] = f"SECURITY: Possible prompt injection: '{pattern}'"
                result["content"] = ""  # DO NOT respond to injection attempts
                logger.warning("Prompt injection detected from prospect: %s", pattern)
                return result

        # SECURITY: Flag messages with suspicious character distributions
        # (many non-ASCII, control chars, or very long messages from prospects)
        non_ascii_ratio = sum(1 for c in raw_content if ord(c) > 127) / max(len(raw_content), 1)
        if non_ascii_ratio > 0.5 and len(raw_content) > 50:
            result["requires_human"] = True
            result["human_reason"] = f"SECURITY: Suspicious character distribution ({non_ascii_ratio:.0%} non-ASCII)"
            result["content"] = ""
            logger.warning("Suspicious message from prospect: %.0f%% non-ASCII", non_ascii_ratio * 100)
            return result

        # Check for escalation keywords
        for keyword in SAFETY["escalation_keywords"]:
            if keyword in content_lower:
                result["requires_human"] = True
                result["human_reason"] = f"Escalation keyword detected: '{keyword}'"
                result["content"] = "I appreciate you sharing that — let me connect you with someone who can help with that directly."
                return result

    # Build system prompt
    system_prompt = build_system_prompt(conversation, prospect, messages, offer_key)

    # Build user message
    if stage == "new":
        user_msg = (
            f"Generate a personalized opener for @{prospect.get('ig_handle', '')}. "
            f"Their bio: {prospect.get('bio', 'N/A')}. "
            f"Source: {prospect.get('source', 'unknown')}."
        )
    elif last_inbound:
        user_msg = (
            f"The prospect just said: \"{last_inbound['content']}\"\n\n"
            f"Generate your next reply. Follow the qualification flow based on the current stage ({stage})."
        )
    else:
        user_msg = f"Generate the next message in this conversation. Current stage: {stage}."

    try:
        response_text = _claude_cli(system_prompt, user_msg, model=model, max_tokens=300)

        result["content"] = _clean_response(response_text, stage=stage)
        result["model"] = model
        result["tokens_in"] = 0  # CLI doesn't report tokens
        result["tokens_out"] = 0
        result["cost"] = 0.0  # Max plan — no per-token cost

        # Analyze response + prospect's last message for stage progression
        if last_inbound:
            result["stage_suggestion"], result["qual_updates"] = _analyze_stage_progression(
                stage, last_inbound["content"], result["content"], conversation
            )

    except Exception as e:
        logger.error("Brain error: %s", e)
        result["requires_human"] = True
        result["human_reason"] = f"Error: {e}"

    return result


def _clean_response(text: str, stage: str = "") -> str:
    """Clean Claude's response to be DM-ready."""
    # Remove surrounding quotes
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    # Remove "Message:" or "DM:" prefixes
    text = re.sub(r'^(Message|DM|Response|Reply|Setter):\s*', '', text, flags=re.IGNORECASE)
    # Remove markdown formatting
    text = text.replace("**", "").replace("__", "")
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # SECURITY: Sanitize output before sending
    text = _sanitize_output(text, stage=stage)
    return text


def _sanitize_output(text: str, stage: str = "") -> str:
    """Security check on AI-generated output before it gets sent as a DM.

    Catches: sensitive data leaks, excessive length, dangerous content.
    Returns empty string if output is unsafe (will trigger escalation).

    Args:
        stage: conversation stage — booking/booked stages skip phone regex
               because the setter needs to reference prospect-provided booking info.
    """
    # Check for sensitive data patterns (API keys, internal emails, revenue)
    booking_stages = ("booking", "booked", "show")
    for pattern in SAFETY.get("sensitive_data_patterns", []):
        # Skip phone number regex in booking stages — prospect provides their phone
        if stage in booking_stages and r"\d{3}" in pattern:
            continue
        if re.search(pattern, text, re.IGNORECASE):
            logger.error("SECURITY: Sensitive data detected in AI output, blocking send")
            return ""

    # Enforce max DM length
    max_len = SAFETY.get("max_dm_length", 300)
    if len(text) > max_len:
        # Truncate at last sentence boundary
        truncated = text[:max_len]
        last_period = truncated.rfind(".")
        last_question = truncated.rfind("?")
        last_excl = truncated.rfind("!")
        cut = max(last_period, last_question, last_excl)
        if cut > max_len // 2:
            text = truncated[:cut + 1]
        else:
            text = truncated

    # Block if AI tried to generate system-level commands or code
    danger_patterns = [
        r"```", r"import\s+\w+", r"subprocess\.", r"os\.system",
        r"eval\(", r"exec\(", r"<script", r"javascript:",
    ]
    for pat in danger_patterns:
        if re.search(pat, text, re.IGNORECASE):
            logger.error("SECURITY: Dangerous content in AI output: %s", pat)
            return ""

    return text


def _analyze_stage_progression(
    current_stage: str,
    prospect_msg: str,
    our_response: str,
    conversation: Dict,
) -> Tuple[str, Dict]:
    """Determine if the conversation should advance to a new stage.

    Returns: (new_stage, qual_updates_dict)
    """
    msg_lower = prospect_msg.lower()
    qual_updates = {}

    # Negative signals — prospect disengaging
    negative_signals = [
        "not interested", "no thanks", "stop", "leave me alone",
        "don't contact", "unsubscribe", "not for me",
    ]
    for signal in negative_signals:
        if signal in msg_lower:
            return "disqualified", {}

    # Stage-specific progression
    if current_stage == "opener_sent":
        # Any reply means they're engaged
        return "replied", {}

    elif current_stage in ("replied", "qualifying"):
        # Check for commitment signals
        commitment_signals = ["yes", "been trying", "actively", "looking for", "working on", "want to"]
        if any(s in msg_lower for s in commitment_signals) and not conversation.get("qual_commitment"):
            qual_updates["qual_commitment"] = True

        # Check for urgency signals
        urgency_signals = ["asap", "this month", "this quarter", "ready", "now", "soon", "need to", "goal"]
        if any(s in msg_lower for s in urgency_signals) and not conversation.get("qual_urgency"):
            qual_updates["qual_urgency"] = True

        # Check for resource signals — aggressive detection for capital mentions
        resource_signals = ["budget", "saved", "have the money", "set aside", "ready to invest",
                          "capital", "$", "k", "thousand", "credit", "savings", "loan"]
        if any(s in msg_lower for s in resource_signals) and not conversation.get("qual_resources"):
            qual_updates["qual_resources"] = True

        # Check if all 3 qualifiers now met
        c = conversation.get("qual_commitment") or qual_updates.get("qual_commitment")
        u = conversation.get("qual_urgency") or qual_updates.get("qual_urgency")
        r = conversation.get("qual_resources") or qual_updates.get("qual_resources")
        if c and u and r:
            return "qualified", qual_updates

        # Still qualifying
        return "qualifying", qual_updates

    elif current_stage == "qualified":
        # We should be bridging to booking
        return "booking", {}

    elif current_stage == "booking":
        # Check if they confirmed booking
        booking_signals = ["booked", "scheduled", "confirmed", "yes", "done", "see you",
                          "locked in", "all set", "just booked", "got it"]
        if any(s in msg_lower for s in booking_signals):
            return "booked", {}
        # Check if they're sharing contact info (name/email/phone) — booking in progress
        import re as _re
        has_email = bool(_re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', prospect_msg))
        has_phone = bool(_re.search(r'[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}', prospect_msg))
        if has_email or has_phone:
            return "booked", {}

    return current_stage, qual_updates


# ── Opener Generation ────────────────────────────────────────────────────────

def generate_opener(prospect: Dict, offer_key: str = "amazon_os") -> Dict:
    """Get the right opener for a prospect based on source/context.

    Uses Sabbo's exact scripts — no AI generation for openers.
    """
    source = prospect.get("source", "new_follower")

    result = {
        "content": "",
        "model": "script",  # Not AI-generated
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0.0,
    }

    if source == "story_viewer":
        # Check if we've spoken before
        existing = db.get_prospect_by_handle(prospect.get("ig_handle", ""))
        if existing:
            conv = db.get_conversation_by_prospect(existing["id"]) if existing else None
            if conv:
                result["content"] = DM_SCRIPT["opener_story_reengage"]
            else:
                result["content"] = DM_SCRIPT["opener_story_new"]
        else:
            result["content"] = DM_SCRIPT["opener_story_new"]
    elif source == "comment_trigger":
        # AI picks opener based on what they commented
        comment_text = prospect.get("source_detail", "")
        system = f"""Generate a short casual DM opener for someone who commented "{comment_text}" on an Amazon FBA post.
Keep it under 2 sentences. Sound like a friend texting. Reference what they commented.
Example vibe: "yooo i saw your comment — you looking into amazon?"
Return ONLY the message text."""
        try:
            result["content"] = _clean_response(
                _claude_cli(system, f"Comment: {comment_text}", model=MODELS["opener"])
            )
            result["model"] = MODELS["opener"]
        except Exception:
            openers = DM_SCRIPT["opener_cold"]
            result["content"] = openers[0] if isinstance(openers, list) else openers  # Fallback
    else:
        # Default: cold follower opener (rotates from list)
        import random as _rnd
        openers = DM_SCRIPT["opener_cold"]
        if isinstance(openers, list):
            result["content"] = _rnd.choice(openers)
        else:
            result["content"] = openers

    return result


# ── ICP Scoring ──────────────────────────────────────────────────────────────

def score_icp(prospect: Dict) -> Dict:
    """Score a prospect's ICP fit using Haiku.

    Returns: {score: int (1-10), reasoning: str, offer_match: str}
    """
    system = """You are an ICP (Ideal Customer Profile) scorer for two offers:

1. **Amazon OS** — Amazon FBA coaching ($3K-$10K). ICP: People with $5K-$20K capital, motivated by income replacement or asset building. Age 22-45, US/Canada/UK/AU. Signals: entrepreneur, side hustle, Amazon, ecommerce, FBA, financial freedom.

2. **Agency OS** — Done-for-you growth agency ($5K-$25K/mo). ICP: 7-8 figure founders with product-market fit but no repeatable acquisition engine. Has real business, real website, real team.

Score this Instagram profile on a 1-10 scale for ICP fit and identify which offer matches.

OUTPUT FORMAT (exactly this, nothing else):
SCORE: [1-10]
OFFER: [amazon_os|agency_os|both|none]
REASONING: [One sentence explaining the score]"""

    user = (
        f"Handle: @{prospect.get('ig_handle', '')}\n"
        f"Name: {prospect.get('full_name', '')}\n"
        f"Bio: {prospect.get('bio', 'No bio')}\n"
        f"Followers: {prospect.get('follower_count', 0)}\n"
        f"Following: {prospect.get('following_count', 0)}\n"
        f"Business: {'Yes' if prospect.get('is_business') else 'No'}\n"
        f"Category: {prospect.get('category', '')}\n"
        f"Website: {prospect.get('website', '')}"
    )

    result = {"score": 0, "reasoning": "", "offer_match": "none"}

    try:
        text = _claude_cli(system, user, model=MODELS["icp_scoring"], max_tokens=100)

        # Parse structured output
        score_match = re.search(r'SCORE:\s*(\d+)', text)
        offer_match = re.search(r'OFFER:\s*(\w+)', text)
        reason_match = re.search(r'REASONING:\s*(.+)', text)

        if score_match:
            result["score"] = min(10, max(1, int(score_match.group(1))))
        if offer_match:
            result["offer_match"] = offer_match.group(1).strip()
        if reason_match:
            result["reasoning"] = reason_match.group(1).strip()

    except Exception as e:
        logger.error("ICP scoring error: %s", e)

    return result
