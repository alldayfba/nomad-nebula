"""Engagement Cog — proactive student engagement via scheduled messages and announcements."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, time as dtime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

STUDENTS_DB = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"


class EngagementCog(commands.Cog):
    """Proactive student engagement — wins digest, at-risk alerts, announcements."""

    def __init__(self, bot):
        self.bot = bot
        self.admin_role_id = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))

    def cog_load(self):
        self._daily_check.start()
        self._weekly_wins.start()

    def cog_unload(self):
        self._daily_check.cancel()
        self._weekly_wins.cancel()

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return any(r.id == self.admin_role_id for r in interaction.user.roles)

    @tasks.loop(time=dtime(hour=14, minute=0))  # 14:00 UTC = ~9-10 AM EST
    async def _daily_check(self):
        """Daily 9 AM EST: check for at-risk students and post to team channel."""
        now = datetime.now()
        if now.weekday() >= 5:
            return  # Skip weekends

        if not STUDENTS_DB.exists():
            return

        try:
            conn = sqlite3.connect(str(STUDENTS_DB), timeout=5)
            conn.row_factory = sqlite3.Row
            at_risk = conn.execute(
                "SELECT name, health_score, risk_level, current_milestone "
                "FROM students WHERE status = 'active' AND health_score < 40 "
                "ORDER BY health_score ASC LIMIT 10"
            ).fetchall()
            conn.close()

            if not at_risk:
                return

            lines = [f"**Daily Student Health Alert** -- {now.strftime('%B %d')}\n"]
            lines.append(f"{len(at_risk)} students at risk:\n")
            for s in at_risk:
                lines.append(f"- **{s['name']}** -- Score: {s['health_score']}/100 "
                             f"({s['risk_level']}) -- Milestone: {s['current_milestone'] or 'None'}")

            lines.append("\nConsider reaching out to these students today.")

            # Post to first text channel that has "team" or "alerts" or "staff" in the name
            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    if any(kw in channel.name.lower() for kw in ["team", "alert", "staff", "ops"]):
                        await channel.send("\n".join(lines))
                        return
        except Exception:
            pass

    @_daily_check.before_loop
    async def _before_daily(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=dtime(hour=22, minute=0))  # 22:00 UTC = ~5 PM EST
    async def _weekly_wins(self):
        """Friday: post weekly wins digest to #wins channel."""
        now = datetime.now()
        if now.weekday() != 4:  # Friday only
            return

        # Get wins from engagement_signals in students.db
        try:
            if not STUDENTS_DB.exists():
                return
            conn = sqlite3.connect(str(STUDENTS_DB), timeout=5)
            conn.row_factory = sqlite3.Row
            wins = conn.execute(
                "SELECT s.name, es.signal_type, es.notes, es.date "
                "FROM engagement_signals es JOIN students s ON s.id = es.student_id "
                "WHERE es.signal_type IN ('first_sale', 'profitable_product', 'revenue_milestone', 'listing_live', 'other') "
                "AND es.date >= date('now', '-7 days') ORDER BY es.date DESC LIMIT 10"
            ).fetchall()

            if not wins:
                conn.close()
                return

            lines = ["**Weekly Wins Digest**\n"]
            for w in wins:
                win_type = (w["signal_type"] or "win").replace("_", " ").title()
                name = w["name"]
                notes = (w["notes"] or "")[:200]
                lines.append(f"- **{name}** — {win_type}" + (f": {notes}" if notes else ""))
            conn.close()

            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    if "win" in channel.name.lower():
                        await channel.send("\n".join(lines))
                        return
        except Exception:
            pass

    @_weekly_wins.before_loop
    async def _before_weekly(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="announce", description="[Admin] Post an announcement to a channel")
    @app_commands.describe(channel="Channel to post in", message="The announcement message")
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        if not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await channel.send(f"**Announcement**\n\n{message}")
        await interaction.followup.send(f"Posted to #{channel.name}", ephemeral=True)

    @app_commands.command(name="student-health", description="[Admin] Show at-risk students")
    async def student_health(self, interaction: discord.Interaction):
        if not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if not STUDENTS_DB.exists():
            await interaction.followup.send("Student database not found.", ephemeral=True)
            return

        conn = sqlite3.connect(str(STUDENTS_DB), timeout=5)
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) FROM students WHERE status = 'active'").fetchone()[0]
        at_risk = conn.execute(
            "SELECT name, health_score, risk_level, current_milestone "
            "FROM students WHERE status = 'active' AND health_score < 40 "
            "ORDER BY health_score ASC"
        ).fetchall()
        healthy = conn.execute(
            "SELECT COUNT(*) FROM students WHERE status = 'active' AND health_score >= 70"
        ).fetchone()[0]
        conn.close()

        lines = ["**Student Health Overview**\n"]
        lines.append(f"- Total active: {total}")
        lines.append(f"- Healthy (70+): {healthy}")
        lines.append(f"- At risk (<40): {len(at_risk)}")

        if at_risk:
            lines.append("\n**At-Risk Students:**")
            for s in at_risk[:15]:
                lines.append(f"- {s['name']} -- {s['health_score']}/100 ({s['risk_level']}) -- {s['current_milestone'] or 'N/A'}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot):
    await bot.add_cog(EngagementCog(bot))
