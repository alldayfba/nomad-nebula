"""Admin Cog — /bot-status, /set-model, /blacklist, /faq-*, /top-questions, /bot-insights."""

from __future__ import annotations

import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from .database import BotDatabase
from .security import is_admin


class AdminCog(commands.Cog):
    """Admin-only commands for bot management, FAQ curation, and analytics."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.admin_role_id = os.getenv("DISCORD_SALES_ADMIN_ROLE_ID", "")
        self.start_time = datetime.utcnow()

    def _check_admin(self, interaction):
        return is_admin(interaction, self.admin_role_id)

    # ── /bot-status ───────────────────────────────────────────────────────────

    @app_commands.command(name="bot-status", description="[Admin] Show Nova Sales bot statistics")
    async def status(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        stats = self.db.get_stats()
        uptime = datetime.utcnow() - self.start_time
        hours = uptime.total_seconds() / 3600

        # Get current model from chat cog
        chat_cog = self.bot.get_cog("ChatCog")
        model = chat_cog.model if chat_cog else "unknown"

        embed = discord.Embed(
            title="Nova Sales — Bot Status",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Uptime", value=f"{hours:.1f} hours", inline=True)
        embed.add_field(name="Model", value=model, inline=True)
        embed.add_field(name="Total Chats", value=str(stats["total_chats"]), inline=True)
        embed.add_field(name="FAQ Entries", value=str(stats["faq_entries"]), inline=True)
        embed.add_field(
            name="API Usage",
            value=f"{stats['total_tokens_in']:,} in / {stats['total_tokens_out']:,} out",
            inline=True
        )
        embed.add_field(name="Blacklisted", value=str(stats["blacklisted_users"]), inline=True)
        embed.add_field(name="Injection Attempts", value=str(stats["injection_attempts"]), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /set-model ────────────────────────────────────────────────────────────

    @app_commands.command(name="set-model", description="[Admin] Switch Claude model")
    @app_commands.describe(model="Model to use")
    @app_commands.choices(model=[
        app_commands.Choice(name="Haiku (fast, cheap)", value="claude-haiku-4-5-20251001"),
        app_commands.Choice(name="Sonnet (balanced)", value="claude-sonnet-4-6"),
    ])
    async def set_model(self, interaction: discord.Interaction, model: app_commands.Choice[str]):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        chat_cog = self.bot.get_cog("ChatCog")
        if chat_cog:
            old_model = chat_cog.model
            chat_cog.model = model.value
            self.db.log_audit(str(interaction.user.id), "set_model",
                              f"{old_model} → {model.value}")
            await interaction.response.send_message(
                f"Model switched to **{model.name}** (`{model.value}`)", ephemeral=True
            )
        else:
            await interaction.response.send_message("Chat cog not loaded.", ephemeral=True)

    # ── /blacklist ────────────────────────────────────────────────────────────

    @app_commands.command(name="blacklist", description="[Admin] Block a user from the bot")
    @app_commands.describe(member="User to blacklist", reason="Reason for blacklisting")
    async def blacklist(self, interaction: discord.Interaction, member: discord.Member,
                        reason: str = "Admin decision"):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        self.db.add_blacklist(str(member.id), reason, str(interaction.user.id))
        self.db.log_audit(str(interaction.user.id), "blacklist",
                          f"user={member.display_name} reason={reason}")

        await interaction.response.send_message(
            f"**{member.display_name}** has been blacklisted. Reason: {reason}",
            ephemeral=True
        )

    # ── /unblacklist ──────────────────────────────────────────────────────────

    @app_commands.command(name="unblacklist", description="[Admin] Remove a user from the blacklist")
    @app_commands.describe(member="User to unblacklist")
    async def unblacklist(self, interaction: discord.Interaction, member: discord.Member):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        self.db.remove_blacklist(str(member.id))
        self.db.log_audit(str(interaction.user.id), "unblacklist", f"user={member.display_name}")
        await interaction.response.send_message(
            f"**{member.display_name}** has been removed from the blacklist.",
            ephemeral=True
        )

    # ── FAQ Management ────────────────────────────────────────────────────────

    @app_commands.command(name="faq-add", description="[Admin] Add a FAQ entry to the sales knowledge base")
    @app_commands.describe(question="The question", answer="The approved answer")
    async def faq_add(self, interaction: discord.Interaction, question: str, answer: str):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        self.db.add_knowledge_entry(
            question=question[:500],
            answer=answer[:2000],
            source="admin",
            approved=True,
            approved_by=str(interaction.user.id),
        )
        self.db.log_audit(str(interaction.user.id), "faq_add", question[:200])

        await interaction.response.send_message(
            f"FAQ added and auto-approved.\n**Q:** {question[:100]}...\n**A:** {answer[:100]}...",
            ephemeral=True
        )

    @app_commands.command(name="faq-list", description="[Admin] Show all approved FAQ entries")
    async def faq_list(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        entries = self.db.get_approved_knowledge_all()
        if not entries:
            await interaction.response.send_message("No FAQ entries yet. Use `/faq-add` to create one.",
                                                    ephemeral=True)
            return

        lines = [f"**Approved FAQ ({len(entries)})**\n"]
        for e in entries[:15]:
            votes = f"👍{e.get('upvotes', 0)} 👎{e.get('downvotes', 0)}"
            lines.append(f"`#{e['id']}` {votes} | **Q:** {e['question'][:60]}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="faq-pending", description="[Admin] Show auto-generated FAQ entries awaiting approval")
    async def faq_pending(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        entries = self.db.get_pending_knowledge()
        if not entries:
            await interaction.response.send_message(
                "No pending entries. Candidates are auto-created when a question is asked 5+ times.",
                ephemeral=True
            )
            return

        lines = [f"**Pending FAQ ({len(entries)})** — use `/faq-approve <id>` to approve\n"]
        for e in entries[:15]:
            lines.append(f"`#{e['id']}` **Q:** {e['question'][:80]}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="faq-approve", description="[Admin] Approve a pending FAQ entry")
    @app_commands.describe(entry_id="FAQ entry ID", answer="Override the auto-generated answer")
    async def faq_approve(self, interaction: discord.Interaction, entry_id: int,
                          answer: str = None):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        if answer:
            conn = self.db._get_conn()
            try:
                conn.execute("UPDATE knowledge_base SET answer = ? WHERE id = ?",
                             (answer[:2000], entry_id))
                conn.commit()
            finally:
                conn.close()

        self.db.approve_knowledge(entry_id, str(interaction.user.id))
        self.db.log_audit(str(interaction.user.id), "faq_approve", f"entry_id={entry_id}")

        await interaction.response.send_message(f"FAQ entry `#{entry_id}` approved.", ephemeral=True)

    @app_commands.command(name="faq-delete", description="[Admin] Delete a FAQ entry")
    @app_commands.describe(entry_id="FAQ entry ID to delete")
    async def faq_delete(self, interaction: discord.Interaction, entry_id: int):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        self.db.delete_knowledge(entry_id)
        self.db.log_audit(str(interaction.user.id), "faq_delete", f"entry_id={entry_id}")
        await interaction.response.send_message(f"FAQ entry `#{entry_id}` deleted.", ephemeral=True)

    # ── Analytics ─────────────────────────────────────────────────────────────

    @app_commands.command(name="top-questions", description="[Admin] Show most-asked sales questions")
    @app_commands.describe(days="Look back period in days (default: 30)")
    async def top_questions(self, interaction: discord.Interaction, days: int = 30):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        clusters = self.db.get_top_clusters(days=days, limit=10)
        if not clusters:
            await interaction.response.send_message("No question data yet.", ephemeral=True)
            return

        lines = [f"**Top Questions (last {days} days)**\n"]
        for i, c in enumerate(clusters, 1):
            lines.append(
                f"{i}. **{c['frequency']}x** | `{c['category']}` | {c['representative_question'][:70]}"
            )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="bot-insights", description="[Admin] Nova Sales analytics dashboard")
    async def insights(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        stats = self.db.get_stats()
        clusters = self.db.get_top_clusters(days=30, limit=5)
        pending = self.db.get_pending_knowledge()

        embed = discord.Embed(
            title="Nova Sales — Bot Insights",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow(),
        )

        embed.add_field(name="Total Conversations", value=str(stats["total_chats"]), inline=True)
        embed.add_field(name="FAQ Entries", value=str(stats["faq_entries"]), inline=True)
        embed.add_field(name="Pending FAQ", value=str(len(pending)), inline=True)

        if clusters:
            top_q = "\n".join(
                f"**{c['frequency']}x** {c['representative_question'][:50]}"
                for c in clusters[:5]
            )
            embed.add_field(name="Top Questions (30d)", value=top_q, inline=False)

        # Estimated API cost (Haiku pricing)
        cost_in = stats["total_tokens_in"] * 0.25 / 1_000_000
        cost_out = stats["total_tokens_out"] * 1.25 / 1_000_000
        total_cost = cost_in + cost_out
        embed.add_field(name="Est. API Cost", value=f"~${total_cost:.2f}", inline=True)
        embed.add_field(name="Injection Attempts", value=str(stats["injection_attempts"]), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
