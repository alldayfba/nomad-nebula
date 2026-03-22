"""Ticket Cog — /ticket, /close-ticket, /ticket-add, /tickets-list + transcript listener."""

from __future__ import annotations

import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from .database import BotDatabase
from .security import RateLimiter, is_admin, is_support

TICKET_CATEGORIES = [
    app_commands.Choice(name="General", value="general"),
    app_commands.Choice(name="Billing", value="billing"),
    app_commands.Choice(name="Technical", value="technical"),
    app_commands.Choice(name="Coaching", value="coaching"),
    app_commands.Choice(name="Product Sourcing", value="product-sourcing"),
]


def _safe_int(val: str) -> int | None:
    """Safely convert string to int. Returns None on failure."""
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


class TicketCog(commands.Cog):
    """Support ticket system with private channels and transcript logging."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.rate_limiter = RateLimiter()
        self.admin_role_id = os.getenv("DISCORD_ADMIN_ROLE_ID", "")
        self.support_role_id = os.getenv("DISCORD_SUPPORT_ROLE_ID", "")
        self.ticket_category_id = os.getenv("DISCORD_TICKET_CATEGORY_ID", "")

    def _get_ticket_category(self, guild):
        """Get the Discord category for ticket channels."""
        cat_id = _safe_int(self.ticket_category_id)
        if cat_id:
            return guild.get_channel(cat_id)
        return None

    # ── /ticket ───────────────────────────────────────────────────────────────

    @app_commands.command(name="ticket", description="Open a support ticket")
    @app_commands.describe(
        subject="Brief description of your issue",
        category="Ticket category"
    )
    @app_commands.choices(category=TICKET_CATEGORIES)
    async def ticket(self, interaction: discord.Interaction, subject: str,
                     category: app_commands.Choice[str] = None):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild = interaction.guild

        if not guild:
            await interaction.followup.send("Tickets can only be created in a server.", ephemeral=True)
            return

        # Blacklist check
        if self.db.is_blacklisted(user.id):
            await interaction.followup.send("You are currently restricted from using this bot.",
                                            ephemeral=True)
            return

        # Rate limit
        if not self.rate_limiter.check(user.id, "ticket"):
            await interaction.followup.send(
                "You've opened too many tickets recently. Please wait before creating another.",
                ephemeral=True
            )
            return

        cat = category.value if category else "general"
        subject = subject[:200].strip()

        # Create private channel
        ticket_category = self._get_ticket_category(guild)

        # Build permission overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

        # Add support role
        support_rid = _safe_int(self.support_role_id)
        if support_rid:
            support_role = guild.get_role(support_rid)
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        # Add admin role
        admin_rid = _safe_int(self.admin_role_id)
        if admin_rid:
            admin_role = guild.get_role(admin_rid)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        # Create the channel
        import re as _re
        safe_name = _re.sub(r'[^a-z0-9-]', '', user.display_name.lower().replace(" ", "-"))[:20] or "user"
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}",
                category=ticket_category,
                overwrites=overwrites,
                reason=f"Support ticket: {subject[:50]}",
            )
        except discord.HTTPException:
            # Fallback: create without category if category is invalid
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}",
                overwrites=overwrites,
                reason=f"Support ticket: {subject[:50]}",
            )

        # Save to DB
        ticket_num = self.db.create_ticket(
            user_id=user.id,
            username=user.display_name,
            subject=subject,
            category=cat,
            channel_id=channel.id,
        )

        # Rename channel with ticket number
        await channel.edit(name=f"ticket-{ticket_num:04d}-{safe_name}")

        # Send opening embed in ticket channel
        embed = discord.Embed(
            title=f"Ticket #{ticket_num:04d}",
            description=subject,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Category", value=cat.replace("-", " ").title(), inline=True)
        embed.add_field(name="Opened by", value=user.mention, inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        embed.set_footer(text="Use /close-ticket to close this ticket")

        await channel.send(embed=embed)
        await channel.send(
            f"{user.mention} Your ticket has been created. "
            f"Describe your issue here and our team will respond."
        )

        # Log
        self.db.record_rate_limit(str(user.id), "ticket")
        self.db.log_audit(str(user.id), "ticket_open",
                          f"ticket={ticket_num} subject={subject} category={cat}")

        await interaction.followup.send(
            f"Ticket #{ticket_num:04d} created! Head to {channel.mention} to continue.",
            ephemeral=True
        )

    # ── /close-ticket ─────────────────────────────────────────────────────────

    @app_commands.command(name="close-ticket", description="Close the current ticket")
    async def close_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        ticket = self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.followup.send(
                "This command can only be used inside a ticket channel.",
                ephemeral=True
            )
            return

        user = interaction.user
        # Only ticket creator, support, or admin can close
        is_creator = str(user.id) == str(ticket["user_id"])
        has_support = is_support(interaction, self.support_role_id)
        has_admin = is_admin(interaction, self.admin_role_id)

        if not (is_creator or has_support or has_admin):
            await interaction.followup.send(
                "Only the ticket creator, support team, or admins can close tickets.",
                ephemeral=True
            )
            return

        # Close in DB
        self.db.close_ticket(ticket["id"], str(user.id))
        self.db.log_audit(str(user.id), "ticket_close",
                          f"ticket={ticket['ticket_number']} closed_by={user.display_name}")

        # Send closing embed
        embed = discord.Embed(
            title=f"Ticket #{ticket['ticket_number']:04d} — Closed",
            description=f"Closed by {user.mention}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Subject", value=ticket["subject"], inline=False)
        embed.set_footer(text="Transcript saved. This channel will be deleted in 10 seconds.")

        await interaction.followup.send(embed=embed)

        # Delete channel after short delay
        import asyncio
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason=f"Ticket #{ticket['ticket_number']} closed")
        except discord.errors.NotFound:
            pass

    # ── /ticket-add ───────────────────────────────────────────────────────────

    @app_commands.command(name="ticket-add", description="Add a user to this ticket")
    @app_commands.describe(member="User to add to the ticket")
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = self.db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside a ticket channel.",
                ephemeral=True
            )
            return

        user = interaction.user
        is_creator = str(user.id) == str(ticket["user_id"])
        has_support = is_support(interaction, self.support_role_id)
        has_admin = is_admin(interaction, self.admin_role_id)

        if not (is_creator or has_support or has_admin):
            await interaction.response.send_message(
                "Only the ticket creator, support, or admins can add users.",
                ephemeral=True
            )
            return

        await interaction.channel.set_permissions(
            member, read_messages=True, send_messages=True
        )
        await interaction.response.send_message(f"{member.mention} has been added to this ticket.")

    # ── /tickets-list ─────────────────────────────────────────────────────────

    @app_commands.command(name="tickets-list", description="[Admin] List all open tickets")
    async def tickets_list(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.admin_role_id):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        tickets = self.db.get_open_tickets()
        if not tickets:
            await interaction.response.send_message("No open tickets.", ephemeral=True)
            return

        lines = [f"**Open Tickets ({len(tickets)})**\n"]
        for t in tickets[:20]:
            age = ""
            if t.get("created_at"):
                try:
                    created = datetime.fromisoformat(t["created_at"])
                    hours = (datetime.utcnow() - created).total_seconds() / 3600
                    age = f" ({hours:.0f}h ago)" if hours < 24 else f" ({hours/24:.0f}d ago)"
                except (ValueError, TypeError):
                    pass

            lines.append(
                f"`#{t['ticket_number']:04d}` | **{t['subject'][:40]}** | "
                f"{t['category']} | by {t['username']}{age}"
            )

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ── Transcript Listener ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.guild:
            return

        # Check if this message is in a ticket channel
        ticket = self.db.get_ticket_by_channel(message.channel.id)
        if ticket:
            self.db.add_ticket_message(
                ticket_id=ticket["id"],
                user_id=message.author.id,
                username=message.author.display_name,
                content=message.content[:4000],
            )


async def setup(bot):
    await bot.add_cog(TicketCog(bot))
