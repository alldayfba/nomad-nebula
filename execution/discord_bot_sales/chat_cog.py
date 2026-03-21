"""Chat Cog — /ask slash command + Claude API integration for Nova Sales."""

from __future__ import annotations

import os
import sys
import threading

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .database import BotDatabase
from .knowledge import (
    build_knowledge_block,
    get_relevant_knowledge,
    maybe_auto_generate_faq,
    track_question,
)
from .security import (
    RateLimiter,
    filter_output,
    sanitize_input,
    wrap_user_input,
)
from .system_prompt import build_system_prompt, build_data_prompt, build_live_data_block

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from execution.dashboard_client import DashboardClient
    _dashboard = DashboardClient()
except Exception:
    _dashboard = None

# Learning engine — tracks patterns, evolves knowledge
try:
    from .learning_engine import LearningEngine
    _learning = LearningEngine()
except Exception:
    _learning = None

# Sales query router — fetches specific data on demand
try:
    from .sales_queries import SalesQueryRouter
    _query_router = SalesQueryRouter(_dashboard) if _dashboard else None
except Exception:
    _query_router = None

# Chat context tracker — reads channel messages passively
try:
    from .chat_context import ChatContextTracker
    _chat_context = ChatContextTracker(max_messages=50, max_age_seconds=3600)
except Exception:
    _chat_context = None

# Proxy health tracker — auto-fallback if proxy dies
class _ProxyHealth:
    def __init__(self):
        self.failures = 0
        self.max_failures = 3
        self.is_down = False
        self.last_alert_ts = 0
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.max_failures and not self.is_down:
            self.is_down = True
            self._alert(f"⚠️ **Nova Sales proxy DOWN** — switching to API fallback after {self.failures} failures")
            print(f"[nova-sales] Proxy marked DOWN after {self.failures} failures", file=sys.stderr)

    def record_success(self):
        if self.is_down:
            self.is_down = False
            self._alert("✅ **Nova Sales proxy RECOVERED** — switching back to proxy")
            print("[nova-sales] Proxy recovered", file=sys.stderr)
        self.failures = 0

    def _alert(self, message: str):
        import time as _t
        if _t.time() - self.last_alert_ts < 300:  # Max 1 alert per 5 min
            return
        self.last_alert_ts = _t.time()
        if self.webhook_url:
            try:
                import requests as _req
                _req.post(self.webhook_url, json={"content": message}, timeout=5)
            except Exception:
                pass

_proxy_health = _ProxyHealth()

import time as _time_mod


class _ErrorTracker:
    def __init__(self):
        self.total_requests = 0
        self.errors = 0
        self.timeouts = 0
        self.total_latency = 0.0
        self.start_time = _time_mod.time()

    def record_success(self, latency: float):
        self.total_requests += 1
        self.total_latency += latency

    def record_error(self):
        self.total_requests += 1
        self.errors += 1

    def record_timeout(self):
        self.total_requests += 1
        self.timeouts += 1

    def get_stats(self) -> dict:
        uptime = _time_mod.time() - self.start_time
        successful = self.total_requests - self.errors - self.timeouts
        avg_latency = (self.total_latency / successful) if successful > 0 else 0
        error_rate = (self.errors + self.timeouts) / self.total_requests * 100 if self.total_requests else 0
        return {
            "uptime_hours": round(uptime / 3600, 1),
            "total_requests": self.total_requests,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "error_rate_pct": round(error_rate, 1),
            "avg_latency_s": round(avg_latency, 1),
            "proxy_status": "DOWN" if _proxy_health.is_down else "OK",
        }


_error_tracker = _ErrorTracker()


def _split_message(text: str, max_len: int = 1900) -> list:
    """Split a long message into chunks that fit Discord's 2000-char limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            # Fall back to splitting at space
            split_at = text.rfind(" ", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


import time as _time

_LIVE_DATA_CACHE: dict = {}
_LIVE_DATA_TTL = 300  # 5 minutes


def _fetch_live_data() -> dict:
    """Fetch live dashboard data with 5-minute cache."""
    now = _time.time()
    if _LIVE_DATA_CACHE.get("ts", 0) + _LIVE_DATA_TTL > now:
        return _LIVE_DATA_CACHE.get("data", {})

    data = {}
    if _dashboard:
        for key, fn in [
            ("kpi",              lambda: _dashboard.get_kpi_snapshot("mtd")),
            ("team",             lambda: _dashboard.get_team_performance("mtd")),
            ("upcoming_calls",   lambda: _dashboard.get_upcoming_calls()),
            ("recent_calls",     lambda: _dashboard.get_recent_calls(days=30)),
            ("funnel",           lambda: _dashboard.get_funnel_data("mtd")),
            ("objections",       lambda: _dashboard.get_objection_data()),
            ("noshow",           lambda: _dashboard.get_noshow_analysis()),
            ("roster",           lambda: _dashboard.get_team_roster()),
            ("insights",         lambda: _dashboard.get_insights()),
            ("quotas",           lambda: _dashboard.get_quotas()),
            ("revenue",          lambda: _dashboard.get_revenue_metrics()),
            ("lead_sources",     lambda: _dashboard.get_lead_sources("mtd")),
            ("closer_eoc",       lambda: _dashboard.get_closer_submissions()),
            ("sdr_activity",     lambda: _dashboard.get_sdr_submissions()),
            ("commissions",      lambda: _dashboard.get_commissions()),
            ("data_health",      lambda: _dashboard.get_data_health()),
            # GHL live CRM data
            ("ghl_pipeline",     lambda: _dashboard.get_ghl_pipelines()),
            ("ghl_appointments", lambda: _dashboard.get_ghl_appointments()),
        ]:
            try:
                data[key] = fn()
            except Exception:
                pass

    _LIVE_DATA_CACHE["data"] = data
    _LIVE_DATA_CACHE["ts"] = now
    return data


def _sync_outcomes_background():
    """Background thread: sync EOC reports into learning engine on boot + every 15min."""
    if not _dashboard or not _learning:
        return
    try:
        # Get team member map for name resolution
        roster = _dashboard.get_team_roster() or []
        member_map = {}
        for m in roster:
            mid = m.get("id", "")
            name = m.get("full_name") or m.get("name") or mid
            if mid:
                member_map[mid] = name

        # Sync last 30 days of EOC reports
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        eoc = _dashboard.get_closer_submissions(start=since) or []
        if eoc:
            _learning.sync_sales_outcomes(eoc, member_map)
            print(f"[nova-sales] Learning engine synced {len(eoc)} EOC reports", file=sys.stderr)
    except Exception as e:
        print(f"[nova-sales] Learning sync error: {e}", file=sys.stderr)


class ChatCog(commands.Cog):
    """Handles /ask command with Claude API integration for sales Q&A."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.rate_limiter = RateLimiter()

        # Check for CLI proxy first (uses Max plan, no API credits needed)
        proxy_url = os.getenv("CLAUDE_PROXY_URL", "")
        api_key = os.getenv("ANTHROPIC_API_KEY2") or os.getenv("ANTHROPIC_API_KEY", "")

        self.claude_proxy = None
        self.claude_api = None
        if AsyncAnthropic and proxy_url:
            self.claude_proxy = AsyncAnthropic(api_key="proxy", base_url=proxy_url)
        if AsyncAnthropic and api_key:
            self.claude_api = AsyncAnthropic(api_key=api_key)
        self.claude = self.claude_proxy or self.claude_api

        # Sonnet for data-aware Q&A — questions may reference live pipeline
        self.model = os.getenv("DISCORD_SALES_CHAT_MODEL", "claude-sonnet-4-6")

        # Initial learning sync (background thread so bot starts fast)
        threading.Thread(target=_sync_outcomes_background, daemon=True).start()

        # Periodic sync every 15 minutes
        self._sync_loop.start()

    def cog_unload(self):
        self._sync_loop.cancel()

    @tasks.loop(minutes=15)
    async def _sync_loop(self):
        """Re-sync EOC data every 15 minutes so learning engine stays fresh."""
        threading.Thread(target=_sync_outcomes_background, daemon=True).start()

    @_sync_loop.before_loop
    async def _before_sync(self):
        await self.bot.wait_until_ready()

    async def _handle_question(self, user_id, channel_id, question, respond_func, user_name=""):
        """Core Q&A logic shared by slash commands.

        Args:
            user_id: Discord user ID
            channel_id: Discord channel ID
            question: Raw question text
            respond_func: async callable(text) to send response chunks
            user_name: Display name for logging
        """
        # Layer 1: Blacklist check
        if self.db.is_blacklisted(user_id):
            await respond_func("You are currently restricted from using this bot.")
            return

        # Layer 2: Rate limit
        if not self.rate_limiter.check(user_id, "chat"):
            self.db.record_rate_limit(str(user_id), "chat")
            await respond_func("You're sending messages too fast. Please wait a minute and try again.")
            return

        # Layer 3: Input sanitization + injection detection
        sanitized, is_injection = sanitize_input(question)

        if is_injection:
            self.db.log_audit(str(user_id), "injection_attempt", question[:500])

            # Auto-blacklist after 5 injection attempts in 1 hour
            recent_injections = self.db.count_recent_audit(str(user_id), "injection_attempt", 3600)
            if recent_injections >= 5:
                self.db.add_blacklist(str(user_id), "Auto-blacklisted: repeated prompt injection attempts",
                                     "system")
                self.db.log_audit(str(user_id), "auto_blacklist", "5+ injection attempts in 1 hour")
                await respond_func("Your access has been restricted due to repeated policy violations.")
                return

            await respond_func(
                "I'm Nova Sales — I help with sales scripts, objections, frameworks, and training. "
                "What would you like to know?"
            )
            return

        if not sanitized:
            await respond_func("Please ask a question and I'll do my best to help!")
            return

        if not self.claude:
            await respond_func("Chat is temporarily unavailable. Please try again later.")
            return

        # Load conversation history
        history = self.db.get_chat_history(str(user_id), str(channel_id), limit=10)

        # Track question + get relevant FAQ entries
        cluster_id, frequency = track_question(self.db, str(user_id), sanitized)
        faq_entries = get_relevant_knowledge(self.db, sanitized, limit=3)
        knowledge_block = build_knowledge_block(faq_entries)

        # Maybe auto-generate FAQ candidate if cluster is hot
        maybe_auto_generate_faq(self.db, cluster_id, frequency)

        # Detect intents early so we can pick the right prompt weight
        intents = []
        if _query_router:
            try:
                intents = _query_router.detect_intent(sanitized)
            except Exception:
                pass

        # Data-only intents get a lightweight prompt (~2K tokens vs ~14K)
        DATA_INTENTS = {"contact_lookup", "call_history", "contact_notes", "payment_query",
                        "pipeline_stage", "rep_performance", "lead_activity", "offer_breakdown"}
        TRAINING_INTENTS = {"objection_analysis"}  # needs frameworks
        is_data_question = bool(intents) and all(i in DATA_INTENTS for i in intents)

        live_data = _fetch_live_data()
        learned_insights = ""
        if _learning:
            try:
                learned_insights = _learning.get_contextual_insights(sanitized)
            except Exception:
                pass

        # Get recent team chat context (passive read)
        chat_context_block = ""
        if _chat_context:
            try:
                chat_context_block = _chat_context.get_recent_context(limit=15)
            except Exception:
                pass

        if is_data_question:
            system_prompt = build_data_prompt(
                live_data=live_data or None,
                learned_insights=learned_insights,
            )
        else:
            system_prompt = build_system_prompt(
                knowledge_entries=faq_entries or None,
                live_data=live_data or None,
                learned_insights=learned_insights,
            )

        # Append team chat context so Nova knows what the team is discussing
        if chat_context_block:
            system_prompt += f"\n\n{chat_context_block}"

        # Build messages array
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Wrap user input in boundary tags (Layer 2 injection defense)
        wrapped_input = wrap_user_input(sanitized)
        if knowledge_block:
            wrapped_input = f"{knowledge_block}\n\n{wrapped_input}"

        # Auto-fetch relevant data based on question intent (intents already detected above)
        if _query_router and intents:
            try:
                query_context = _query_router.fetch_data(intents, sanitized)
                if query_context:
                    wrapped_input = f"<sales_data>\n{query_context}\n</sales_data>\n\n{wrapped_input}"
            except Exception:
                pass  # Query routing should never break the bot

        messages.append({"role": "user", "content": wrapped_input})

        # Call Claude with timeout + proxy fallback
        _call_start = _time_mod.time()
        try:
            import asyncio
            # Pick client: use proxy unless it's marked down
            client = self.claude
            if _proxy_health.is_down and self.claude_api:
                client = self.claude_api
            elif self.claude_proxy:
                client = self.claude_proxy

            if not client:
                await respond_func("Chat is temporarily unavailable. Please try again later.")
                return

            coro = client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=system_prompt,
                messages=messages,
            )
            response = await asyncio.wait_for(coro, timeout=25.0)

            reply = response.content[0].text
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            _proxy_health.record_success()
            _error_tracker.record_success(_time_mod.time() - _call_start)

        except asyncio.TimeoutError:
            _proxy_health.record_failure()
            _error_tracker.record_timeout()
            # Retry once with API fallback if available
            if self.claude_api and client != self.claude_api:
                try:
                    coro2 = self.claude_api.messages.create(
                        model=self.model, max_tokens=1500,
                        system=system_prompt, messages=messages,
                    )
                    response = await asyncio.wait_for(coro2, timeout=25.0)
                    reply = response.content[0].text
                    tokens_in = response.usage.input_tokens
                    tokens_out = response.usage.output_tokens
                except Exception:
                    await respond_func("Nova is taking too long — try again in a moment.")
                    return
            else:
                await respond_func("Nova is taking too long — try again in a moment.")
                return
        except Exception as e:
            _proxy_health.record_failure()
            _error_tracker.record_error()
            self.db.log_audit(str(user_id), "api_error", str(e)[:500])
            # Try API fallback
            if self.claude_api and client != self.claude_api:
                try:
                    coro3 = self.claude_api.messages.create(
                        model=self.model, max_tokens=1500,
                        system=system_prompt, messages=messages,
                    )
                    response = await asyncio.wait_for(coro3, timeout=25.0)
                    reply = response.content[0].text
                    tokens_in = response.usage.input_tokens
                    tokens_out = response.usage.output_tokens
                except Exception:
                    await respond_func("Something went wrong. Please try again in a moment.")
                    return
            else:
                await respond_func("Something went wrong. Please try again in a moment.")
                return

        # Layer 4: Output filtering
        filtered_reply, leak_detected = filter_output(reply)
        if leak_detected:
            self.db.log_audit(str(user_id), "output_leak_blocked", reply[:500])

        # Save to chat history
        self.db.add_chat_message(str(user_id), str(channel_id), "user", sanitized,
                                self.model, tokens_in, tokens_out)
        self.db.add_chat_message(str(user_id), str(channel_id), "assistant", filtered_reply,
                                self.model, 0, 0)

        # Learning engine: log interaction for pattern mining
        if _learning:
            try:
                _learning.log_interaction(
                    user_id=str(user_id),
                    user_name=user_name,
                    question=sanitized,
                    answer=filtered_reply,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
            except Exception:
                pass  # Learning should never break the bot

        # Log
        self.db.record_rate_limit(str(user_id), "chat")
        self.db.log_audit(str(user_id), "chat", f"model={self.model} in={tokens_in} out={tokens_out}")

        # Send response (chunked if needed)
        chunks = _split_message(filtered_reply)
        for chunk in chunks:
            msg = await respond_func(chunk)

            # Add reaction buttons for quality signal on the last chunk
            if chunk == chunks[-1] and msg:
                try:
                    await msg.add_reaction("👍")
                    await msg.add_reaction("👎")
                except Exception:
                    pass  # Reaction perms may be missing

    # ── /ask Slash Command ────────────────────────────────────────────────────

    @app_commands.command(name="ask", description="Ask Nova Sales a sales question")
    @app_commands.describe(question="Your sales question — scripts, objections, frameworks, techniques")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        async def respond(text):
            return await interaction.followup.send(text)

        await self._handle_question(
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            question=question,
            respond_func=respond,
            user_name=interaction.user.display_name,
        )

    # ── /pipeline Slash Command ────────────────────────────────────────────

    @app_commands.command(name="pipeline", description="Show today's calls and live pipeline status")
    async def pipeline(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        lines = ["**Pipeline Status**\n"]

        live_data = _fetch_live_data()

        # KPI summary
        kpi = live_data.get("kpi", {})
        if kpi:
            closer = kpi.get("closer", kpi)
            calls_taken = closer.get("calls_taken", "N/A")
            showed = closer.get("showed", "N/A")
            closed = closer.get("closed", "N/A")
            rev = float(closer.get("revenue_collected", 0) or 0)
            show_rate = closer.get("show_rate", 0) or 0
            close_rate = closer.get("close_rate", 0) or 0
            lines.append("**MTD KPIs:**")
            lines.append(f"- Calls: {calls_taken}")
            lines.append(f"- Shows: {showed}")
            lines.append(f"- Closed: {closed}")
            lines.append(f"- Revenue: ${rev:,.0f}")
            lines.append(f"- Show Rate: {show_rate:.1f}%")
            lines.append(f"- Close Rate: {close_rate:.1f}%")
            lines.append("")

        # Today's calls
        calls = live_data.get("upcoming_calls") or []
        if calls:
            lines.append(f"**Today's Calls ({len(calls)}):**")
            for c in calls[:10]:
                name = c.get("contact_name") or "Unknown"
                time = c.get("start_time") or c.get("scheduled_for") or ""
                status = c.get("status") or ""
                closer = c.get("closer") or ""
                line = f"- {name}"
                if time:
                    line += f" @ {time[:16]}"
                if status:
                    line += f" ({status})"
                if closer:
                    line += f" -> {closer}"
                lines.append(line)
            lines.append("")
        else:
            lines.append("**Today's Calls:** None in system\n")

        # Team performance
        team = live_data.get("team", {})
        reps = team.get("reps", []) if isinstance(team, dict) else []
        if reps:
            lines.append("**Rep Performance (MTD):**")
            for rep in reps[:5]:
                name = rep.get("name", "Unknown")
                cash = float(rep.get("revenue", rep.get("cash_collected", 0)) or 0)
                cr = rep.get("close_rate", 0) or 0
                lines.append(f"- {name}: ${cash:,.0f} | {cr:.0f}% close rate")
            lines.append("")

        # Insights
        insights = live_data.get("insights", {})
        if insights and isinstance(insights, dict):
            pace = insights.get("revenue_pace")
            proj = insights.get("projected_eom_revenue")
            if pace:
                lines.append(f"**Revenue Pace:** ${float(pace):,.0f}/day")
            if proj:
                lines.append(f"**Projected EOM:** ${float(proj):,.0f}")

        await interaction.followup.send("\n".join(lines))

    # ── /learning Slash Command ────────────────────────────────────────────

    @app_commands.command(name="learning", description="Show what Nova has learned from real sales data")
    async def learning_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not _learning:
            await interaction.followup.send("Learning engine not loaded.")
            return

        stats = _learning.get_stats()
        insights = _learning.get_contextual_insights("sales performance overview")

        lines = ["**Nova Sales Learning Engine**\n"]
        lines.append(f"- Interactions logged: {stats.get('total_interactions', 0)}")
        lines.append(f"- Sales outcomes tracked: {stats.get('total_outcomes_tracked', 0)}")
        lines.append(f"- Patterns learned: {stats.get('learned_patterns', 0)}")
        lines.append(f"- Rep profiles built: {stats.get('rep_profiles', 0)}")

        top = stats.get("top_topics", [])
        if top:
            lines.append("\n**Top Topics Asked:**")
            for t in top:
                lines.append(f"- {t['topic']}: {t['count']}x")

        if insights:
            lines.append(f"\n**Live Insights:**\n{insights[:1500]}")

        await interaction.followup.send("\n".join(lines))

    # ── /bot-health Slash Command ────────────────────────────────────────

    @app_commands.command(name="bot-health", description="[Admin] Show Nova Sales health metrics")
    async def nova_health(self, interaction: discord.Interaction):
        admin_role = int(os.getenv("DISCORD_SALES_ADMIN_ROLE_ID", "0"))
        if not any(r.id == admin_role for r in interaction.user.roles):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        stats = _error_tracker.get_stats()
        learning_stats = _learning.get_stats() if _learning else {}
        lines = ["**Nova Sales Health**\n"]
        lines.append(f"- Uptime: {stats['uptime_hours']}h")
        lines.append(f"- Requests: {stats['total_requests']}")
        lines.append(f"- Errors: {stats['errors']} | Timeouts: {stats['timeouts']}")
        lines.append(f"- Error rate: {stats['error_rate_pct']}%")
        lines.append(f"- Avg latency: {stats['avg_latency_s']}s")
        lines.append(f"- Proxy: {stats['proxy_status']}")
        if learning_stats:
            lines.append(f"\n**Learning Engine:**")
            lines.append(f"- Interactions: {learning_stats.get('total_interactions', 0)}")
            lines.append(f"- Outcomes: {learning_stats.get('total_outcomes_tracked', 0)}")
            lines.append(f"- Patterns: {learning_stats.get('learned_patterns', 0)}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── /analytics Slash Command ───────────────────────────────────────────

    @app_commands.command(name="analytics", description="[Admin] Show Nova Sales usage analytics")
    async def analytics(self, interaction: discord.Interaction):
        admin_role = int(os.getenv("DISCORD_SALES_ADMIN_ROLE_ID", "0"))
        if not any(r.id == admin_role for r in interaction.user.roles):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        lines = ["**Nova Sales Analytics**\n"]

        # Error tracking
        stats = _error_tracker.get_stats()
        lines.append(f"**Health:**")
        lines.append(f"- Uptime: {stats['uptime_hours']}h")
        lines.append(f"- Total requests: {stats['total_requests']}")
        lines.append(f"- Error rate: {stats['error_rate_pct']}%")
        lines.append(f"- Avg latency: {stats['avg_latency_s']}s")
        lines.append(f"- Proxy: {stats['proxy_status']}")

        # Learning stats
        if _learning:
            ls = _learning.get_stats()
            lines.append(f"\n**Learning Engine:**")
            lines.append(f"- Interactions: {ls.get('total_interactions', 0)}")
            lines.append(f"- Outcomes tracked: {ls.get('total_outcomes_tracked', 0)}")
            lines.append(f"- Patterns learned: {ls.get('learned_patterns', 0)}")
            lines.append(f"- Rep profiles: {ls.get('rep_profiles', 0)}")
            top = ls.get('top_topics', [])
            if top:
                lines.append(f"\n**Top Topics:**")
                for t in top:
                    lines.append(f"- {t['topic'].replace('_', ' ').title()}: {t['count']}x")

        # Chat context
        if _chat_context:
            ctx = _chat_context.get_recent_context(limit=1)
            lines.append(f"\n**Chat Context:** {'Active' if ctx else 'Empty'}")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── Passive Message Listener ──────────────────────────────────────────
    # Reads ALL channel messages to build rolling context.
    # Nova NEVER responds unprompted — this is read-only signal capture.

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Passively record channel messages for context."""
        # Ignore bots (including self)
        if message.author.bot:
            return
        # Ignore DMs
        if not message.guild:
            return
        # Record to chat context tracker
        if _chat_context and message.content:
            channel_name = getattr(message.channel, "name", str(message.channel.id))
            _chat_context.record_message(
                channel_id=str(message.channel.id),
                channel_name=channel_name,
                author_name=message.author.display_name,
                content=message.content,
            )


async def setup(bot):
    await bot.add_cog(ChatCog(bot))
