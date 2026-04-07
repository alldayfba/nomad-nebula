"""
Discord Relay Cog — replaces Zapier ZAP-006 (Discord Server Call Recording).

Listens for messages in configured source channels and reposts them to
target channels. Filters out bot messages to prevent loops.
Preserves message content and attachments.

Config:
    RELAY_MAP maps source_channel_id → target_channel_id
    Currently: #post-a-call-recording → target channel

Add to main.py:
    from relay_cog import RelayCog
    await bot.add_cog(RelayCog(bot))
"""

from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands

logger = logging.getLogger("nova.relay")

# Source channel → Target channel mapping
# ZAP-006: post-a-call-recording (1374870183742800012) → repost target
# TODO: Sabbo — set the target channel ID
RELAY_MAP = {
    "1374870183742800012": os.environ.get("RELAY_TARGET_CHANNEL", ""),
}


class RelayCog(commands.Cog, name="Relay"):
    """Relay messages between Discord channels (replaces Zapier channel-to-channel zaps)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages in source channels and relay to targets."""
        # Don't relay bot messages (prevents loops)
        if message.author.bot:
            return

        source_id = str(message.channel.id)
        target_id = RELAY_MAP.get(source_id, "")

        if not target_id:
            return

        target_channel = self.bot.get_channel(int(target_id))
        if not target_channel:
            logger.warning(f"Relay target channel {target_id} not found")
            return

        # Build the relay message
        embed = discord.Embed(
            title="\U0001f3a5 New Server Call Recording",
            description=message.content or "(no text)",
            color=0x5865F2,
        )
        embed.set_footer(text=f"From #{message.channel.name} by {message.author.display_name}")
        embed.timestamp = message.created_at

        # Forward attachments
        files = []
        for attachment in message.attachments:
            # For small files, re-upload; for large ones, include link
            if attachment.size < 8_000_000:  # 8MB Discord limit
                try:
                    file = await attachment.to_file()
                    files.append(file)
                except Exception:
                    embed.add_field(
                        name="Attachment",
                        value=f"[{attachment.filename}]({attachment.url})",
                        inline=False,
                    )
            else:
                embed.add_field(
                    name="Attachment",
                    value=f"[{attachment.filename}]({attachment.url}) ({attachment.size // 1_000_000}MB)",
                    inline=False,
                )

        try:
            await target_channel.send(embed=embed, files=files if files else discord.utils.MISSING)
            logger.info(f"Relayed message from #{message.channel.name} to #{target_channel.name}")
        except Exception as e:
            logger.error(f"Failed to relay message: {e}")


async def setup(bot: commands.Bot):
    """Called by bot.load_extension()."""
    await bot.add_cog(RelayCog(bot))
