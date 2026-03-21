# Nova Discord Bots -- Deployment Guide

## Prerequisites
- Python 3.9+ (using .venv at project root)
- Discord Bot tokens (in .env)
- Anthropic API key OR Claude CLI proxy running on port 5055
- Supabase project (for sales bot dashboard data)
- GHL API key (for sales bot CRM data)

## Environment Variables (.env)
Required for BOTH bots:
- `DISCORD_BOT_TOKEN` -- Student bot token
- `DISCORD_GUILD_ID` -- Student Discord server ID
- `DISCORD_ADMIN_ROLE_ID` -- Admin role in student server
- `DISCORD_SALES_BOT_TOKEN` -- Sales bot token
- `DISCORD_SALES_GUILD_ID` -- Sales team server ID
- `DISCORD_SALES_ADMIN_ROLE_ID` -- Admin role in sales server
- `CLAUDE_PROXY_URL` -- Claude CLI proxy (default: http://127.0.0.1:5055)
- `ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY2` -- Fallback API keys
- `DISCORD_WEBHOOK_URL` -- Ops alert webhook

Sales bot only:
- `NEXT_PUBLIC_SUPABASE_URL` -- Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` -- Service role key
- `DASHBOARD_ORG_ID` -- Organization ID
- `GHL_API_KEY` -- GoHighLevel v1 API key

## Starting the Bots
Both bots run as launchd services (auto-restart on crash):

```bash
# Student bot
launchctl load ~/Library/LaunchAgents/com.sabbo.nova-discord-bot.plist

# Sales bot
launchctl load ~/Library/LaunchAgents/com.sabbo.nova-sales-bot.plist

# EOC reschedule sync (every 30 min)
launchctl load ~/Library/LaunchAgents/com.sabbo.eoc-reschedule-sync.plist

# Database backups (daily 3 AM)
launchctl load ~/Library/LaunchAgents/com.sabbo.bot-db-backup.plist
```

## Stopping/Restarting
```bash
launchctl unload ~/Library/LaunchAgents/com.sabbo.nova-discord-bot.plist
launchctl load ~/Library/LaunchAgents/com.sabbo.nova-discord-bot.plist
```

## Logs
- Student bot: `.tmp/discord/nova.log`
- Sales bot: `.tmp/nova-sales-bot.log` + `.tmp/nova-sales-bot-error.log`
- EOC sync: `.tmp/eoc-reschedule-sync.log`
- DB backup: `.tmp/bot-db-backup.log`

## Databases
- `.tmp/discord/discord_bot.db` -- Student bot (chat, tickets, FAQ)
- `.tmp/discord/nova_sales.db` -- Sales bot (chat, FAQ)
- `.tmp/discord/nova_student_learning.db` -- Student learning patterns
- `.tmp/discord/nova_sales_learning.db` -- Sales learning patterns
- `.tmp/coaching/students.db` -- Student profiles + milestones
- Backups: `/Users/Shared/antigravity/memory/backups/YYYY-MM-DD/`

## Common Issues
1. **"Chat is temporarily unavailable"** -- Proxy is down. Check `lsof -i :5055`. Restart with `launchctl unload/load com.sabbo.claude-cli-proxy`.
2. **Bot not responding** -- Check `launchctl list | grep nova`. PID should be non-negative.
3. **Stale data** -- Sales bot caches data for 5 min. Restart bot to clear cache.
4. **Missing slash commands** -- Commands sync on startup. Restart the bot.
