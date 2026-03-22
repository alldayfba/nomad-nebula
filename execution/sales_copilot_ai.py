#!/usr/bin/env python3
"""
SalesCopilot — AI Engine

Stage detection (Haiku, <500ms) + suggestion generation (Sonnet, streaming).
Fires suggestions when: prospect stops speaking, question detected, objection
keyword matched, stage transition, or manual hotkey trigger.

Usage:
  python execution/sales_copilot_ai.py --test
"""

from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    import anthropic
    HAS_ANTHROPIC = True
except (ImportError, Exception):
    HAS_ANTHROPIC = False

from sales_copilot_corpus import SalesCorpus, OBJECTION_KEYWORDS, NEPQ_STAGES

# ─── Configuration ───────────────────────────────────────────────────────────

STAGE_MODEL = os.getenv("COPILOT_STAGE_MODEL", "claude-haiku-4-5-20251001")
SUGGEST_MODEL = os.getenv("COPILOT_SUGGEST_MODEL", "claude-sonnet-4-6")
MAX_SUGGEST_TOKENS = int(os.getenv("COPILOT_MAX_TOKENS", "512"))

# AI mode: "api" uses Claude API, "local" uses corpus-only keyword matching
AI_MODE = os.getenv("COPILOT_AI_MODE", "auto")  # auto | api | local

# Trigger thresholds
PROSPECT_SILENCE_TRIGGER = float(os.getenv("COPILOT_SILENCE_TRIGGER", "3.0"))
MIN_SUGGEST_INTERVAL = float(os.getenv("COPILOT_MIN_SUGGEST_INTERVAL", "8.0"))

# Offer mode
OFFER_MODE = os.getenv("COPILOT_OFFER", "amazon")  # amazon | agency


# ─── Stage Detector ──────────────────────────────────────────────────────────

class StageDetector:
    """Classifies the current NEPQ stage. Uses API if available, keyword heuristics as fallback."""

    STAGES = [
        "connecting", "situation", "problem_awareness", "pre_frame",
        "solution_awareness", "consequence", "commitment", "bridge",
        "close", "objection_handling",
    ]

    # Keyword heuristics for local stage detection
    STAGE_KEYWORDS = {
        "connecting": ["how's it going", "thanks for hopping on", "good to meet", "how are you"],
        "situation": ["walk me through", "tell me about", "what do you do", "how long have you", "what's your current"],
        "problem_awareness": ["how's that going", "what would you change", "biggest frustration", "what's been the challenge"],
        "pre_frame": ["what have you done in the past", "what have you tried", "what stopped you", "why didn't it work"],
        "solution_awareness": ["if we could solve", "what would that look like", "imagine if", "picture this"],
        "consequence": ["if nothing changes", "what's that costing you", "how long are you willing", "a year from now"],
        "commitment": ["does this feel right", "on a scale of", "are you ready", "what would it take"],
        "bridge": ["based on what you've told me", "here's what I'd recommend", "let me share"],
        "close": ["how would you like to move forward", "ready to get started", "let's do this", "payment", "zelle", "investment"],
        "objection_handling": ["think about it", "too expensive", "talk to my", "not the right time", "can't afford"],
    }

    def __init__(self, client=None):
        self.client = client
        self.current_stage = "connecting"
        self._lock = threading.Lock()
        self._use_api = client is not None and AI_MODE != "local"

    def detect(self, transcript_text: str) -> str:
        """Classify the call stage from recent transcript."""
        if not transcript_text.strip():
            return self.current_stage

        # Try API first if available
        if self._use_api and self.client:
            try:
                response = self.client.messages.create(
                    model=STAGE_MODEL,
                    max_tokens=50,
                    messages=[{
                        "role": "user",
                        "content": f"""Classify this sales call into ONE stage.
Stages: {', '.join(self.STAGES)}

Transcript (most recent):
{transcript_text[-1500:]}

Reply with ONLY the stage name, nothing else.""",
                    }],
                )
                stage = response.content[0].text.strip().lower().replace(" ", "_")
                if stage in self.STAGES:
                    with self._lock:
                        self.current_stage = stage
                    return stage
            except Exception as e:
                print(f"[SalesCopilot] API stage detection failed, using local: {e}")
                self._use_api = False  # Fall back permanently

        # Local keyword-based detection
        return self._detect_local(transcript_text)

    def _detect_local(self, transcript_text: str) -> str:
        """Detect stage using keyword heuristics."""
        text_lower = transcript_text[-2000:].lower()
        best_stage = self.current_stage
        best_score = 0

        for stage, keywords in self.STAGE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            # Weight recent text more (last 500 chars get 2x)
            recent = transcript_text[-500:].lower()
            score += sum(2 for kw in keywords if kw in recent)
            if score > best_score:
                best_score = score
                best_stage = stage

        if best_score > 0:
            with self._lock:
                self.current_stage = best_stage

        return self.current_stage


# ─── Suggestion Generator ───────────────────────────────────────────────────

class LocalSuggestionGenerator:
    """Generates suggestions from pre-built corpus responses (no API needed)."""

    def __init__(self, corpus: SalesCorpus):
        self.corpus = corpus
        self._last_suggest_time = 0.0
        self._lock = threading.Lock()

    def generate(self, transcript_text: str, stage: str,
                 last_prospect_text: str, on_chunk=None) -> str:
        now = time.time()
        with self._lock:
            if now - self._last_suggest_time < MIN_SUGGEST_INTERVAL:
                return ""
            self._last_suggest_time = now

        parts = []

        # Check for objection first — highest priority
        objection = self.corpus.detect_objection(last_prospect_text)
        if objection:
            category, card = objection
            display = category.replace("_", " ").title()
            parts.append(f"⚠ OBJECTION: {display}\n")
            if card:
                # Extract the "Exact response script" from the card
                lines = card.split("\n")
                in_script = False
                script_lines = []
                for line in lines:
                    if "exact response" in line.lower() or "response script" in line.lower():
                        in_script = True
                        continue
                    if in_script:
                        if line.startswith("**") and not line.startswith("> "):
                            break
                        if line.strip().startswith(">"):
                            script_lines.append(line.strip().lstrip("> ").strip())
                if script_lines:
                    parts.append("1. [Concerned] " + " ".join(script_lines[:3]))
                    parts.append("   (Battle Card Response)\n")

                # Extract "If they push back again"
                in_pushback = False
                pushback_lines = []
                for line in lines:
                    if "push back" in line.lower():
                        in_pushback = True
                        continue
                    if in_pushback:
                        if line.startswith("**") or line.startswith("---"):
                            break
                        if line.strip().startswith(">"):
                            pushback_lines.append(line.strip().lstrip("> ").strip())
                if pushback_lines:
                    parts.append("2. [Challenging] " + " ".join(pushback_lines[:2]))
                    parts.append("   (Pushback Response)\n")

        # Stage-specific suggestions
        stage_info = NEPQ_STAGES.get(stage, {})
        questions = stage_info.get("questions", [])
        tip = stage_info.get("tip", "")

        if not parts:
            # No objection — show stage-appropriate questions
            tones = ["[Curious]", "[Concerned]", "[Challenging]"]
            for i, q in enumerate(questions[:3]):
                parts.append(f"{i+1}. {tones[i % 3]} \"{q}\"")
                parts.append(f"   (NEPQ Stage {stage_info.get('number', '?')})\n")

        if not parts:
            parts.append(f"TIP: {tip}")

        # Add next stage hint
        stage_order = list(NEPQ_STAGES.keys())
        try:
            idx = stage_order.index(stage)
            if idx < len(stage_order) - 1:
                next_stage = NEPQ_STAGES[stage_order[idx + 1]]
                parts.append(f"\n→ NEXT: Stage {next_stage['number']} — {next_stage['name']}")
        except ValueError:
            pass

        result = "\n".join(parts)

        # Stream via callback if provided
        if on_chunk and result:
            on_chunk(result)

        return result


class SuggestionGenerator:
    """Generates real-time response suggestions using Claude Sonnet."""

    def __init__(self, client, corpus: SalesCorpus):
        self.client = client
        self.corpus = corpus
        self._last_suggest_time = 0.0
        self._lock = threading.Lock()

    def generate(self, transcript_text: str, stage: str,
                 last_prospect_text: str, on_chunk=None) -> str:
        """Generate 2-3 suggested responses. Streams if on_chunk callback provided.

        Args:
            transcript_text: Full formatted transcript (last 20 entries)
            stage: Current NEPQ stage
            last_prospect_text: Last few prospect utterances
            on_chunk: Optional callback(str) for streaming text chunks

        Returns:
            Complete suggestion text
        """
        now = time.time()
        with self._lock:
            if now - self._last_suggest_time < MIN_SUGGEST_INTERVAL:
                return ""
            self._last_suggest_time = now

        # Build context-aware system prompt
        corpus_context = self.corpus.get_prompt_for_context(
            stage=stage,
            last_prospect_text=last_prospect_text,
            offer=OFFER_MODE,
        )

        system_prompt = f"""You are a real-time sales call coach for Sabbo, a 21-year-old entrepreneur who runs an Amazon FBA coaching business (Amazon OS, $3K-$10K) and a growth agency (Agency OS, $5K-$25K/mo).

You are watching a LIVE sales call. Your job is to suggest what Sabbo should say next.

{corpus_context}

## YOUR RULES:
- Give exactly 2-3 short response options (1-3 sentences each)
- Number each option (1, 2, 3)
- Include a tonality tag in brackets: [Curious], [Concerned], [Challenging], [Playful], [Confused]
- Reference the framework being used in parentheses (e.g., NEPQ Stage 3, Reason Close, Pre-Frame Callback)
- If you detect an objection, flag it with ⚠ and provide the battle card response
- If Sabbo should ask a question, make it an open-ended question
- If Sabbo is rushing or skipped a stage, flag it with ⏭ STAGE SKIPPED
- Keep it conversational — Sabbo is 21, talks naturally, not corporate
- NEVER suggest something that sounds scripted or salesy
- Be specific to what the prospect just said — don't give generic advice"""

        messages = [{
            "role": "user",
            "content": f"""LIVE CALL TRANSCRIPT:
{transcript_text[-3000:]}

CURRENT STAGE: {stage}
PROSPECT'S LAST WORDS: {last_prospect_text[-500:]}

Generate 2-3 suggested responses for Sabbo to say next.""",
        }]

        try:
            if on_chunk:
                # Streaming mode
                parts = []
                with self.client.messages.stream(
                    model=SUGGEST_MODEL,
                    max_tokens=MAX_SUGGEST_TOKENS,
                    system=system_prompt,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        parts.append(text)
                        on_chunk(text)
                return "".join(parts)
            else:
                # Non-streaming mode
                response = self.client.messages.create(
                    model=SUGGEST_MODEL,
                    max_tokens=MAX_SUGGEST_TOKENS,
                    system=system_prompt,
                    messages=messages,
                )
                return response.content[0].text
        except Exception as e:
            print(f"[SalesCopilot] Suggestion error: {e}")
            return f"[Error generating suggestions: {e}]"


# ─── AI Engine (Orchestrator) ────────────────────────────────────────────────

class AIEngine:
    """Orchestrates stage detection + suggestion generation with trigger logic."""

    def __init__(self, corpus: SalesCorpus):
        self.corpus = corpus
        self.use_api = False
        self.client = None

        # Try to connect to API
        if HAS_ANTHROPIC and AI_MODE != "local":
            try:
                self.client = anthropic.Anthropic()
                # Quick validation — just check key exists
                if os.getenv("ANTHROPIC_API_KEY"):
                    self.use_api = True
                    print("[SalesCopilot] AI mode: API (Claude Sonnet + Haiku)")
                else:
                    print("[SalesCopilot] No ANTHROPIC_API_KEY — using local mode")
            except Exception as e:
                print(f"[SalesCopilot] API init failed: {e} — using local mode")

        if not self.use_api:
            print("[SalesCopilot] AI mode: LOCAL (corpus battle cards + stage coaching)")

        self.stage_detector = StageDetector(self.client if self.use_api else None)

        if self.use_api:
            self.suggestion_gen = SuggestionGenerator(self.client, corpus)
        else:
            self.suggestion_gen = LocalSuggestionGenerator(corpus)

        # State
        self.current_stage = "connecting"
        self.current_suggestions = ""
        self.objection_detected = None  # (category, card_text) or None
        self._generating = False

        # Callbacks
        self.on_stage_change = None  # callback(stage: str)
        self.on_suggestions = None  # callback(text: str)
        self.on_suggestion_chunk = None  # callback(chunk: str)
        self.on_objection = None  # callback(category: str)

    def should_trigger(self, prospect_silence: float, last_prospect_text: str,
                       transcript_text: str) -> str | None:
        """Check if we should trigger suggestion generation.

        Returns trigger reason string or None.
        """
        if self._generating:
            return None

        # 1. Prospect stopped speaking (natural pause)
        if 0 < prospect_silence < 30 and prospect_silence >= PROSPECT_SILENCE_TRIGGER:
            if last_prospect_text.strip():
                return "prospect_pause"

        # 2. Question detected
        if last_prospect_text.strip().endswith("?"):
            return "question"

        # 3. Objection keyword
        objection = self.corpus.detect_objection(last_prospect_text)
        if objection:
            self.objection_detected = objection
            return "objection"

        return None

    def trigger_suggestions(self, transcript_text: str, last_prospect_text: str,
                            reason: str = "manual"):
        """Generate suggestions (runs in background thread)."""
        if self._generating:
            return

        self._generating = True

        def _run():
            try:
                # Detect stage
                new_stage = self.stage_detector.detect(transcript_text)
                if new_stage != self.current_stage:
                    self.current_stage = new_stage
                    if self.on_stage_change:
                        self.on_stage_change(new_stage)

                # Check for objection
                objection = self.corpus.detect_objection(last_prospect_text)
                if objection:
                    self.objection_detected = objection
                    if self.on_objection:
                        self.on_objection(objection[0])

                # Generate suggestions
                def on_chunk(chunk):
                    if self.on_suggestion_chunk:
                        self.on_suggestion_chunk(chunk)

                result = self.suggestion_gen.generate(
                    transcript_text=transcript_text,
                    stage=self.current_stage,
                    last_prospect_text=last_prospect_text,
                    on_chunk=on_chunk,
                )

                self.current_suggestions = result
                if self.on_suggestions:
                    self.on_suggestions(result)

            except Exception as e:
                print(f"[SalesCopilot] AI engine error: {e}")
            finally:
                self._generating = False

        threading.Thread(target=_run, daemon=True).start()

    def force_suggest(self, transcript_text: str, last_prospect_text: str):
        """Force-trigger suggestions (manual hotkey)."""
        self.trigger_suggestions(transcript_text, last_prospect_text, reason="manual")


# ─── Test Mode ───────────────────────────────────────────────────────────────

def test_ai():
    """Test AI engine with a hardcoded transcript."""
    print("\n=== SalesCopilot AI Test ===\n")

    corpus = SalesCorpus()
    corpus.load()

    engine = AIEngine(corpus)

    # Test transcript
    transcript = """[Sabbo] Hey what's up, how's it going? Thanks for hopping on the call.
[Prospect] Yeah good, thanks for having me. I've been looking into Amazon FBA for a while now.
[Sabbo] Cool, so what made you reach out? What's been going on?
[Prospect] Well I've been watching YouTube videos for like 6 months trying to figure out how to start. I spent about $2,000 on a course last year but it was just a bunch of pre-recorded videos and I never really made any progress. I've been burned before by these online coaches and I'm just not sure if it's worth trying again honestly.
[Sabbo] I hear you. So you've tried this before and it didn't work out. What do you think was the main reason it didn't work?
[Prospect] I think I just didn't have anyone to actually guide me through it. The course was fine but when I had questions there was nobody there. I'd post in the Facebook group and get nothing back."""

    last_prospect = "I think I just didn't have anyone to actually guide me through it. The course was fine but when I had questions there was nobody there."

    print("Detecting stage...")
    stage = engine.stage_detector.detect(transcript)
    print(f"  Stage: {stage}\n")

    print("Checking objections...")
    objection = corpus.detect_objection(last_prospect)
    if objection:
        print(f"  Objection: {objection[0]}")
    else:
        print("  No objection detected")

    print("\nGenerating suggestions (streaming)...\n")

    def on_chunk(chunk):
        sys.stdout.write(chunk)
        sys.stdout.flush()

    result = engine.suggestion_gen.generate(
        transcript_text=transcript,
        stage=stage,
        last_prospect_text=last_prospect,
        on_chunk=on_chunk,
    )

    print(f"\n\nTotal suggestion length: {len(result)} chars")
    print("\nAI test PASSED.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_ai()
    else:
        print("Usage: python execution/sales_copilot_ai.py --test")
