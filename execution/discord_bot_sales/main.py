#!/usr/bin/env python3
"""
Nova Sales — Internal Sales Team Discord Bot — Entry Point

Run: python -m execution.discord_bot_sales.main
Or:  python execution/run_nova_sales.py

Requires .env variables:
  DISCORD_SALES_BOT_TOKEN      — Bot token from Discord Developer Portal
  DISCORD_SALES_GUILD_ID       — Server ID for slash command sync
  DISCORD_SALES_ADMIN_ROLE_ID  — Role ID for admin commands
  ANTHROPIC_API_KEY            — Claude API key
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root + execution/ on path for imports (nova_core lives in execution/)
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "execution"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import discord
from discord.ext import commands


def create_bot():
    """Create and configure the Nova Sales Discord bot."""
    intents = discord.Intents.default()
    intents.guilds = True
    intents.reactions = True
    intents.members = True           # Required for on_member_join welcome flow
    intents.message_content = True   # Required to read channel messages for context

    bot = commands.Bot(
        command_prefix="!",  # Prefix commands disabled (slash only), but required by discord.py
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready():
        print("[nova-sales] Nova Sales online", file=sys.stderr)
        print(f"[nova-sales] Logged in as {bot.user} (ID: {bot.user.id})", file=sys.stderr)
        print(f"[nova-sales] Guilds: {len(bot.guilds)}", file=sys.stderr)

        # Set bot status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Sales Team | /ask /training /roleplay"
            )
        )

        # Sync slash commands to guild (instant, not global 1hr delay)
        guild_id = os.getenv("DISCORD_SALES_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"[nova-sales] Synced {len(synced)} slash commands to guild {guild_id}",
                  file=sys.stderr)
        else:
            synced = await bot.tree.sync()
            print(f"[nova-sales] Synced {len(synced)} slash commands globally (may take up to 1hr)",
                  file=sys.stderr)

        print("[nova-sales] Ready.", file=sys.stderr)

        # Security: leave unauthorized guilds
        allowed_ids = set()
        allowed_str = os.getenv("ALLOWED_GUILD_IDS", "")
        if allowed_str:
            allowed_ids = {int(g.strip()) for g in allowed_str.split(",") if g.strip()}
        guild_id_env = os.getenv("DISCORD_SALES_GUILD_ID", "")
        if guild_id_env:
            allowed_ids.add(int(guild_id_env))

        if allowed_ids:
            for guild in bot.guilds:
                if guild.id not in allowed_ids:
                    print(f"[nova-sales] SECURITY: Leaving unauthorized guild {guild.name} ({guild.id})", file=sys.stderr)
                    await guild.leave()

    @bot.event
    async def on_member_join(member: discord.Member):
        """Welcome new sales team members."""
        try:
            welcome = (
                f"**Welcome to the sales team, {member.display_name}!**\n\n"
                "I'm **Nova Sales**, your AI sales manager and trainer. Here's what I can do:\n\n"
                "- `/ask` -- Ask about scripts, objections, techniques, or sales data\n"
                "- `/pipeline` -- See today's calls, MTD KPIs, and team performance\n"
                "- `/training` -- Get today's training module\n"
                "- `/roleplay` -- Practice sales scenarios with me\n"
                "- `/battle-card` -- Get objection battle cards with word tracks\n"
                "- `/script` -- Look up scripts by topic\n"
                "- `/learning` -- See what I've learned from real sales data\n\n"
                "I read the team chat and have access to live pipeline data, so feel free to ask me anything!"
            )
            await member.send(welcome)
        except discord.Forbidden:
            pass
        except Exception:
            pass

    @bot.tree.error
    async def on_app_command_error(interaction, error):
        """Global error handler for slash commands."""
        if isinstance(error, discord.app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You don't have permission to use this command.",
                                                    ephemeral=True)
        elif isinstance(error, discord.app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(
                f"Command on cooldown. Try again in {error.retry_after:.0f}s.",
                ephemeral=True
            )
        else:
            print(f"[nova-sales] Command error: {error}", file=sys.stderr)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "Something went wrong. Please try again.",
                        ephemeral=True
                    )
            except Exception:
                pass

    return bot


async def main():
    """Load cogs and start the bot."""
    token = os.getenv("DISCORD_SALES_BOT_TOKEN")
    if not token:
        print("[nova-sales] ERROR: DISCORD_SALES_BOT_TOKEN not set in .env", file=sys.stderr)
        print("[nova-sales] Get one from: https://discord.com/developers/applications", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[nova-sales] WARNING: ANTHROPIC_API_KEY not set — AI commands will not work", file=sys.stderr)

    bot = create_bot()

    # Load cogs
    cog_modules = [
        "execution.discord_bot_sales.chat_cog",
        "execution.discord_bot_sales.admin_cog",
        "execution.discord_bot_sales.training_cog",
    ]

    for cog in cog_modules:
        try:
            await bot.load_extension(cog)
            print(f"[nova-sales] Loaded {cog.split('.')[-1]}", file=sys.stderr)
        except Exception as e:
            print(f"[nova-sales] Failed to load {cog}: {e}", file=sys.stderr)

    print("[nova-sales] Starting bot...", file=sys.stderr)
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
