#!/usr/bin/env python3
"""
SalesCopilot — Sales Training Corpus Loader

Loads and indexes the sales training library for real-time AI suggestions.
Three-tier system:
  Tier 1: Always in prompt (~15K tokens) — NEPQ stages, closes, tones, rules
  Tier 2: Stage-specific (~5-10K tokens) — loaded based on current call stage
  Tier 3: Never sent — raw transcripts, management docs (too large)

Usage:
  python execution/sales_copilot_corpus.py --test
"""

from __future__ import annotations

import os
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Objection Keywords → Battle Card Index ──────────────────────────────────

# Map keywords/phrases to objection categories for real-time detection
OBJECTION_KEYWORDS = {
    # Trust / Past Experience
    "already have an agency": "trust_already_have_agency",
    "have an agency": "trust_already_have_agency",
    "got burned": "trust_burned_before",
    "burned before": "trust_burned_before",
    "bad experience": "trust_burned_before",
    "burned by": "trust_burned_before",
    "tried before": "trust_burned_before",
    "didn't work": "trust_burned_before",
    "ghost": "trust_ghosting",
    "disappear": "trust_ghosting",
    "references": "trust_want_references",
    "case studies": "trust_want_references",
    "trial": "trust_trial_period",
    "test it out": "trust_trial_period",

    # Money / Budget
    "too expensive": "money_too_expensive",
    "can't afford": "money_cant_afford",
    "afford it": "money_cant_afford",
    "budget": "money_budget",
    "not in the budget": "money_budget",
    "see results first": "money_results_first",
    "pay for performance": "money_results_first",
    "smaller scope": "money_smaller_scope",
    "start small": "money_smaller_scope",

    # Timing / Decision
    "think about it": "timing_think_about_it",
    "need to think": "timing_think_about_it",
    "sleep on it": "timing_think_about_it",
    "talk to my partner": "timing_talk_to_partner",
    "talk to my spouse": "timing_talk_to_partner",
    "talk to my wife": "timing_talk_to_partner",
    "talk to my husband": "timing_talk_to_partner",
    "too busy": "timing_too_busy",
    "not the right time": "timing_not_right_time",
    "bad timing": "timing_not_right_time",
    "maybe later": "timing_not_right_time",
    "next month": "timing_not_right_time",
    "next quarter": "timing_not_right_time",

    # Scope / Fit
    "don't understand my industry": "fit_industry",
    "different industry": "fit_industry",
    "keep it in-house": "fit_inhouse",
    "hire someone": "fit_inhouse",
    "what if it doesn't work": "fit_guarantee",
    "guarantee": "fit_guarantee",

    # Comparison
    "what makes you different": "comparison_different",
    "hire in-house": "comparison_inhouse",

    # Amazon-Specific
    "youtube is free": "amazon_youtube_free",
    "free on youtube": "amazon_youtube_free",
    "learn this on youtube": "amazon_youtube_free",
    "watch youtube": "amazon_youtube_free",
    "just youtube": "amazon_youtube_free",
    "saturated": "amazon_saturated",
    "too competitive": "amazon_saturated",
    "not enough capital": "amazon_no_capital",
    "don't have the money": "amazon_no_capital",
}


# ─── NEPQ Stage Definitions ─────────────────────────────────────────────────

NEPQ_STAGES = {
    "connecting": {
        "number": 1,
        "name": "Connecting",
        "tip": "Build rapport. Get micro-commitment: 'Are you in a spot to talk 30-40 min?'",
        "questions": [
            "Are you in a good spot to chat for about 30-40 minutes?",
            "How's your day going so far?",
            "What made you reach out / book the call?",
        ],
    },
    "situation": {
        "number": 2,
        "name": "Situation",
        "tip": "Discover current state. Ask about revenue, team, channels, what they've tried.",
        "questions": [
            "Walk me through your day-to-day right now.",
            "How long have you been at this?",
            "What does your current process look like?",
        ],
    },
    "problem_awareness": {
        "number": 3,
        "name": "Problem Awareness",
        "tip": "Identify the gap. Use: 'How's that going honestly?'",
        "questions": [
            "How's that going honestly?",
            "What would you change if you could?",
            "What's been the biggest frustration?",
        ],
    },
    "pre_frame": {
        "number": 4,
        "name": "Pre-Frame (Revealing Question)",
        "tip": "Ask: 'What have you done in the past to reach this goal?' — surfaces limiting beliefs.",
        "questions": [
            "What have you done in the past to try to solve this?",
            "What happened when you tried that?",
            "What do you think stopped it from working?",
        ],
    },
    "solution_awareness": {
        "number": 5,
        "name": "Solution Awareness",
        "tip": "Future pace: 'If we solved X, what would that look like for you?'",
        "questions": [
            "If we could solve that problem, what would your life look like?",
            "What would change in your business if this was handled?",
            "How would it feel to not have to worry about that anymore?",
        ],
    },
    "consequence": {
        "number": 6,
        "name": "Consequence",
        "tip": "Inaction cost: 'A year from now, if nothing changes, where will you be?'",
        "questions": [
            "If you don't fix this, where do you see yourself in 12 months?",
            "What is this costing you right now — per month?",
            "How long are you willing to let this continue?",
        ],
    },
    "commitment": {
        "number": 7,
        "name": "Commitment",
        "tip": "Decision test: 'Does this feel like the right move?'",
        "questions": [
            "Based on everything we've discussed, does this feel like the right move?",
            "On a scale of 1-10, where are you at?",
            "What would need to happen for you to feel confident moving forward?",
        ],
    },
    "bridge": {
        "number": 8,
        "name": "Transition to Pitch",
        "tip": "Bridge: 'Based on what you've told me, here's what I'd recommend...'",
        "questions": [],
    },
    "close": {
        "number": 9,
        "name": "Close",
        "tip": "Ask: 'How would you like to move forward?' Then be silent.",
        "questions": [
            "How would you like to move forward?",
            "What would make this a no-brainer for you?",
        ],
    },
    "objection_handling": {
        "number": 10,
        "name": "Objection Handling",
        "tip": "Reframe the thinking, not the person. Consequence the inaction. Identity shift.",
        "questions": [],
    },
}


# ─── Tier 1: Always-On Prompt ────────────────────────────────────────────────

TIER1_PROMPT = """## SALES COACHING FRAMEWORKS (Always Active)

### NEPQ 9-Stage Structure
| # | Stage | Key Question |
|---|---|---|
| 1 | Connecting | "Are you in a spot to talk 30-40 min?" |
| 2 | Situation | "Walk me through your day-to-day" |
| 3 | Problem Awareness | "How's that going honestly?" |
| 4 | Pre-Frame | "What have you done in the past to reach this goal?" |
| 5 | Solution Awareness | "If we solved X, what would that look like?" |
| 6 | Consequence | "A year from now, if nothing changes..." |
| 7 | Commitment | "Does this feel like the right move?" |
| 8 | Bridge | "Based on what you've told me, here's what I'd recommend..." |
| 9 | Close | "How would you like to move forward?" |

### The 5 Tones (JP Egan)
- **Curious** — genuine interest, chin up, open. Use during discovery (Stages 2-4).
- **Confused** — head tilt, slower pace, "help me understand." Use when prospect contradicts themselves.
- **Concerned** — lean in, lower voice, slow down. Use when discussing costs/consequences (Stage 6).
- **Challenging** — direct, steady, not aggressive. Use when prospect deflects or gives smokescreens.
- **Playful** — smile in voice, casual. Use during rapport (Stage 1) and to break tension.

### 7 All-Purpose Closes (Hormozi)
1. **Main Concern Close:** "What's the main thing holding you back?" → Handle that one thing.
2. **Reason Close:** "The fact that you can't afford it IS the reason you need this."
3. **Hypothetical Close:** "If money wasn't a factor, would you do this?"
4. **Zoom Out Close:** "In 5 years, will this $X matter? Will NOT doing this matter?"
5. **1-10 Scale Close:** "On a scale of 1-10, where are you? What would make it a 10?"
6. **Best/Worst Case Close:** "Best case — changes your life. Worst case — you learn a ton."
7. **Card Not On Me Close:** "I didn't bring my wallet either. We'll figure out the money. Is this what you want?"

### 28 Rules of Closing (Condensed)
- Never sell past the close. When they say yes, STOP TALKING.
- The person who speaks first after the price loses.
- Objections are buying signals. They're still talking = still interested.
- Frame every investment against the cost of NOT acting.
- Ask for the sale directly. Don't hint. Don't hope. Ask.
- Urgency must be real. Never manufacture fake scarcity.
- The close starts in the first 5 minutes, not the last 5.
- If you wouldn't buy your own product, fix the product.
- Price is never the real objection. It's always value or trust.

### Smokescreens vs Real Objections
- If objection appears suddenly at close but wasn't mentioned during discovery → smokescreen.
- If you resolve one concern and they immediately produce another → first was smokescreen.
- Surface the real objection: "Is that the main thing, or is there something else giving you pause?"

### Key Objection Word Tracks
| Objection | Response |
|---|---|
| "I need to think" | "What specifically? Let's work through it right now." + Callback to Stage 4 limiting belief. |
| "Too expensive" | Reason Close: "That's exactly why you need this. How long do you want that to be your reality?" |
| "Talk to spouse/partner" | "What questions will they have? Let's prep you. Want to do a 3-way call?" |
| "Been burned before" | "What went wrong? ... Here's specifically how this is structurally different." |
| "Not the right time" | "When would be? What would change? The busyness IS the reason to start now." |
| "YouTube is free" | "YouTube teaches information. We teach accountability to results. That's why you're still watching." |
| "Market is saturated" | "Amazon did $600B+ last year. More products than sellers. The issue is knowing where to look." |

### The Revealing Question (Johnny Mau Pre-Frame)
Ask in Stage 4: "What have you done in the past to try to reach this goal?"
- If they say "nothing" → "What stopped you?" → Extract fear/belief → Reference it during close.
- If they say something → "What happened?" → "Why did it stop working?" → Their own words become your close ammunition.
- The pre-frame callback dissolves objections: "Remember when you told me [their own words]? This is that pattern showing up again."
"""


# ─── Corpus Loader ───────────────────────────────────────────────────────────

class SalesCorpus:
    """Loads and indexes the sales training library for real-time AI suggestions."""

    def __init__(self):
        self.tier1_prompt = TIER1_PROMPT
        self.stage_content: dict[str, str] = {}
        self.objection_cards: dict[str, str] = {}
        self._loaded = False

    def load(self):
        """Load Tier 2 content from disk."""
        if self._loaded:
            return

        # Load battle cards
        self._load_battle_cards()

        # Load stage-specific content
        self._load_stage_content()

        self._loaded = True
        print(f"[SalesCopilot] Corpus loaded: {len(self.objection_cards)} battle cards, {len(self.stage_content)} stage prompts")

    def _load_battle_cards(self):
        """Parse battle cards from Agency_OS_Objection_Battle_Cards.md."""
        cards_path = PROJECT_ROOT / "SabboOS" / "Agency_OS_Objection_Battle_Cards.md"
        if not cards_path.exists():
            print(f"[SalesCopilot] Battle cards not found at {cards_path}")
            return

        content = cards_path.read_text()

        # Split by ### headers (each is a battle card)
        sections = re.split(r'^### ', content, flags=re.MULTILINE)
        for section in sections[1:]:  # Skip preamble
            lines = section.strip().split('\n')
            title = lines[0].strip().strip('"')
            full_card = '\n'.join(lines)

            # Map to objection categories
            title_lower = title.lower()
            for keyword, category in OBJECTION_KEYWORDS.items():
                if keyword in title_lower:
                    self.objection_cards[category] = full_card
                    break
            else:
                # Store by title slug as fallback
                slug = re.sub(r'[^a-z0-9]+', '_', title_lower).strip('_')
                self.objection_cards[slug] = full_card

    def _load_stage_content(self):
        """Load stage-specific coaching content."""
        # Pre-frame psychology (Stages 1-4)
        mau_path = PROJECT_ROOT / "bots" / "creators" / "johnny-mau-brain.md"
        if mau_path.exists():
            mau_content = mau_path.read_text()
            # Extract the revealing question section
            revealing_match = re.search(
                r'(?:Revealing Question|Pre-Frame).*?(?=\n## |\Z)',
                mau_content, re.DOTALL | re.IGNORECASE
            )
            if revealing_match:
                self.stage_content["pre_frame"] = revealing_match.group()[:3000]

        # Amazon-specific closer script (all stages)
        amazon_script = PROJECT_ROOT / "clients" / "kd-amazon-fba" / "scripts" / "closing-call-script.md"
        if amazon_script.exists():
            script = amazon_script.read_text()
            # Store first 4000 chars as reference
            self.stage_content["amazon_script"] = script[:4000]

        # Agency closer script
        agency_script = PROJECT_ROOT / "SabboOS" / "Agency_OS_Closer_Script.md"
        if agency_script.exists():
            script = agency_script.read_text()
            self.stage_content["agency_script"] = script[:4000]

    def detect_objection(self, text: str) -> tuple[str, str] | None:
        """Detect if text contains an objection. Returns (category, card_text) or None."""
        text_lower = text.lower()
        for keyword, category in OBJECTION_KEYWORDS.items():
            if keyword in text_lower:
                card = self.objection_cards.get(category, "")
                return (category, card)
        return None

    def get_prompt_for_context(self, stage: str, last_prospect_text: str, offer: str = "amazon") -> str:
        """Build the optimal prompt given current call state."""
        parts = [self.tier1_prompt]

        # Add stage-specific content
        stage_info = NEPQ_STAGES.get(stage, {})
        if stage_info:
            parts.append(f"\n## CURRENT STAGE: {stage_info.get('name', stage)} (Stage {stage_info.get('number', '?')}/9)")
            parts.append(f"**Coaching tip:** {stage_info.get('tip', '')}")
            questions = stage_info.get("questions", [])
            if questions:
                parts.append("**Suggested questions:**")
                for q in questions:
                    parts.append(f"- {q}")

        # Add pre-frame content for early stages
        if stage in ("connecting", "situation", "problem_awareness", "pre_frame"):
            if "pre_frame" in self.stage_content:
                parts.append(f"\n## PRE-FRAME PSYCHOLOGY (Johnny Mau)")
                parts.append(self.stage_content["pre_frame"][:2000])

        # Add offer-specific script reference
        script_key = f"{offer}_script"
        if script_key in self.stage_content:
            parts.append(f"\n## REFERENCE: {offer.upper()} CLOSER SCRIPT (excerpt)")
            parts.append(self.stage_content[script_key][:2000])

        # Check for objections in prospect's last words
        objection = self.detect_objection(last_prospect_text)
        if objection:
            category, card = objection
            parts.append(f"\n## ⚠ OBJECTION DETECTED: {category.replace('_', ' ').title()}")
            if card:
                parts.append(card[:2000])

        return "\n\n".join(parts)

    def get_stage_info(self, stage: str) -> dict:
        """Get stage info for overlay display."""
        return NEPQ_STAGES.get(stage, {
            "number": "?",
            "name": stage.replace("_", " ").title(),
            "tip": "",
            "questions": [],
        })


# ─── Test Mode ───────────────────────────────────────────────────────────────

def test_corpus():
    """Test corpus loading and objection detection."""
    print("\n=== SalesCopilot Corpus Test ===\n")

    corpus = SalesCorpus()
    corpus.load()

    print(f"Tier 1 prompt length: {len(corpus.tier1_prompt)} chars (~{len(corpus.tier1_prompt)//4} tokens)")
    print(f"Battle cards loaded: {len(corpus.objection_cards)}")
    print(f"Stage content loaded: {len(corpus.stage_content)}")

    # Test objection detection
    test_phrases = [
        "I need to think about it",
        "That's way too expensive for me",
        "I need to talk to my wife first",
        "We already have an agency handling this",
        "I can just learn this on YouTube for free",
        "The market is too saturated",
        "I've been burned before by coaches",
        "This sounds interesting, tell me more",  # No objection
    ]

    print("\nObjection detection tests:")
    for phrase in test_phrases:
        result = corpus.detect_objection(phrase)
        if result:
            cat, _ = result
            print(f"  '{phrase}' → {cat}")
        else:
            print(f"  '{phrase}' → (no objection)")

    # Test prompt building
    print("\nPrompt for 'problem_awareness' stage:")
    prompt = corpus.get_prompt_for_context(
        stage="problem_awareness",
        last_prospect_text="We've tried agencies before and got burned. We spent like 40K and got nothing.",
        offer="agency",
    )
    print(f"  Length: {len(prompt)} chars (~{len(prompt)//4} tokens)")
    print(f"  Contains objection card: {'OBJECTION DETECTED' in prompt}")

    print("\nCorpus test PASSED.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_corpus()
    else:
        print("Usage: python execution/sales_copilot_corpus.py --test")
