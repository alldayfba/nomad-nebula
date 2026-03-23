"""Chat Cog — /ask slash command + DM handler + Claude API integration."""

import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .database import BotDatabase
from .knowledge import (
    build_knowledge_block,
    get_relevant_knowledge,
    track_question,
)
try:
    from nova_core.knowledge import maybe_auto_generate_faq
except ImportError:
    maybe_auto_generate_faq = None
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
    """Log every chat interaction to nova.db AND Supabase for cross-platform sync."""
    # Local SQLite log
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
        pass

    # Supabase sync — fire and forget
    _sync_chat_to_supabase(user_id, platform, question, answer)


def _sync_chat_to_supabase(discord_user_id: str, platform: str, question: str, answer: str):
    """Sync Discord Nova conversations to Supabase so SaaS Nova can see them."""
    try:
        import httpx
        sb_url = os.getenv("PROFITS_SUPABASE_URL") or os.getenv("STUDENT_SAAS_SUPABASE_URL", "")
        sb_key = os.getenv("PROFITS_SUPABASE_KEY") or os.getenv("STUDENT_SAAS_SUPABASE_KEY", "")
        if not sb_url or not sb_key:
            return

        headers = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}", "Content-Type": "application/json"}

        # Find the Supabase user_id from discord_user_id
        r = httpx.get(
            f"{sb_url}/rest/v1/users?discord_user_id=eq.{discord_user_id}&select=id",
            headers=headers, timeout=5.0,
        )
        users = r.json() if r.status_code == 200 else []
        if not users:
            return
        supabase_user_id = users[0]["id"]

        # Find or create a conversation for this platform
        conv_r = httpx.get(
            f"{sb_url}/rest/v1/academy_chat_conversations?user_id=eq.{supabase_user_id}&title=eq.Discord&select=id&limit=1",
            headers=headers, timeout=5.0,
        )
        convs = conv_r.json() if conv_r.status_code == 200 else []

        if convs:
            conv_id = convs[0]["id"]
            httpx.patch(
                f"{sb_url}/rest/v1/academy_chat_conversations?id=eq.{conv_id}",
                headers=headers, json={"updated_at": datetime.utcnow().isoformat()}, timeout=5.0,
            )
        else:
            cr = httpx.post(
                f"{sb_url}/rest/v1/academy_chat_conversations",
                headers={**headers, "Prefer": "return=representation"},
                json={"user_id": supabase_user_id, "title": "Discord"},
                timeout=5.0,
            )
            created = cr.json()
            conv_id = created[0]["id"] if isinstance(created, list) and created else None
            if not conv_id:
                return

        # Insert both messages
        httpx.post(
            f"{sb_url}/rest/v1/academy_chat_messages",
            headers=headers,
            json=[
                {"conversation_id": conv_id, "role": "user", "content": question[:2000]},
                {"conversation_id": conv_id, "role": "assistant", "content": answer[:4000]},
            ],
            timeout=5.0,
        )
    except Exception:
        pass  # Sync should never break the bot

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

    # Channel names created by Nova for /ask questions
    NOVA_CHANNEL_PREFIX = "nova-"
    NOVA_CATEGORY_NAME = "Nova Chats"
    AUTO_CLOSE_HOURS = 24

    def __init__(self, bot):
        self.bot = bot
        self.db = BotDatabase()
        self.rate_limiter = RateLimiter()
        self.base_system_prompt = build_system_prompt()
        self.admin_role_id = os.getenv("DISCORD_ADMIN_ROLE_ID", "")
        self._nova_category_id = None  # Cached category channel ID

        # Check for CLI proxy first (uses Max plan, no API credits needed)
        proxy_url = os.getenv("CLAUDE_PROXY_URL", "")
        api_key = os.getenv("ANTHROPIC_API_KEY2") or os.getenv("ANTHROPIC_API_KEY", "")

        self.claude_proxy = None
        self.claude_api = None
        self.saas_chat_url = os.getenv("SAAS_CHAT_URL", "https://247profits.org/api/nova/chat")
        self.saas_chat_secret = os.getenv("NOVA_API_SECRET", "")
        if AsyncAnthropic and proxy_url:
            self.claude_proxy = AsyncAnthropic(api_key="proxy", base_url=proxy_url)
        if AsyncAnthropic and api_key:
            self.claude_api = AsyncAnthropic(api_key=api_key)
        self.claude = self.claude_proxy or self.claude_api

        self.model = os.getenv("DISCORD_CHAT_MODEL", "claude-haiku-4-5-20251001")

    async def _handle_question(self, user_id, channel_id, question, respond_func,
                               user_name="", channel_context="", image_urls=None):
        """Core logic shared by /ask and DM handler.

        Args:
            user_id: Discord user ID
            channel_id: Discord channel ID
            question: Raw question text
            respond_func: async callable(text) to send response chunks
            user_name: Display name for logging
            channel_context: Recent channel messages for conversational context
            image_urls: List of image URLs from Discord attachments for vision analysis
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
            if maybe_auto_generate_faq:
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

        # ── Student/Admin context injection ─────────────────────────────
        # Check if this is the owner/admin (Sabbo)
        OWNER_DISCORD_ID = "333610222146813957"
        is_owner = str(user_id) == OWNER_DISCORD_ID

        student_ctx = _get_student_context(user_id)
        if student_ctx or is_owner:
            from nova_core.prompts import build_prompt
            platform_context = {}
            if student_ctx:
                platform_context = {
                    "studentTier": student_ctx.get("studentTier"),
                    "currentMilestone": student_ctx.get("currentMilestone"),
                    "healthScore": student_ctx.get("healthScore"),
                    "riskLevel": student_ctx.get("riskLevel"),
                    "milestones": student_ctx.get("milestones", []),
                    "lastMood": student_ctx.get("lastMood"),
                    "lastBlockers": student_ctx.get("lastBlockers"),
                }

            if is_owner:
                platform_context["isOwner"] = True
                platform_context["ownerContext"] = (
                    "This user is **Sabbo** — the founder and owner of 24/7 Profits, AllDayFBA, "
                    "and your creator. He has full admin override on everything. "
                    "When he asks 'how am I doing', report on the overall program: "
                    "student count, health scores, at-risk students, recent wins, Discord engagement, "
                    "system status. Pull from all available data — students.db, SaaS, engagement signals. "
                    "Address him directly as Sabbo. He is not a student — he is the CEO."
                )
                # Fetch real student data from Supabase via Nova API
                try:
                    import requests as _req
                    nova_secret = os.getenv("NOVA_API_SECRET", "")
                    nova_headers = {"X-Nova-Secret": nova_secret}
                    base_url = "http://127.0.0.1:5050"

                    # Get newest students with full onboarding data from Supabase
                    # Fall back to local students.db which now has imported onboarding CSV data
                    resp = _req.get(f"{base_url}/nova/students?sort=newest&limit=20", headers=nova_headers, timeout=10)
                    saas_has_data = resp.ok and len(resp.json().get("students", [])) > 0 and any(s.get("goals") for s in resp.json().get("students", []))

                    if not saas_has_data:
                        # Use local students.db (has imported onboarding form CSV data)
                        import sqlite3 as _sq
                        _students_db = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"
                        if _students_db.exists():
                            sconn = _sq.connect(str(_students_db), timeout=5)
                            sconn.row_factory = _sq.Row
                            total = sconn.execute("SELECT COUNT(*) FROM students WHERE status='active'").fetchone()[0]

                            newest = sconn.execute(
                                "SELECT name, start_date, goals, struggles, capital_to_invest, age, location, "
                                "amazon_status, has_selleramp, has_keepa, has_llc, health_score, current_milestone "
                                "FROM students WHERE status='active' ORDER BY start_date DESC LIMIT 20"
                            ).fetchall()

                            roster_lines = []
                            for s in newest:
                                line = f"  - **{s['name']}** (joined {s['start_date']}"
                                if s['age']: line += f", age {s['age']}"
                                if s['location']: line += f", {s['location'][:40]}"
                                if s['goals']: line += f", goals: {s['goals'][:80]}"
                                if s['struggles']: line += f", struggles: {s['struggles'][:80]}"
                                if s['capital_to_invest']: line += f", capital: {s['capital_to_invest']}"
                                if s['amazon_status']: line += f", amazon: {s['amazon_status'][:40]}"
                                tools = []
                                if s['has_selleramp'] == '1': tools.append('SellerAMP')
                                if s['has_keepa'] == '1': tools.append('Keepa')
                                if s['has_llc'] == '1': tools.append('LLC')
                                if tools: line += f", has: {', '.join(tools)}"
                                line += f", health: {s['health_score']}, milestone: {s['current_milestone'] or 'enrolled'})"
                                roster_lines.append(line)

                            sconn.close()
                            stats_block = f"Total active students: {total}."
                            if roster_lines:
                                stats_block += "\n\nSTUDENT ROSTER (from onboarding form responses):\n" + "\n".join(roster_lines)
                            platform_context["programStats"] = stats_block

                    elif resp.ok:
                        data = resp.json()
                        students = data.get("students", [])
                        total = data.get("count", 0)

                        roster_lines = []
                        for s in students:
                            line = f"  - **{s['name']}** (joined {s.get('joined', '?')}"
                            if s.get('experience_level'):
                                line += f", experience: {s['experience_level']}"
                            if s.get('capital_available'):
                                line += f", capital: ${s['capital_available']}"
                            if s.get('goals'):
                                line += f", goals: {s['goals'][:100]}"
                            if s.get('struggles'):
                                line += f", struggles: {s['struggles'][:100]}"
                            if s.get('onboarding_completed'):
                                line += ", onboarding: complete"
                            else:
                                line += f", onboarding step: {s.get('onboarding_step', 0)}"
                            if s.get('milestones'):
                                line += f", milestones: {', '.join(s['milestones'][:5])}"
                            if s.get('last_active'):
                                line += f", last active: {s['last_active']}"
                            line += ")"
                            roster_lines.append(line)

                        stats_block = f"Total students in SaaS: {total}."
                        if roster_lines:
                            stats_block += "\n\nSTUDENT ROSTER (from 247profits.org — real onboarding data):\n" + "\n".join(roster_lines)

                        platform_context["programStats"] = stats_block
                    else:
                        platform_context["programStats"] = "Could not fetch student data from SaaS."
                except Exception as _e:
                    platform_context["programStats"] = f"Error fetching students: {_e}"

            system_prompt = build_prompt("discord", faq_entries=faq_entries, platform_context=platform_context)
        else:
            system_prompt = self.base_system_prompt

        # Build messages array
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Wrap user input in boundary tags (injection defense)
        wrapped_input = wrap_user_input(sanitized)

        # Build multimodal content if images are attached
        _image_blocks = []
        if image_urls:
            import base64
            import httpx
            for img_url in image_urls[:4]:  # Max 4 images per message
                try:
                    # Download image and convert to base64 (Discord CDN URLs need direct fetch)
                    img_resp = httpx.get(img_url, timeout=10.0, follow_redirects=True)
                    if img_resp.status_code == 200:
                        ct = img_resp.headers.get("content-type", "image/png")
                        # Normalize content type
                        if "jpeg" in ct or "jpg" in ct:
                            media_type = "image/jpeg"
                        elif "png" in ct:
                            media_type = "image/png"
                        elif "gif" in ct:
                            media_type = "image/gif"
                        elif "webp" in ct:
                            media_type = "image/webp"
                        else:
                            media_type = "image/png"
                        b64 = base64.standard_b64encode(img_resp.content).decode("utf-8")
                        _image_blocks.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64},
                        })
                except Exception as img_err:
                    print(f"[chat-cog] Failed to download image: {img_err}", file=sys.stderr)

        # Inject recent channel conversation for context (so Nova knows what was discussed)
        # Live context = last 200 messages. For older history, pull a compressed summary from DB.
        if channel_context:
            # Check if there's older history in the DB beyond what's in live context
            older_history = self.db.get_chat_history(str(user_id), str(channel_id), limit=500)
            if len(older_history) > len(history):
                # Summarize the older messages that aren't in the live 200
                old_msgs = older_history[len(history):]
                old_summary_lines = []
                for m in old_msgs[-20:]:  # last 20 older messages as summary
                    role = "Student" if m["role"] == "user" else "Nova"
                    old_summary_lines.append(f"[{role}]: {m['content'][:150]}")
                if old_summary_lines:
                    channel_context = (
                        "--- EARLIER CONVERSATION HISTORY (summarized) ---\n"
                        + "\n".join(old_summary_lines)
                        + "\n--- RECENT MESSAGES ---\n"
                        + channel_context
                    )

            wrapped_input = f"<channel_conversation>\n{channel_context}\n</channel_conversation>\n\n{wrapped_input}"

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

        # ── Learning engine: user history + program insights ──────────
        if _learning:
            try:
                # Inject this user's past Nova conversations for continuity
                user_history = _learning.get_user_history(str(user_id), limit=5)
                if user_history:
                    hist_lines = []
                    for h in reversed(user_history):  # oldest first
                        hist_lines.append(f"Q: {h['question'][:150]}")
                        hist_lines.append(f"A: {h['answer'][:200]}")
                    wrapped_input = (
                        f"<prior_conversations>\nThis student's recent past questions with Nova:\n"
                        + "\n".join(hist_lines)
                        + "\n</prior_conversations>\n\n"
                        + wrapped_input
                    )

                # For owner/admin: inject program-wide learning insights
                if is_owner:
                    insights = _learning.get_program_insights()
                    if insights:
                        wrapped_input = (
                            f"<program_insights>\n{insights}\n</program_insights>\n\n"
                            + wrapped_input
                        )
            except Exception:
                pass

        # If images attached, build multimodal content blocks
        if _image_blocks:
            user_content = _image_blocks + [{"type": "text", "text": wrapped_input}]
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": wrapped_input})

        # Call Claude: 1) Local proxy → 2) SaaS proxy (Vercel) → 3) API key
        _call_start = _time_mod.time()
        import asyncio
        client = self.claude
        if _proxy_health.is_down and self.claude_api:
            client = self.claude_api
        elif self.claude_proxy:
            client = self.claude_proxy

        if not client and not self.saas_chat_url:
            await respond_func("Chat is temporarily unavailable. Please try again later.")
            return

        reply = None
        tokens_in = 0
        tokens_out = 0

        # Web search tool definition
        web_search_tool = {
            "name": "web_search",
            "description": "Search the web for current info about Amazon FBA, ecommerce, products, or any topic. Use when you need up-to-date data.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"],
            },
        }

        system_prompt += "\n\nYou have a web_search tool. Use it when students ask about current Amazon policies, fees, product research, or anything you're unsure about. Reference Sabbo's frameworks FIRST, then supplement with search results."

        async def _do_web_search(query: str) -> str:
            """DuckDuckGo instant answer — free, no key."""
            try:
                import aiohttp
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as r:
                        if r.status != 200:
                            return "Search unavailable."
                        d = await r.json(content_type=None)
                        parts = []
                        if d.get("AbstractText"):
                            parts.append(d["AbstractText"])
                        if d.get("Answer"):
                            parts.append(d["Answer"])
                        for t in list(d.get("RelatedTopics") or [])[:5]:
                            if isinstance(t, dict) and t.get("Text"):
                                parts.append(t["Text"])
                        return "\n\n".join(parts) if parts else "No results found."
            except Exception:
                return "Search unavailable."

        async def _call_with_tools(api_client, msgs, max_loops=3):
            """Call Claude with web_search tool support, handling tool_use responses."""
            current_msgs = list(msgs)
            for _ in range(max_loops):
                coro = api_client.messages.create(
                    model=self.model, max_tokens=1800,
                    system=system_prompt, messages=current_msgs,
                    tools=[web_search_tool],
                )
                response = await asyncio.wait_for(coro, timeout=45.0)

                # Check for tool use
                tool_block = next((b for b in response.content if b.type == "tool_use"), None)
                if tool_block and tool_block.name == "web_search":
                    search_q = (tool_block.input or {}).get("query", "")
                    search_result = await _do_web_search(search_q)
                    current_msgs.append({"role": "assistant", "content": response.content})
                    current_msgs.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": tool_block.id, "content": search_result}
                    ]})
                    continue

                # No tool use — extract text
                text_block = next((b for b in response.content if b.type == "text"), None)
                return (text_block.text if text_block else "", response.usage.input_tokens, response.usage.output_tokens)
            return ("I had trouble searching. Let me answer based on what I know.", 0, 0)

        # Attempt 1: Local Claude CLI proxy (free via Max plan)
        if client:
            try:
                result = await _call_with_tools(client, messages)
                reply, tokens_in, tokens_out = result[0], result[1], result[2]
                _proxy_health.record_success()
                _error_tracker.record_success(_time_mod.time() - _call_start)
            except Exception as e1:
                _proxy_health.record_failure()
                print(f"[chat-cog] Proxy failed: {e1}", file=sys.stderr)

        # Attempt 2: SaaS proxy on Vercel (routes through tunnel → Max plan)
        if reply is None and self.saas_chat_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.saas_chat_url,
                        json={"model": self.model, "max_tokens": 1800, "system": system_prompt, "messages": messages},
                        headers={"X-Nova-Secret": self.saas_chat_secret, "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=50),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("content") and len(data["content"]) > 0:
                                reply = data["content"][0].get("text", "")
                                tokens_in = data.get("usage", {}).get("input_tokens", 0)
                                tokens_out = data.get("usage", {}).get("output_tokens", 0)
                                _error_tracker.record_success(_time_mod.time() - _call_start)
            except Exception as e2:
                print(f"[chat-cog] SaaS proxy failed: {e2}", file=sys.stderr)

        # Attempt 3: Direct API key (costs money, last resort)
        if reply is None and self.claude_api:
            try:
                result3 = await _call_with_tools(self.claude_api, messages)
                reply, tokens_in, tokens_out = result3[0], result3[1], result3[2]
            except Exception as e3:
                self.db.log_audit(str(user_id), "api_error", str(e3)[:500])

        if reply is None:
            await respond_func("Nova is temporarily unavailable. Please try again in a moment.")
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

    # ── Nova Channel Management ──────────────────────────────────────────────

    async def _get_or_create_nova_category(self, guild):
        """Get or create the 'Nova Chats' category channel."""
        if self._nova_category_id:
            cat = guild.get_channel(self._nova_category_id)
            if cat:
                return cat

        # Look for existing category
        for cat in guild.categories:
            if cat.name.lower() == self.NOVA_CATEGORY_NAME.lower():
                self._nova_category_id = cat.id
                return cat

        # Create it — only admin + bot can see the category by default
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        admin_rid = int(self.admin_role_id) if self.admin_role_id else 0
        if admin_rid:
            admin_role = guild.get_role(admin_rid)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_channels=True
                )

        cat = await guild.create_category(self.NOVA_CATEGORY_NAME, overwrites=overwrites)
        self._nova_category_id = cat.id
        return cat

    async def _get_or_create_nova_channel(self, guild, user):
        """Get existing Nova channel for user, or create a new private one."""
        safe_name = f"{self.NOVA_CHANNEL_PREFIX}{user.display_name.lower().replace(' ', '-')[:20]}"

        # Check for existing open channel for this user
        category = await self._get_or_create_nova_category(guild)
        for ch in category.text_channels:
            if ch.topic and str(user.id) in ch.topic:
                return ch, False  # Existing channel

        # Create new private channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        admin_rid = int(self.admin_role_id) if self.admin_role_id else 0
        if admin_rid:
            admin_role = guild.get_role(admin_rid)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_channels=True
                )

        channel = await guild.create_text_channel(
            name=safe_name,
            category=category,
            overwrites=overwrites,
            topic=f"Nova chat for {user.display_name} (uid:{user.id}) — auto-closes after {self.AUTO_CLOSE_HOURS}h inactivity",
        )

        # Welcome embed
        embed = discord.Embed(
            title=f"Hey {user.display_name}!",
            description=(
                "This is your private Nova chat. Ask me anything about Amazon FBA, sourcing, or ecommerce.\n\n"
                "Just type your questions here — no need for `/ask`. I'll respond to every message.\n\n"
                f"This channel auto-closes after {self.AUTO_CLOSE_HOURS} hours of inactivity."
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Nova — 24/7 Profits AI Coach")
        await channel.send(embed=embed)

        return channel, True  # New channel

    def cog_load(self):
        self._auto_close_channels.start()

    def cog_unload(self):
        self._auto_close_channels.cancel()

    @tasks.loop(minutes=30)
    async def _auto_close_channels(self):
        """Auto-close Nova chat channels after 24h of inactivity."""
        for guild in self.bot.guilds:
            try:
                category = None
                for cat in guild.categories:
                    if cat.name.lower() == self.NOVA_CATEGORY_NAME.lower():
                        category = cat
                        break
                if not category:
                    continue

                for channel in category.text_channels:
                    if not channel.name.startswith(self.NOVA_CHANNEL_PREFIX):
                        continue

                    # Check last message time
                    last_msg = None
                    async for msg in channel.history(limit=1):
                        last_msg = msg

                    if not last_msg:
                        continue

                    age_hours = (datetime.utcnow() - last_msg.created_at.replace(tzinfo=None)).total_seconds() / 3600
                    if age_hours >= self.AUTO_CLOSE_HOURS:
                        try:
                            # Send closing notice
                            await channel.send(
                                embed=discord.Embed(
                                    title="Chat Closed",
                                    description="This chat has been closed due to inactivity. Use `/ask` anytime to start a new one!",
                                    color=discord.Color.greyple(),
                                )
                            )
                            import asyncio
                            await asyncio.sleep(5)
                            await channel.delete(reason=f"Nova auto-close: {self.AUTO_CLOSE_HOURS}h inactivity")
                        except Exception:
                            pass
            except Exception:
                pass

    @_auto_close_channels.before_loop
    async def _before_auto_close(self):
        await self.bot.wait_until_ready()

    @staticmethod
    async def _fetch_channel_context(channel, limit=200) -> str:
        """Fetch channel messages for conversational context.

        200 messages covers a full day of active 1-on-1 coaching.
        Keeps prompt under ~15K tokens to avoid timeouts.
        """
        try:
            messages = []
            async for msg in channel.history(limit=limit):
                prefix = "[Nova]" if msg.author.bot else f"[{msg.author.display_name}]"
                content = msg.content[:300] if msg.content else ""
                if content:
                    messages.append(f"{prefix}: {content}")
            messages.reverse()
            return "\n".join(messages) if messages else ""
        except Exception:
            return ""

    # ── /ask Slash Command ────────────────────────────────────────────────────

    def _is_admin(self, member: discord.Member) -> bool:
        """Check if a guild member has the admin role."""
        if not self.admin_role_id:
            return False
        admin_rid = int(self.admin_role_id)
        return any(r.id == admin_rid for r in member.roles)

    @app_commands.command(name="ask", description="Ask about Amazon FBA, ecommerce, or marketing")
    @app_commands.describe(question="Your question")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command only works in a server.", ephemeral=True)
            return

        # If admin is using /ask inside an existing nova-* channel, respond inline
        is_admin = isinstance(interaction.user, discord.Member) and self._is_admin(interaction.user)
        current_channel = interaction.channel
        in_nova_channel = (
            current_channel
            and hasattr(current_channel, 'name')
            and current_channel.name.startswith(self.NOVA_CHANNEL_PREFIX)
            and hasattr(current_channel, 'category')
            and current_channel.category
            and current_channel.category.name.lower() == self.NOVA_CATEGORY_NAME.lower()
        )

        if is_admin and in_nova_channel:
            # Admin is viewing a student's Nova channel — respond inline
            channel = current_channel

            await channel.send(f"**{interaction.user.display_name} (admin):** {question}")

            await interaction.followup.send("Answering in this channel.", ephemeral=True)

            async def respond(text):
                return await channel.send(text)

            # Fetch recent channel context so Nova knows the conversation
            channel_context = await self._fetch_channel_context(channel)

            async with channel.typing():
                await self._handle_question(
                    user_id=interaction.user.id,
                    channel_id=channel.id,
                    question=question,
                    respond_func=respond,
                    user_name=interaction.user.display_name,
                    channel_context=channel_context,
                )
            return

        # Default: get or create private Nova channel for this user
        channel, is_new = await self._get_or_create_nova_channel(guild, interaction.user)

        # Send the question in the channel
        await channel.send(f"**{interaction.user.display_name}:** {question}")

        # Notify user where to find their chat
        await interaction.followup.send(
            f"Head to {channel.mention} — I'm answering there!",
            ephemeral=True,
        )

        # Respond in the private channel
        async def respond(text):
            return await channel.send(text)

        async with channel.typing():
            await self._handle_question(
                user_id=interaction.user.id,
                channel_id=channel.id,
                question=question,
                respond_func=respond,
                user_name=interaction.user.display_name,
                channel_context="",
            )

    # ── Private Channel Follow-Up Listener ─────────────────────────────────
    # When a student sends a message in their Nova channel, auto-respond.

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-respond in Nova channels + respond to @Nova mentions in any channel."""
        if message.author.bot:
            return
        if not message.guild:
            return

        # Detect context
        is_nova_channel = (
            message.channel.name.startswith(self.NOVA_CHANNEL_PREFIX)
            and message.channel.category
            and message.channel.category.name.lower() == self.NOVA_CATEGORY_NAME.lower()
        )
        bot_mentioned = self.bot.user in message.mentions if message.mentions else False
        content_lower = message.content.lower().strip()
        nova_prefix = content_lower.startswith("nova,") or content_lower.startswith("nova ")
        nova_invoked = bot_mentioned or nova_prefix

        if not is_nova_channel and not nova_invoked:
            return  # Not a Nova channel and Nova wasn't called — ignore

        is_admin = isinstance(message.author, discord.Member) and self._is_admin(message.author)

        # In Nova channels: channel owner gets auto-response, everyone else needs @Nova
        # Outside Nova channels: everyone needs @Nova
        if is_nova_channel:
            topic = message.channel.topic or ""
            is_channel_owner = f"uid:{message.author.id}" in topic
            if not is_channel_owner and not nova_invoked:
                return  # Not the owner and didn't invoke Nova
        else:
            if not nova_invoked:
                return  # Outside Nova channel, must invoke

        # Fetch full channel conversation so Nova has complete context
        channel_context = await self._fetch_channel_context(message.channel)

        async def respond(text):
            return await message.channel.send(text)

        # Extract image URLs from attachments for vision analysis
        image_urls = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith('image/'):
                image_urls.append(att.url)

        question_text = message.content or ""
        if not question_text and image_urls:
            question_text = "What do you see in this image? Analyze it in the context of Amazon FBA."

        async with message.channel.typing():
            await self._handle_question(
                user_id=message.author.id,
                channel_id=message.channel.id,
                question=question_text,
                respond_func=respond,
                user_name=message.author.display_name,
                channel_context=channel_context,
                image_urls=image_urls if image_urls else None,
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
