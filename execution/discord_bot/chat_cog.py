"""Chat Cog — /ask slash command + DM handler + Claude API integration."""

import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from .database import BotDatabase
from .knowledge import (
    build_knowledge_block,
    get_relevant_knowledge,
    track_question,
)
from nova_core.knowledge import maybe_auto_generate_faq
from .security import (
    RateLimiter,
    filter_output,
    sanitize_input,
    wrap_user_input,
)

from .system_prompt import build_system_prompt

# Learning engine — tracks student interaction patterns
try:
    from .learning_engine import StudentLearningEngine
    _learning = StudentLearningEngine()
except Exception:
    _learning = None

# Student query router — fetches personalized student data
try:
    from .student_queries import StudentQueryRouter
    _query_router = StudentQueryRouter()
except Exception:
    _query_router = None

# 247profits SaaS client for richer student context
try:
    from .saas_client import ProfitsSaasClient
    _saas_client = ProfitsSaasClient()
except Exception:
    _saas_client = None

# Student DB for context injection
STUDENTS_DB = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"


def _get_student_context(discord_user_id):
    """Look up student profile by Discord ID. Returns context dict or None."""
    if not STUDENTS_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(STUDENTS_DB), timeout=5)
        conn.row_factory = sqlite3.Row
        student = conn.execute(
            "SELECT name, tier, current_milestone, health_score, risk_level, "
            "capital, status, subscription_tier, start_date "
            "FROM students WHERE discord_user_id = ? AND status = 'active'",
            (str(discord_user_id),),
        ).fetchone()
        if not student:
            conn.close()
            return None

        sid = conn.execute(
            "SELECT id FROM students WHERE discord_user_id = ?",
            (str(discord_user_id),),
        ).fetchone()["id"]

        # Get milestones
        milestones = conn.execute(
            "SELECT milestone, status FROM milestones WHERE student_id = ? AND status = 'completed'",
            (sid,),
        ).fetchall()

        # Get recent check-in mood
        last_checkin = conn.execute(
            "SELECT mood, action_items FROM check_ins "
            "WHERE student_id = ? ORDER BY date DESC LIMIT 1",
            (sid,),
        ).fetchone()

        conn.close()

        ctx = {
            "studentTier": "tier_" + student["tier"].lower() if student["tier"] else None,
            "currentMilestone": student["current_milestone"],
            "healthScore": student["health_score"],
            "riskLevel": student["risk_level"],
            "milestones": [m["milestone"] for m in milestones],
        }
        if last_checkin:
            if last_checkin["mood"]:
                ctx["lastMood"] = last_checkin["mood"]
            if last_checkin["action_items"]:
                ctx["lastBlockers"] = last_checkin["action_items"]
        return ctx
    except Exception:
        return None


def _log_chat_to_nova(user_id: str, platform: str, question: str, answer: str,
                      channel_id: str = "", tokens_in: int = 0, tokens_out: int = 0):
    """Log every chat interaction to nova.db for audit trail."""
    try:
        from nova_core.database import get_conn
        conn = get_conn()
        conn.execute(
            "INSERT INTO chat_log (user_id, platform, channel_id, question, answer, "
            "tokens_in, tokens_out, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, platform, channel_id, question[:2000], answer[:4000],
             tokens_in, tokens_out, datetime.utcnow().isoformat()),
        )
        conn.commit()
    except Exception:
        pass  # Logging should never break the bot

try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

# Proxy health tracker — auto-fallback if proxy dies
class _ProxyHealth:
    def __init__(self):
        self.failures = 0
        self.max_failures = 3
        self.is_down = False
        self.last_alert_ts = 0
        _wh = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.webhook_url = _wh if _wh.startswith("https://discord.com/api/webhooks/") else ""

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.max_failures and not self.is_down:
            self.is_down = True
            self._alert(f"⚠️ **Nova Student proxy DOWN** — switching to API fallback after {self.failures} failures")
            print(f"[nova-student] Proxy marked DOWN after {self.failures} failures", file=sys.stderr)

    def record_success(self):
        if self.is_down:
            self.is_down = False
            self._alert("✅ **Nova Student proxy RECOVERED** — switching back to proxy")
            print("[nova-student] Proxy recovered", file=sys.stderr)
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


def _split_message(text, max_len=1900):
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


class ChatCog(commands.Cog):
    """Handles /ask command and DM conversations with Claude API."""

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.rate_limiter = RateLimiter()
        self.base_system_prompt = build_system_prompt()

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

        self.model = os.getenv("DISCORD_CHAT_MODEL", "claude-haiku-4-5-20251001")

    async def _handle_question(self, user_id, channel_id, question, respond_func,
                               user_name="", channel_context=""):
        """Core logic shared by /ask and DM handler.

        Args:
            user_id: Discord user ID
            channel_id: Discord channel ID
            question: Raw question text
            respond_func: async callable(text) to send response chunks
            user_name: Display name for logging
            channel_context: Recent channel messages for conversational context
        """
        # Layer 0: Input length guard
        if len(question) > 4000:
            question = question[:4000]

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
                "I'm Nova — I can only help with Amazon FBA, ecommerce, and marketing questions. "
                "What would you like to know?"
            )
            return

        if not sanitized:
            await respond_func("Please ask a question and I'll do my best to help!")
            return

        if not self.claude:
            await respond_func("Chat is temporarily unavailable. Please try again later.")
            return

        # Load full conversation history for this thread/channel
        history = self.db.get_chat_history(str(user_id), str(channel_id), limit=100)

        # Track question + get relevant FAQ entries (non-critical — fallback on error)
        cluster_id, frequency = 0, 0
        faq_entries = []
        knowledge_block = ""
        try:
            cluster_id, frequency = track_question(self.db, str(user_id), sanitized)
            faq_entries = get_relevant_knowledge(self.db, sanitized, limit=3)
            knowledge_block = build_knowledge_block(faq_entries)
            maybe_auto_generate_faq(cluster_id, frequency)
        except Exception as _kb_err:
            print(f"[chat-cog] Knowledge system error (non-fatal): {_kb_err}", file=sys.stderr)

        # Detect student data intents for query routing
        intents = []
        if _query_router:
            try:
                intents = _query_router.detect_intent(sanitized)
            except Exception:
                pass

        # ── Student context injection ────────────────────────────────────
        # Look up this Discord user in students.db for personalized responses
        student_ctx = _get_student_context(user_id)
        if student_ctx:
            # Build per-user prompt with student context via nova_core
            from nova_core.prompts import build_prompt
            system_prompt = build_prompt("discord", faq_entries=faq_entries, platform_context={
                "studentTier": student_ctx.get("studentTier"),
                "currentMilestone": student_ctx.get("currentMilestone"),
                "healthScore": student_ctx.get("healthScore"),
                "riskLevel": student_ctx.get("riskLevel"),
                "milestones": student_ctx.get("milestones", []),
                "lastMood": student_ctx.get("lastMood"),
                "lastBlockers": student_ctx.get("lastBlockers"),
            })
        else:
            system_prompt = self.base_system_prompt

        # Build messages array
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Wrap user input in boundary tags (injection defense)
        wrapped_input = wrap_user_input(sanitized)

        # Inject recent channel conversation for context (so Nova knows what was discussed)
        if channel_context:
            wrapped_input = f"<recent_channel_messages>\n{channel_context}\n</recent_channel_messages>\n\n{wrapped_input}"

        if knowledge_block and not student_ctx:
            # Only prepend knowledge block if not already in the prompt via build_prompt
            wrapped_input = f"{knowledge_block}\n\n{wrapped_input}"

        # Auto-fetch student-specific data based on question intent
        if _query_router and intents:
            try:
                query_context = _query_router.fetch_data(intents, sanitized, str(user_id))
                if query_context:
                    wrapped_input = f"<student_data>\n{query_context}\n</student_data>\n\n{wrapped_input}"
            except Exception:
                pass

        # Inject SaaS chat history + action plan context
        if _saas_client:
            try:
                saas_ctx = _saas_client.get_student_context(str(user_id))
                if saas_ctx:
                    wrapped_input = f"<saas_context>\n{saas_ctx}\n</saas_context>\n\n{wrapped_input}"
            except Exception:
                pass

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
                max_tokens=1800,
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
                        model=self.model, max_tokens=1800,
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
                        model=self.model, max_tokens=1800,
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

        # Save to chat history (discord_bot.db)
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
                pass

        # ── Audit trail: log to nova.db ──────────────────────────────────
        _log_chat_to_nova(str(user_id), "discord", sanitized, filtered_reply,
                          str(channel_id), tokens_in, tokens_out)

        # Log
        self.db.record_rate_limit(str(user_id), "chat")
        self.db.log_audit(str(user_id), "chat", f"model={self.model} in={tokens_in} out={tokens_out}")

        # Send response (chunked if needed)
        chunks = _split_message(filtered_reply)
        for chunk in chunks:
            msg = await respond_func(chunk)

            # Add reaction buttons for quality signal on the LAST chunk
            if chunk == chunks[-1] and msg:
                try:
                    await msg.add_reaction("👍")
                    await msg.add_reaction("👎")
                except Exception:
                    pass  # Reaction perms may be missing

    # ── /ask Slash Command ────────────────────────────────────────────────────

    @staticmethod
    async def _fetch_channel_context(channel, limit=20) -> str:
        """Fetch recent messages from the channel for conversational context.

        Captures what was being discussed so Nova can reference it.
        """
        try:
            messages = []
            async for msg in channel.history(limit=limit):
                if msg.author.bot:
                    # Include bot messages but mark them
                    messages.append(f"[{msg.author.display_name}]: {msg.content[:300]}")
                else:
                    messages.append(f"[{msg.author.display_name}]: {msg.content[:300]}")
            messages.reverse()  # Oldest first
            return "\n".join(messages) if messages else ""
        except Exception:
            return ""

    @app_commands.command(name="ask", description="Ask about Amazon FBA, ecommerce, or marketing")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        # Fetch recent channel messages for context BEFORE creating thread
        channel_context = await self._fetch_channel_context(interaction.channel)

        # Create a thread for this conversation
        thread = None
        try:
            thread_name = question[:80].strip() or "Nova Chat"
            msg = await interaction.followup.send(f"**{interaction.user.display_name}** asked: {question[:200]}")
            thread = await msg.create_thread(name=thread_name, auto_archive_duration=1440)
        except Exception:
            pass

        if thread:
            # Respond inside the thread — student can continue naturally
            async def respond(text):
                return await thread.send(text)

            await self._handle_question(
                user_id=interaction.user.id,
                channel_id=thread.id,  # Thread ID = conversation ID
                question=question,
                respond_func=respond,
                user_name=interaction.user.display_name,
                channel_context=channel_context,
            )
        else:
            # Fallback: respond directly (thread creation failed)
            async def respond_direct(text):
                return await interaction.followup.send(text)

            await self._handle_question(
                user_id=interaction.user.id,
                channel_id=interaction.channel_id,
                question=question,
                respond_func=respond_direct,
                user_name=interaction.user.display_name,
                channel_context=channel_context,
            )

    # ── Thread Follow-Up Listener ──────────────────────────────────────────
    # When a student sends a message in a Nova thread, auto-respond.
    # Bot NEVER initiates — only responds when the student writes in the thread.

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-respond to follow-up messages in Nova threads."""
        # Ignore bots (including self)
        if message.author.bot:
            return

        # Only respond in threads
        if not isinstance(message.channel, discord.Thread):
            return

        # Only respond in threads created by this bot
        # Check if the thread's parent message was from this bot
        try:
            if message.channel.owner_id != self.bot.user.id:
                return
        except Exception:
            return

        # Process the follow-up question
        async def respond(text):
            return await message.channel.send(text)

        async with message.channel.typing():
            await self._handle_question(
                user_id=message.author.id,
                channel_id=message.channel.id,  # Thread ID = same conversation
                question=message.content,
                respond_func=respond,
                user_name=message.author.display_name,
            )

    # ── Feedback Reaction Listener ────────────────────────────────────────────
    # Passively captures 👍/👎 reactions on bot messages for quality feedback.
    # Bot NEVER sends messages in response — this is read-only signal capture.

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Capture thumbs up/down reactions on bot messages for feedback."""
        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        if emoji not in ("👍", "👎"):
            return

        # Check if the reacted message is from this bot
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return
            message = await channel.fetch_message(payload.message_id)
            if message.author.id != self.bot.user.id:
                return
        except Exception:
            return

        # Find the user question that preceded this bot response
        question_text = ""
        history = self.db.get_chat_history(
            str(payload.user_id), str(payload.channel_id), limit=2
        )
        for msg in history:
            if msg["role"] == "user":
                question_text = msg["content"]
                break

        # Store feedback via nova_core
        try:
            from nova_core.feedback import store_feedback
            rating = 5 if emoji == "👍" else 1
            store_feedback(
                platform="discord",
                user_id=str(payload.user_id),
                rating=rating,
                question_text=question_text,
                answer_text=message.content[:2000],
                message_id=str(payload.message_id),
            )
        except Exception:
            pass  # Feedback storage should never break the bot

    # ── DM Handler — DISABLED (bot does not respond to DMs) ───────────────────
    # DM responses are intentionally disabled. Use /ask in the server instead.


async def setup(bot):
    await bot.add_cog(ChatCog(bot))
