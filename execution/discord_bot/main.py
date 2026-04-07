#!/usr/bin/env python3
"""
24/7 Profits & Growth Agency Discord Bot — Entry Point

Run: python -m execution.discord_bot.main
Or:  python execution/discord_bot/main.py

Requires .env variables:
  DISCORD_BOT_TOKEN          — Bot token from Discord Developer Portal
  DISCORD_GUILD_ID           — Server ID for slash command sync
  DISCORD_ADMIN_ROLE_ID      — Role ID for admin commands
  DISCORD_SUPPORT_ROLE_ID    — Role ID for ticket visibility
  DISCORD_TICKET_CATEGORY_ID — Category ID for ticket channels
  DISCORD_CHAT_MODEL         — Claude model (default: claude-haiku-4-5-20251001)
  ANTHROPIC_API_KEY          — Claude API key
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
    """Create and configure the Discord bot."""
    intents = discord.Intents.default()
    intents.message_content = True   # Required for DM handling + ticket transcript
    intents.members = True           # Required for member lookups

    bot = commands.Bot(
        command_prefix="!",  # Prefix commands disabled (slash only), but required by discord.py
        intents=intents,
        help_command=None,   # We use slash commands, not !help
    )

    @bot.event
    async def on_ready():
        print(f"[discord-bot] Logged in as {bot.user} (ID: {bot.user.id})", file=sys.stderr)
        print(f"[discord-bot] Guilds: {len(bot.guilds)}", file=sys.stderr)

        # Sync slash commands to guild (instant, not global 1hr delay)
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"[discord-bot] Synced {len(synced)} slash commands to guild {guild_id}",
                  file=sys.stderr)
        else:
            synced = await bot.tree.sync()
            print(f"[discord-bot] Synced {len(synced)} slash commands globally (may take up to 1hr)",
                  file=sys.stderr)

        # Validate role IDs exist in the guild
        guild_id_str = os.getenv("DISCORD_GUILD_ID", "")
        if guild_id_str:
            guild_obj = bot.get_guild(int(guild_id_str))
            if guild_obj:
                for role_name, role_id_str in [
                    ("admin", os.getenv("DISCORD_ADMIN_ROLE_ID", "")),
                    ("support", os.getenv("DISCORD_SUPPORT_ROLE_ID", "")),
                ]:
                    if role_id_str:
                        try:
                            role = guild_obj.get_role(int(role_id_str))
                            if not role:
                                print(f"[discord-bot] WARNING: {role_name} role ID {role_id_str} not found in guild",
                                      file=sys.stderr)
                        except (ValueError, TypeError):
                            print(f"[discord-bot] WARNING: {role_name} role ID '{role_id_str}' is not a valid integer",
                                  file=sys.stderr)

        print("[discord-bot] Ready.", file=sys.stderr)

        # Security: leave unauthorized guilds
        allowed_ids = set()
        allowed_str = os.getenv("ALLOWED_GUILD_IDS", "")
        if allowed_str:
            allowed_ids = {int(g.strip()) for g in allowed_str.split(",") if g.strip()}
        guild_id_env = os.getenv("DISCORD_GUILD_ID", "")
        if guild_id_env:
            allowed_ids.add(int(guild_id_env))

        if allowed_ids:
            for guild in bot.guilds:
                if guild.id not in allowed_ids:
                    print(f"[discord-bot] SECURITY: Leaving unauthorized guild {guild.name} ({guild.id})", file=sys.stderr)
                    await guild.leave()

    @bot.event
    async def on_member_join(member: discord.Member):
        """Welcome new members with a DM explaining how to use Nova."""
        try:
            welcome = (
                f"**Welcome to 24/7 Profits, {member.display_name}!**\n\n"
                "I'm **Nova**, your AI coaching assistant. Here's how I can help:\n\n"
                "- `/ask` -- Ask me anything about Amazon FBA, sourcing, or tools\n"
                "- `/link` -- Connect your Discord to your student account (use your signup email)\n"
                "- `/profile` -- View your progress and milestones\n"
                "- `/checkin` -- Track your weekly progress\n"
                "- `/win` -- Celebrate your wins with the community\n"
                "- `/stuck` -- Get help when you're stuck on a milestone\n"
                "- `/ticket` -- Open a support ticket for the team\n\n"
                "Start by linking your account with `/link` -- then I can give you personalized coaching!"
            )
            await member.send(welcome)
        except discord.Forbidden:
            pass  # DMs disabled
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
            print(f"[discord-bot] Command error: {error}", file=sys.stderr)
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
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("[discord-bot] ERROR: DISCORD_BOT_TOKEN not set in .env", file=sys.stderr)
        print("[discord-bot] Get one from: https://discord.com/developers/applications", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[discord-bot] WARNING: ANTHROPIC_API_KEY not set — /ask will not work", file=sys.stderr)

    bot = create_bot()

    # Load cogs
    cog_modules = [
        "execution.discord_bot.chat_cog",
        "execution.discord_bot.ticket_cog",
        "execution.discord_bot.admin_cog",
        "execution.discord_bot.csm_cog",
        "execution.discord_bot.profile_cog",
        "execution.discord_bot.engagement_cog",
        "execution.discord_bot.relay_cog",
    ]

    for cog in cog_modules:
        try:
            await bot.load_extension(cog)
            print(f"[discord-bot] Loaded {cog.split('.')[-1]}", file=sys.stderr)
        except Exception as e:
            print(f"[discord-bot] Failed to load {cog}: {e}", file=sys.stderr)

    print("[discord-bot] Starting bot...", file=sys.stderr)
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
