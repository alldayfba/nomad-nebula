"""Training Cog — /training, /roleplay, /battle-card, /standup, /script, /training-save, /training-library, /training-push commands."""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from .database import BotDatabase
from .security import RateLimiter, filter_output, is_admin, sanitize_input
from .system_prompt import build_system_prompt

DB_PATH = Path(__file__).parent.parent.parent / ".tmp" / "discord" / "nova_sales_learning.db"

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

# ── Constants ────────────────────────────────────────────────────────────────

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# Weekly training rotation
DAILY_TRAINING = {
    0: ("Opening & First Impressions", "Monday"),
    1: ("Discovery & NEPQ", "Tuesday"),
    2: ("Pitch & Presentation", "Wednesday"),
    3: ("Objection Handling & Closing", "Thursday"),
    4: ("Game Film & Call Review", "Friday"),
    5: ("Mindset & Fundamentals", "Saturday"),
    6: ("Review & Prep", "Sunday"),
}

# Common objection scenarios for random roleplay
COMMON_SCENARIOS = [
    "Price too high",
    "Need to think about it",
    "Talk to my partner",
    "Not the right time",
    "Already working with someone else",
    "Send me more info",
]


def _split_message(text: str, max_len: int = 1900) -> list:
    """Split a long message into chunks that fit Discord's 2000-char limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = text.rfind(" ", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


class TrainingCog(commands.Cog):
    """Sales training commands — daily modules, role plays, battle cards, scripts."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.rate_limiter = RateLimiter()
        self.system_prompt = build_system_prompt()
        self.admin_role_id = os.getenv("DISCORD_SALES_ADMIN_ROLE_ID", "")

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if AsyncAnthropic and api_key:
            self.claude = AsyncAnthropic(api_key=api_key)
        else:
            self.claude = None

        # Training library — persistent SQLite store for saved training modules
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.training_conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        self.training_conn.row_factory = sqlite3.Row
        self.training_conn.execute("""
            CREATE TABLE IF NOT EXISTS training_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                day TEXT,
                content TEXT NOT NULL,
                created_by TEXT,
                approved INTEGER DEFAULT 1,
                uses INTEGER DEFAULT 0,
                rating_sum INTEGER DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.training_conn.commit()

    def _check_admin(self, interaction):
        return is_admin(interaction, self.admin_role_id)

    async def _call_claude(self, prompt: str, model: str, max_tokens: int = 1000) -> str:
        """Call Claude with the sales system prompt. Returns response text or error string."""
        if not self.claude:
            return "AI is temporarily unavailable. Check that ANTHROPIC_API_KEY is set."

        try:
            response = await self.claude.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            reply = response.content[0].text
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            self.db.log_audit("system", "training_api_call",
                              f"model={model} in={tokens_in} out={tokens_out}")
            return reply
        except Exception as e:
            self.db.log_audit("system", "api_error", str(e)[:500])
            return f"Something went wrong calling the AI: {str(e)[:200]}"

    async def _send_chunks(self, interaction, text: str, header: str = ""):
        """Send a potentially long response as chunked followup messages."""
        full_text = f"{header}\n\n{text}".strip() if header else text
        filtered, _ = filter_output(full_text)
        chunks = _split_message(filtered)
        for chunk in chunks:
            await interaction.followup.send(chunk)

    # ── /training ─────────────────────────────────────────────────────────────

    @app_commands.command(name="training", description="Post today's training module based on day of week")
    async def training(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        # Rate limit: 1 per user per 30 minutes
        if not self.rate_limiter.check(str(interaction.user.id), "training"):
            await interaction.followup.send(
                "Training is rate-limited to once per 30 minutes. Come back soon.",
                ephemeral=True
            )
            return

        weekday = datetime.utcnow().weekday()
        topic, day_name = DAILY_TRAINING.get(weekday, ("Fundamentals", "Today"))

        prompt = (
            f"Generate a focused 5-minute training exercise for today's topic: {topic}.\n\n"
            f"Include:\n"
            f"1. One key framework or concept (named, with a 2-3 sentence explanation)\n"
            f"2. One script snippet (exact words to say — format as a dialogue or monologue)\n"
            f"3. One drill the rep can do solo right now (specific, actionable, under 5 minutes)\n\n"
            f"Be specific. No fluff. Reps are busy. Make every word count."
        )

        reply = await self._call_claude(prompt, HAIKU_MODEL, max_tokens=800)
        header = f"**Daily Training — {day_name}: {topic}**"
        await self._send_chunks(interaction, reply, header)

        self.db.log_audit(str(interaction.user.id), "training_command",
                          f"day={day_name} topic={topic}")

    # ── /roleplay ─────────────────────────────────────────────────────────────

    @app_commands.command(name="roleplay", description="Generate a role play scenario for practice")
    @app_commands.describe(scenario="Optional: e.g. 'price objection', 'decision maker not on call'")
    async def roleplay(self, interaction: discord.Interaction, scenario: str = None):
        await interaction.response.defer(thinking=True)

        # Use provided scenario or pick a random common one
        if not scenario:
            scenario = random.choice(COMMON_SCENARIOS)
        else:
            sanitized, is_injection = sanitize_input(scenario)
            if is_injection:
                self.db.log_audit(str(interaction.user.id), "injection_attempt", scenario[:500])
                await interaction.followup.send(
                    "Invalid input. Please describe a sales scenario.",
                    ephemeral=True
                )
                return
            scenario = sanitized[:200]

        prompt = (
            f"Generate a realistic role play scenario for a sales call. Scenario: {scenario}\n\n"
            f"Include:\n"
            f"1. Prospect background (2 sentences — name, situation, what they want)\n"
            f"2. Their opening objection (exact words they say)\n"
            f"3. Three likely follow-up objections if not handled (bullet list)\n"
            f"4. Success criteria (what does a good close look like here?)\n\n"
            f"Use the NEPQ framework as the guide for how to handle this scenario. "
            f"Format clearly with bold headers. Keep it tight — this is for practice, not reading."
        )

        reply = await self._call_claude(prompt, SONNET_MODEL, max_tokens=700)
        header = f"**Role Play: {scenario}**"
        await self._send_chunks(interaction, reply, header)

        self.db.log_audit(str(interaction.user.id), "roleplay_command", f"scenario={scenario[:100]}")

    # ── /battle-card ──────────────────────────────────────────────────────────

    @app_commands.command(name="battle-card", description="Pull an objection battle card with exact word tracks")
    @app_commands.describe(objection="The objection to handle — e.g. 'price too high', 'need to think'")
    async def battle_card(self, interaction: discord.Interaction, objection: str):
        await interaction.response.defer(thinking=True)

        sanitized, is_injection = sanitize_input(objection)
        if is_injection or not sanitized:
            await interaction.followup.send(
                "Invalid input. Please enter a real sales objection.",
                ephemeral=True
            )
            return
        objection_clean = sanitized[:200]

        prompt = (
            f"Create a battle card for this objection: '{objection_clean}'\n\n"
            f"Include:\n"
            f"1. Reframe/acknowledge (1-2 sentences — validate without agreeing)\n"
            f"2. NEPQ question to ask (exact phrasing — make it open-ended and curious)\n"
            f"3. Word track (exact script — what to say word for word)\n"
            f"4. Tone guidance (which of the 5 tones to use and why)\n\n"
            f"Keep it under 200 words. Reps need to be able to glance at this mid-call."
        )

        reply = await self._call_claude(prompt, SONNET_MODEL, max_tokens=400)
        header = f"**Battle Card: {objection_clean}**"
        await self._send_chunks(interaction, reply, header)

        self.db.log_audit(str(interaction.user.id), "battle_card_command",
                          f"objection={objection_clean[:100]}")

    # ── /standup ──────────────────────────────────────────────────────────────

    @app_commands.command(name="standup", description="[Admin] Post the morning standup digest")
    async def standup(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        weekday = datetime.utcnow().weekday()
        topic, day_name = DAILY_TRAINING.get(weekday, ("Fundamentals", "Today"))
        today_str = datetime.utcnow().strftime("%A, %B %d")

        prompt = (
            f"Generate a morning standup message for the sales team.\n\n"
            f"Today is {today_str}. Today's training focus: {topic}.\n\n"
            f"Include:\n"
            f"1. Today's training focus (one sentence — what they're drilling today)\n"
            f"2. One mindset quote from Alex Hormozi or Leila Hormozi philosophy "
            f"(their words or paraphrase — cite the framework, not the person by name)\n"
            f"3. One daily target reminder (specific metric — e.g. '80%+ show rate', "
            f"'3 new bookings minimum', 'every call gets a hard close attempt')\n"
            f"4. A punchy call to action (one sentence — make them want to pick up the phone)\n\n"
            f"Total under 150 words. High energy. No fluff."
        )

        reply = await self._call_claude(prompt, HAIKU_MODEL, max_tokens=300)
        header = f"**Morning Standup — {today_str}**"
        await self._send_chunks(interaction, reply, header)

        self.db.log_audit(str(interaction.user.id), "standup_command", f"date={today_str}")

    # ── /script ───────────────────────────────────────────────────────────────

    @app_commands.command(name="script", description="Look up a script section or word track by topic")
    @app_commands.describe(topic="Script topic — e.g. 'pre-frame', 'discovery questions', 'price close'")
    async def script(self, interaction: discord.Interaction, topic: str):
        await interaction.response.defer(thinking=True)

        sanitized, is_injection = sanitize_input(topic)
        if is_injection or not sanitized:
            await interaction.followup.send(
                "Invalid input. Please enter a sales script topic.",
                ephemeral=True
            )
            return
        topic_clean = sanitized[:200]

        prompt = (
            f"The rep is asking about this sales script topic: '{topic_clean}'\n\n"
            f"Pull the relevant script, word track, or framework from the Sales Manager training library. "
            f"Give them the exact language to use — word for word where possible.\n\n"
            f"Format:\n"
            f"- Context (when to use this, 1 sentence)\n"
            f"- The script or word track (exact language, clearly formatted)\n"
            f"- Tone note (how to deliver it)\n\n"
            f"Be specific. If you don't have an exact script for this, give the closest framework "
            f"from the training library and say which file it comes from."
        )

        reply = await self._call_claude(prompt, SONNET_MODEL, max_tokens=600)
        header = f"**Script: {topic_clean}**"
        await self._send_chunks(interaction, reply, header)

        self.db.log_audit(str(interaction.user.id), "script_command", f"topic={topic_clean[:100]}")


    # ── /training-save ─────────────────────────────────────────────────────

    @app_commands.command(name="training-save", description="[Admin] Save a training module to the library")
    @app_commands.describe(
        title="Training title",
        topic="Topic (opening/discovery/pitch/close/gamefilm)",
        content="Training content",
    )
    async def training_save(self, interaction: discord.Interaction, title: str, topic: str, content: str):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        self.training_conn.execute(
            "INSERT INTO training_library (title, topic, content, created_by) VALUES (?, ?, ?, ?)",
            (title, topic.lower(), content, interaction.user.display_name),
        )
        self.training_conn.commit()
        self.db.log_audit(str(interaction.user.id), "training_save", f"title={title} topic={topic}")
        await interaction.followup.send(f"Saved: **{title}** ({topic})", ephemeral=True)

    # ── /training-library ────────────────────────────────────────────────

    @app_commands.command(name="training-library", description="Browse saved training modules")
    @app_commands.describe(topic="Filter by topic (optional)")
    async def training_library(self, interaction: discord.Interaction, topic: str = None):
        params = []
        query = "SELECT id, title, topic, day, uses, created_at FROM training_library WHERE approved = 1"
        if topic:
            query += " AND topic = ?"
            params.append(topic.lower())
        query += " ORDER BY uses DESC LIMIT 15"
        rows = self.training_conn.execute(query, params).fetchall()

        if not rows:
            await interaction.response.send_message("No training modules found.", ephemeral=True)
            return

        lines = ["**Training Library**\n"]
        for r in rows:
            lines.append(f"- **#{r['id']}** {r['title']} ({r['topic']}) -- used {r['uses']}x")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ── /training-push ───────────────────────────────────────────────────

    @app_commands.command(name="training-push", description="[Admin] Post a training module from the library")
    @app_commands.describe(training_id="Training ID number", channel="Channel to post in")
    async def training_push(self, interaction: discord.Interaction, training_id: int, channel: discord.TextChannel):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        row = self.training_conn.execute(
            "SELECT * FROM training_library WHERE id = ?", (training_id,)
        ).fetchone()
        if not row:
            await interaction.response.send_message(f"Training #{training_id} not found.", ephemeral=True)
            return

        self.training_conn.execute(
            "UPDATE training_library SET uses = uses + 1 WHERE id = ?", (training_id,)
        )
        self.training_conn.commit()

        await channel.send(f"**Training: {row['title']}**\n_{row['topic'].title()}_\n\n{row['content']}")
        await interaction.response.send_message(f"Posted to #{channel.name}", ephemeral=True)

        self.db.log_audit(str(interaction.user.id), "training_push",
                          f"id={training_id} channel={channel.name}")


async def setup(bot):
    await bot.add_cog(TrainingCog(bot))
