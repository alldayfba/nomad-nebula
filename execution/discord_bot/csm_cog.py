"""CSM Cog — Customer Success Manager for Amazon FBA coaching students.

Silent activity tracking, weekly check-ins, win celebrations, stuck flags, referrals.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"

# Keywords that signal frustration (checked case-insensitive)
FRUSTRATED_KEYWORDS = [
    "stuck", "confused", "lost", "quit", "give up", "frustrated",
    "can't figure", "not working", "broken", "impossible", "no idea",
    "overwhelmed", "want to quit", "giving up",
]

# Per-milestone tips for /stuck
MILESTONE_TIPS = {
    "niche_selected": (
        "Niche selection paralysis is the #1 blocker. Here's the fix:\n"
        "1. Pick 3 niches that meet the criteria (demand + low competition + margin)\n"
        "2. Spend 30 min researching each on Amazon\n"
        "3. Pick the one with the clearest path to page 1\n"
        "Don't overthink it — your first product is a learning product, not your forever product."
    ),
    "product_selected": (
        "Product research can feel endless. Focus on these filters:\n"
        "- Monthly revenue $5K-$50K for the top 5 sellers\n"
        "- Under 500 reviews for at least 3 of the top 10\n"
        "- Can you improve the listing/product in an obvious way?\n"
        "If yes to all three, you have a winner. Move to suppliers."
    ),
    "supplier_contacted": (
        "Suppliers not responding? Try this:\n"
        "1. Message at least 10-15 suppliers on Alibaba (not 2-3)\n"
        "2. Use a professional message template (check the course materials)\n"
        "3. Follow up after 48 hours if no response\n"
        "4. Ask for samples from the top 3 that respond\n"
        "Volume solves this problem — more outreach = more options."
    ),
    "sample_received": (
        "Waiting on samples is frustrating but it's part of the game.\n"
        "While you wait:\n"
        "- Start drafting your listing copy\n"
        "- Research keywords with Helium 10 or Jungle Scout\n"
        "- Plan your product photography\n"
        "- Set up your Amazon Seller Central account if you haven't\n"
        "Use the downtime productively."
    ),
    "listing_created": (
        "Listing creation is where most people underinvest. Check these:\n"
        "- Title: main keyword + benefit + key feature (under 200 chars)\n"
        "- Bullets: benefit-first, then feature. All 5 filled.\n"
        "- Images: 7+ images including infographics and lifestyle\n"
        "- A+ Content: use it if you have Brand Registry\n"
        "Your listing IS your sales page. Invest the time."
    ),
    "listing_live": (
        "Listing is live but no traction? Normal. Day 1-14 plan:\n"
        "1. Turn on auto PPC campaign ($15-25/day)\n"
        "2. Send to friends/family for initial reviews (follow TOS)\n"
        "3. Check search term report after 7 days\n"
        "4. Negate irrelevant keywords eating your budget\n"
        "The algorithm needs data. Give it time and budget."
    ),
    "first_sale": (
        "First sale is a mindset shift — you proved the model works.\n"
        "Now focus on:\n"
        "1. Getting to 15+ reviews (social proof threshold)\n"
        "2. Optimizing PPC — lower ACoS, find winning keywords\n"
        "3. Monitor inventory velocity and reorder timing\n"
        "4. Start thinking about product #2\n"
        "The first sale is the hardest. It gets easier from here."
    ),
    "profitable_month": (
        "You're profitable — that means the system works. To scale:\n"
        "1. Launch 1-2 more products in the same niche (brand building)\n"
        "2. Optimize PPC: move winning auto keywords to manual exact\n"
        "3. A/B test your main image (this alone can 2x sales)\n"
        "4. Consider variations (size, color, bundle)\n"
        "Stack products. That's how you get to $10K."
    ),
    "10k_month": (
        "You're at the scaling phase. Key levers:\n"
        "1. Expand to adjacent niches or new markets (UK, CA, DE)\n"
        "2. Build a brand — storefront, A+ Content, Brand Story\n"
        "3. Negotiate better supplier terms (volume discounts)\n"
        "4. Consider hiring a VA for customer service + PPC management\n"
        "At $10K/mo, you're a real business. Operate like one."
    ),
}

# High-severity keywords that trigger a Sabbo alert
ALERT_KEYWORDS = ["quit", "give up", "refund", "cancel", "done with this", "waste of money"]


def _get_db():
    """Get student database connection."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _get_student(conn, discord_user_id: int):
    """Look up a student by Discord user ID."""
    return conn.execute(
        "SELECT * FROM students WHERE discord_user_id = ?",
        (str(discord_user_id),)
    ).fetchone()


def _log_signal(conn, student_id: int, signal_type: str, channel: str, notes: str = ""):
    """Log an engagement signal."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn.execute(
        """INSERT INTO engagement_signals (student_id, signal_type, channel, value, date, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (student_id, signal_type, channel, "true", today, notes, datetime.utcnow().isoformat())
    )
    conn.commit()


def _check_frustrated(text: str) -> bool:
    """Check if message text contains frustration signals."""
    lower = text.lower()
    return any(kw in lower for kw in FRUSTRATED_KEYWORDS)


def _check_alert(text: str) -> bool:
    """Check if message text contains high-severity alert keywords."""
    lower = text.lower()
    return any(kw in lower for kw in ALERT_KEYWORDS)


# ── Milestone choices (reused by /checkin and /stuck) ──────────────────────────

MILESTONE_CHOICES = [
    app_commands.Choice(name="Niche Selection", value="niche_selected"),
    app_commands.Choice(name="Product Research", value="product_selected"),
    app_commands.Choice(name="Contacting Suppliers", value="supplier_contacted"),
    app_commands.Choice(name="Waiting for Samples", value="sample_received"),
    app_commands.Choice(name="Creating Listing", value="listing_created"),
    app_commands.Choice(name="Listing Live", value="listing_live"),
    app_commands.Choice(name="Getting First Sale", value="first_sale"),
    app_commands.Choice(name="Building to Profit", value="profitable_month"),
    app_commands.Choice(name="Scaling to $10K", value="10k_month"),
]

MOOD_CHOICES = [
    app_commands.Choice(name="Feeling great!", value="positive"),
    app_commands.Choice(name="Doing okay", value="neutral"),
    app_commands.Choice(name="Frustrated", value="frustrated"),
    app_commands.Choice(name="Losing motivation", value="disengaged"),
]

MOOD_RESPONSES = {
    "positive": "Keep that energy! You're making progress.",
    "neutral": "Consistency beats motivation. Keep showing up.",
    "frustrated": (
        "Frustration means you're pushing your limits. That's growth. "
        "Drop your specific blocker in the chat and let's solve it."
    ),
    "disengaged": (
        "I hear you. Remember why you started. "
        "Would a 1-on-1 session help? React with \U0001f44b and we'll set something up."
    ),
}


import os as _os
GUILD_ID = _os.getenv("DISCORD_GUILD_ID", "1185214150222286849")

# Student role — used to identify student channels (🎓 prefix)
STUDENT_CHANNEL_PREFIX = "🎓"


def _ensure_sla_table(conn):
    """Create response_sla table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS response_sla (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            message_at TEXT NOT NULL,
            responded_at TEXT,
            response_hours REAL,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)
    conn.commit()


def _is_student_channel(channel_name):
    """Check if a channel is a student private channel (🎓 prefix)."""
    return channel_name and (
        channel_name.startswith("🎓") or channel_name.startswith("%F0%9F%8E%93")
    )


class CSMCog(commands.Cog):
    """Customer Success Manager — tracks student engagement and provides coaching support."""

    def __init__(self, bot):
        self.bot = bot

    # ── Silent Activity Listener + SLA Tracking ────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Silently log all non-bot guild messages as engagement signals + track SLA."""
        # Skip bots and DMs
        if message.author.bot:
            return
        if not message.guild:
            return

        conn = _get_db()
        if not conn:
            return

        try:
            channel_name = getattr(message.channel, "name", "unknown")
            is_private = _is_student_channel(channel_name)

            student = _get_student(conn, message.author.id)

            if student:
                # Student sent a message — log activity
                _log_signal(
                    conn, student["id"], "discord_message", channel_name,
                    notes=f"len={len(message.content)}"
                )

                # Check for frustration signals
                if message.content and _check_frustrated(message.content):
                    _log_signal(
                        conn, student["id"], "mood_frustrated", channel_name,
                        notes=message.content[:200]
                    )

                # SLA: Student sent message in their private channel — log for tracking
                if is_private:
                    _ensure_sla_table(conn)
                    conn.execute("""
                        INSERT INTO response_sla (student_id, channel_id, message_at)
                        VALUES (?, ?, ?)
                    """, (student["id"], str(message.channel.id), datetime.utcnow().isoformat()))
                    conn.commit()

                # Track touchpoint responses — if student replies, mark touchpoints responded
                conn.execute("""
                    UPDATE touchpoints SET status = 'responded', response_at = ?
                    WHERE student_id = ? AND status = 'sent' AND response_at IS NULL
                """, (datetime.utcnow().isoformat(), student["id"]))
                conn.commit()

            elif is_private:
                # Non-student (coach/Sabbo) sent message in a student channel — SLA response
                _ensure_sla_table(conn)
                # Find the student who owns this channel
                owner = conn.execute(
                    "SELECT id FROM students WHERE discord_channel_id = ?",
                    (str(message.channel.id),)
                ).fetchone()
                if owner:
                    # Mark the most recent unanswered SLA entry as responded
                    now = datetime.utcnow().isoformat()
                    pending = conn.execute("""
                        SELECT id, message_at FROM response_sla
                        WHERE student_id = ? AND channel_id = ? AND responded_at IS NULL
                        ORDER BY message_at DESC LIMIT 1
                    """, (owner["id"], str(message.channel.id))).fetchone()
                    if pending:
                        msg_time = datetime.fromisoformat(pending["message_at"])
                        hours = (datetime.utcnow() - msg_time).total_seconds() / 3600
                        conn.execute("""
                            UPDATE response_sla SET responded_at = ?, response_hours = ?
                            WHERE id = ?
                        """, (now, round(hours, 2), pending["id"]))
                        conn.commit()

        except Exception as e:
            print(f"[csm-cog] Activity listener error: {e}", file=sys.stderr)
        finally:
            conn.close()

    # ── /checkin ───────────────────────────────────────────────────────────────

    @app_commands.command(name="checkin", description="Weekly progress check-in")
    @app_commands.describe(
        milestone="What milestone are you working on?",
        actions="What did you do this week?",
        blockers="Anything blocking you?",
        mood="How are you feeling?",
    )
    @app_commands.choices(milestone=MILESTONE_CHOICES, mood=MOOD_CHOICES)
    async def checkin(
        self,
        interaction: discord.Interaction,
        milestone: app_commands.Choice[str],
        actions: str,
        mood: app_commands.Choice[str],
        blockers: str = None,
    ):
        await interaction.response.defer(thinking=True)

        conn = _get_db()
        if not conn:
            await interaction.followup.send("Student tracking system is not set up yet. Ask Sabbo to initialize it.")
            return

        try:
            student = _get_student(conn, interaction.user.id)
            if not student:
                await interaction.followup.send(
                    "I don't have you registered yet. Ask Sabbo to add you to the tracking system!"
                )
                return

            now = datetime.utcnow()
            today = now.strftime("%Y-%m-%d")
            channel_name = getattr(interaction.channel, "name", "discord")

            # Log check-in to check_ins table
            try:
                conn.execute(
                    """INSERT INTO check_ins (student_id, date, milestone, actions, blockers, mood, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (student["id"], today, milestone.value, actions, blockers or "", mood.value, now.isoformat())
                )
                conn.commit()
            except sqlite3.OperationalError:
                # Table might not exist — create it
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS check_ins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        date TEXT NOT NULL,
                        milestone TEXT,
                        actions TEXT,
                        blockers TEXT,
                        mood TEXT,
                        created_at TEXT,
                        FOREIGN KEY (student_id) REFERENCES students(id)
                    )
                """)
                conn.execute(
                    """INSERT INTO check_ins (student_id, date, milestone, actions, blockers, mood, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (student["id"], today, milestone.value, actions, blockers or "", mood.value, now.isoformat())
                )
                conn.commit()

            # Log mood signal
            _log_signal(conn, student["id"], f"mood_{mood.value}", channel_name,
                        notes=f"checkin milestone={milestone.value}")

            # Log assignment_submitted signal
            _log_signal(conn, student["id"], "assignment_submitted", channel_name,
                        notes=f"weekly checkin: {milestone.value}")

            # Build response
            mood_msg = MOOD_RESPONSES.get(mood.value, "Thanks for checking in!")
            response = (
                f"**Check-in logged!** \u2705\n\n"
                f"**Milestone:** {milestone.name}\n"
                f"**Actions:** {actions}\n"
            )
            if blockers:
                response += f"**Blockers:** {blockers}\n"
            response += f"\n{mood_msg}"

            # Flag for Sabbo if mood is bad and there's a blocker
            if blockers and mood.value in ("frustrated", "disengaged"):
                response += (
                    "\n\n*Your blocker has been flagged for Sabbo's attention. "
                    "Expect a follow-up soon.*"
                )
                _log_signal(conn, student["id"], "blocker_flagged", channel_name,
                            notes=f"mood={mood.value} blocker={blockers[:200]}")

            await interaction.followup.send(response)

        except Exception as e:
            print(f"[csm-cog] /checkin error: {e}", file=sys.stderr)
            await interaction.followup.send("Something went wrong logging your check-in. Please try again.")
        finally:
            conn.close()

    # ── /win ───────────────────────────────────────────────────────────────────

    @app_commands.command(name="win", description="Share a win! First sale, new product, milestone hit")
    @app_commands.describe(
        win_type="What kind of win?",
        details="Tell us about it!",
        screenshot="Attach a screenshot (optional)",
    )
    @app_commands.choices(win_type=[
        app_commands.Choice(name="First Sale!", value="first_sale"),
        app_commands.Choice(name="Profitable Product", value="profitable_product"),
        app_commands.Choice(name="Revenue Milestone", value="revenue_milestone"),
        app_commands.Choice(name="New Listing Live", value="listing_live"),
        app_commands.Choice(name="Other Win", value="other"),
    ])
    async def win(
        self,
        interaction: discord.Interaction,
        win_type: app_commands.Choice[str],
        details: str,
        screenshot: discord.Attachment = None,
    ):
        await interaction.response.defer(thinking=True)

        conn = _get_db()
        if not conn:
            await interaction.followup.send("Student tracking system is not set up yet. Ask Sabbo to initialize it.")
            return

        try:
            student = _get_student(conn, interaction.user.id)
            if not student:
                await interaction.followup.send(
                    "I don't have you registered yet. Ask Sabbo to add you to the tracking system!"
                )
                return

            channel_name = getattr(interaction.channel, "name", "discord")

            # Log the win signal
            _log_signal(conn, student["id"], win_type.value, channel_name,
                        notes=f"WIN: {details[:200]}")

            # Log positive mood
            _log_signal(conn, student["id"], "mood_positive", channel_name,
                        notes=f"win shared: {win_type.value}")

            # Log screenshot if provided
            if screenshot:
                _log_signal(conn, student["id"], "screenshot_shared", channel_name,
                            notes=f"win screenshot: {screenshot.filename}")

            # Build celebration message
            celebration = (
                f"\U0001f514 **WIN ALERT** \u2014 {interaction.user.mention} just shared a win!\n\n"
                f"**{win_type.name}**: {details}"
            )

            if screenshot:
                await interaction.followup.send(celebration, file=await screenshot.to_file())
            else:
                await interaction.followup.send(celebration)

        except Exception as e:
            print(f"[csm-cog] /win error: {e}", file=sys.stderr)
            await interaction.followup.send("Something went wrong sharing your win. Please try again.")
        finally:
            conn.close()

    # ── /stuck ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="stuck", description="Flag that you're stuck \u2014 we'll help!")
    @app_commands.describe(
        milestone="What milestone are you stuck on?",
        details="What specifically is blocking you?",
    )
    @app_commands.choices(milestone=MILESTONE_CHOICES)
    async def stuck(
        self,
        interaction: discord.Interaction,
        milestone: app_commands.Choice[str],
        details: str,
    ):
        await interaction.response.defer(thinking=True)

        conn = _get_db()
        if not conn:
            await interaction.followup.send("Student tracking system is not set up yet. Ask Sabbo to initialize it.")
            return

        try:
            student = _get_student(conn, interaction.user.id)
            if not student:
                await interaction.followup.send(
                    "I don't have you registered yet. Ask Sabbo to add you to the tracking system!"
                )
                return

            channel_name = getattr(interaction.channel, "name", "discord")

            # Log stuck + frustrated signals
            _log_signal(conn, student["id"], "milestone_stuck", channel_name,
                        notes=f"milestone={milestone.value} details={details[:200]}")
            _log_signal(conn, student["id"], "mood_frustrated", channel_name,
                        notes=f"stuck at {milestone.value}")

            # Get milestone-specific advice
            tip = MILESTONE_TIPS.get(
                milestone.value,
                "Drop more details about what's blocking you and we'll figure it out together."
            )

            response = (
                f"**Stuck at: {milestone.name}**\n\n"
                f"Here's what usually helps at this stage:\n\n{tip}\n\n"
                f"If this doesn't unblock you, drop more details in the chat "
                f"or use `/ask` to get specific help."
            )

            await interaction.followup.send(response)

            # High-severity alert — log only, no DM (DMs disabled)
            if _check_alert(details):
                _log_signal(conn, student["id"], "high_severity_stuck", channel_name,
                            notes=f"ALERT keywords detected: {details[:200]}")

        except Exception as e:
            print(f"[csm-cog] /stuck error: {e}", file=sys.stderr)
            await interaction.followup.send("Something went wrong. Please try again.")
        finally:
            conn.close()

    # ── /referral ──────────────────────────────────────────────────────────────

    @app_commands.command(name="referral", description="Get your referral code and check referral status")
    async def referral(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        conn = _get_db()
        if not conn:
            await interaction.followup.send(
                "Student tracking system is not set up yet. Ask Sabbo to initialize it.",
                ephemeral=True,
            )
            return

        try:
            student = _get_student(conn, interaction.user.id)
            if not student:
                await interaction.followup.send(
                    "I don't have you registered yet. Ask Sabbo to add you to the tracking system!",
                    ephemeral=True,
                )
                return

            # Ensure referrals table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    referral_code TEXT UNIQUE NOT NULL,
                    referred_count INTEGER DEFAULT 0,
                    enrolled_count INTEGER DEFAULT 0,
                    commission_total REAL DEFAULT 0.0,
                    created_at TEXT,
                    FOREIGN KEY (student_id) REFERENCES students(id)
                )
            """)
            conn.commit()

            # Look up existing referral code
            ref = conn.execute(
                "SELECT * FROM referrals WHERE student_id = ?",
                (student["id"],)
            ).fetchone()

            if not ref:
                # Generate a new referral code
                first_name = (student["name"] or "STUDENT").split()[0].upper()
                code = f"REF-{first_name}-{random.randint(1000, 9999)}"

                # Ensure uniqueness
                while conn.execute("SELECT 1 FROM referrals WHERE referral_code = ?", (code,)).fetchone():
                    code = f"REF-{first_name}-{random.randint(1000, 9999)}"

                conn.execute(
                    """INSERT INTO referrals (student_id, referral_code, created_at)
                       VALUES (?, ?, ?)""",
                    (student["id"], code, datetime.utcnow().isoformat())
                )
                conn.commit()

                ref = conn.execute(
                    "SELECT * FROM referrals WHERE student_id = ?",
                    (student["id"],)
                ).fetchone()

            response = (
                f"**Your Referral Code:** `{ref['referral_code']}`\n\n"
                f"**Referred:** {ref['referred_count']} people\n"
                f"**Enrolled:** {ref['enrolled_count']} students\n"
                f"**Commission Earned:** ${ref['commission_total']:.2f}\n\n"
                f"Share your code with anyone interested in the program!"
            )

            await interaction.followup.send(response, ephemeral=True)

        except Exception as e:
            print(f"[csm-cog] /referral error: {e}", file=sys.stderr)
            await interaction.followup.send(
                "Something went wrong. Please try again.",
                ephemeral=True,
            )
        finally:
            conn.close()


async def setup(bot):
    await bot.add_cog(CSMCog(bot))
