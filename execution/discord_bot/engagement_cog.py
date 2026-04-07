"""Engagement Cog — proactive student engagement via scheduled messages and announcements."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

STUDENTS_DB = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"


class EngagementCog(commands.Cog):
    """Proactive student engagement — wins digest, at-risk alerts, announcements."""

    def __init__(self, bot):
        self.bot = bot
        self.admin_role_id = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))

    # AUTO-POSTING PERMANENTLY REMOVED (2026-04-07).
    # _daily_check and _weekly_wins tasks were deleted — they blindly posted
    # student names + health scores to ANY channel matching keyword patterns,
    # which leaked internal student data into unrelated servers.
    # All student-facing sends require Sabbo's explicit approval (Learned Rule #6).
    # Use the /student-health slash command for on-demand admin checks instead.

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return any(r.id == self.admin_role_id for r in interaction.user.roles)

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
