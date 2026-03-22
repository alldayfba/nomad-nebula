"""Student Query Router — fetches student-specific data for personalized responses."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

STUDENTS_DB = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"

try:
    from .saas_client import ProfitsSaasClient
    _saas = ProfitsSaasClient()
except Exception:
    _saas = None


class StudentQueryRouter:
    """Detects student data queries and fetches personalized context."""

    def detect_intent(self, question: str) -> List[str]:
        q = question.lower()
        intents = []

        if any(kw in q for kw in ["my progress", "where am i", "my milestones", "my status",
                                   "what have i done", "how far", "my journey",
                                   "how am i doing", "how am i", "how's it going",
                                   "my performance", "doing well", "check in"]):
            intents.append("my_progress")

        if any(kw in q for kw in ["what's next", "next step", "what should i do",
                                   "what now", "next milestone", "action plan"]):
            intents.append("next_steps")

        if any(kw in q for kw in ["how to source", "find products", "where to source",
                                   "product research", "what to sell"]):
            intents.append("sourcing_guide")

        if any(kw in q for kw in ["how to use", "setup", "set up", "configure",
                                   "tutorial", "walkthrough"]):
            intents.append("tool_help")

        if any(kw in q for kw in ["my chats", "past questions", "what i asked", "history",
                                   "my conversations", "saas", "dashboard"]):
            intents.append("saas_history")

        return intents

    def fetch_data(self, intents: List[str], question: str, user_id: str) -> str:
        """Fetch student-specific data based on intents."""
        parts = []
        for intent in intents:
            try:
                if intent == "my_progress":
                    parts.append(self._fetch_progress(user_id))
                elif intent == "next_steps":
                    parts.append(self._fetch_next_steps(user_id))
                elif intent == "sourcing_guide":
                    parts.append(self._fetch_sourcing_context(user_id))
                elif intent == "tool_help":
                    parts.append(self._fetch_tool_context(question))
                elif intent == "saas_history":
                    parts.append(self._fetch_saas_context(user_id))
            except Exception as e:
                parts.append(f"[Error: {e}]")
        return "\n\n".join(p for p in parts if p)

    def _get_student(self, discord_user_id: str) -> Optional[Dict]:
        """Look up student by Discord user ID."""
        if not STUDENTS_DB.exists():
            return None
        try:
            conn = sqlite3.connect(str(STUDENTS_DB), timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM students WHERE discord_user_id = ? AND status = 'active'",
                (str(discord_user_id),)
            ).fetchone()
            if row:
                result = dict(row)
                # Get milestones
                milestones = conn.execute(
                    "SELECT milestone, status, completed_at FROM milestones WHERE student_id = ? "
                    "ORDER BY completed_at DESC",
                    (result["id"],)
                ).fetchall()
                result["milestones"] = [dict(m) for m in milestones]

                # Get recent check-ins
                checkins = conn.execute(
                    "SELECT date, mood, actions, blockers FROM check_ins "
                    "WHERE student_id = ? ORDER BY date DESC LIMIT 3",
                    (result["id"],)
                ).fetchall()
                result["recent_checkins"] = [dict(c) for c in checkins]
                conn.close()
                return result
            conn.close()
        except Exception:
            pass
        return None

    def _fetch_progress(self, user_id: str) -> str:
        student = self._get_student(user_id)
        if not student:
            return ""

        lines = ["### Your Progress"]
        lines.append(f"- Tier: {student.get('tier', 'Unknown')}")
        lines.append(f"- Current milestone: {student.get('current_milestone', 'Not set')}")
        lines.append(f"- Health score: {student.get('health_score', 'N/A')}/100")
        lines.append(f"- Start date: {student.get('start_date', 'Unknown')}")

        completed = [m for m in student.get("milestones", []) if m.get("status") == "completed"]
        pending = [m for m in student.get("milestones", []) if m.get("status") != "completed"]
        if completed:
            lines.append(f"\n**Completed milestones ({len(completed)}):**")
            for m in completed[:10]:
                lines.append(f"- {m['milestone']}" + (f" ({m.get('completed_at', '')[:10]})" if m.get('completed_at') else ""))
        if pending:
            lines.append(f"\n**Upcoming milestones ({len(pending)}):**")
            for m in pending[:5]:
                lines.append(f"- {m['milestone']}")

        checkins = student.get("recent_checkins", [])
        if checkins:
            lines.append("\n**Recent check-ins:**")
            for c in checkins:
                mood = c.get("mood", "")
                actions = c.get("actions", "")
                blockers = c.get("blockers", "")
                lines.append(f"- {c.get('date', '')} | Mood: {mood}" +
                             (f" | Actions: {actions[:80]}" if actions else "") +
                             (f" | Blockers: {blockers[:80]}" if blockers else ""))

        # Enrich with SaaS data if available
        if _saas:
            saas_ctx = _saas.get_student_context(str(user_id))
            if saas_ctx:
                lines.append(f"\n{saas_ctx}")

        return "\n".join(lines)

    def _fetch_saas_context(self, user_id: str) -> str:
        if not _saas:
            return ""
        return _saas.get_student_context(user_id)

    def _fetch_next_steps(self, user_id: str) -> str:
        student = self._get_student(user_id)
        if not student:
            return "### Next Steps\nI don't have your student profile linked yet. Ask a team member to connect your Discord to your student account."

        tier = (student.get("tier") or "").lower()
        current = student.get("current_milestone", "")
        completed = [m["milestone"] for m in student.get("milestones", []) if m.get("status") == "completed"]

        lines = ["### Your Next Steps"]
        lines.append(f"Current milestone: **{current}**")

        # Tier-specific guidance
        if "a" in tier or "beginner" in tier:
            if not completed:
                lines.append("\n**You're just getting started! Focus on:**")
                lines.append("1. Watch the Masterclass modules in order")
                lines.append("2. Set up your Amazon Seller Account")
                lines.append("3. Get SellerAmp SAS + Keepa subscriptions")
                lines.append("4. Do your first product scan (follow the Scan Unlimited Workflow)")
            elif len(completed) < 3:
                lines.append("\n**Good progress! Next focus:**")
                lines.append("1. Complete your first purchase (start small, $50-100)")
                lines.append("2. Ship to prep center or do your own prep")
                lines.append("3. Create your first FBA shipment")
        elif "b" in tier:
            lines.append("\n**As an experienced seller, focus on:**")
            lines.append("1. Scaling what's working (don't diversify too early)")
            lines.append("2. Build relationships with 3-5 brands directly")
            lines.append("3. Optimize your repricer (BQool or similar)")

        return "\n".join(lines)

    def _fetch_sourcing_context(self, user_id: str) -> str:
        student = self._get_student(user_id)
        tier = ""
        if student:
            tier = (student.get("tier") or "").lower()

        lines = ["### Sourcing Quick Reference"]
        lines.append("**Sabbo's Leverage Ladder (go in order):**")
        lines.append("1. Retail Arbitrage (RA) — scan clearance in stores")
        lines.append("2. Online Arbitrage (OA) — scan deals online")
        lines.append("3. Wholesale — buy from distributors at bulk pricing")
        lines.append("4. Brand Direct — partner directly with brands")
        lines.append("5. Private Label — create your own products")

        if "a" in tier or "beginner" in tier or not tier:
            lines.append("\n**For beginners: Start with OA + RA**")
            lines.append("- Use SellerAmp SAS to scan products")
            lines.append("- The 1/2 Rule: if Amazon price >= 2x your cost, likely profitable")
            lines.append("- Check Keepa graph: want consistent sales rank + stable pricing")
            lines.append("- Aim for 30%+ ROI minimum, $3+ profit per unit")

        return "\n".join(lines)

    def _fetch_tool_context(self, question: str) -> str:
        q = question.lower()
        lines = ["### Tool Quick Reference"]

        if "selleramp" in q or "sas" in q:
            lines.append("**SellerAmp SAS** (~$18/mo)")
            lines.append("- Sabbo's #1 recommended product research tool")
            lines.append("- Scan products by ASIN, UPC, or name")
            lines.append("- Shows ROI, profit, FBA fees, sales rank, competition")
            lines.append("- Chrome extension for scanning on any website")
        elif "keepa" in q:
            lines.append("**Keepa** (~$20/mo)")
            lines.append("- The KING of Amazon software (Sabbo's words)")
            lines.append("- Price history, sales rank history, BSR trends")
            lines.append("- Product finder for wholesale/brand sourcing")
            lines.append("- 90-day average sales rank = best demand indicator")
        elif "bqool" in q or "repric" in q:
            lines.append("**BQool** (repricer)")
            lines.append("- Use after you have 20+ active listings")
            lines.append("- Automated Buy Box competition")
            lines.append("- Set min/max price rules to protect margins")
        else:
            lines.append("**Sabbo's Core Tool Stack:**")
            lines.append("- SellerAmp SAS (~$18/mo) — product research")
            lines.append("- Keepa (~$20/mo) — price/rank history")
            lines.append("- Rakuten (free) — cashback on purchases")
            lines.append("- Capital One Shopping (free) — auto coupons")
            lines.append("- BQool — repricer (after 20+ listings)")
            lines.append("- Prep center in tax-free state (NH, DE, MT, OR)")

        return "\n".join(lines)
