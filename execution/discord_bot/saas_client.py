"""247profits SaaS Client — fetches student data from the SaaS Supabase."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import requests

TIMEOUT = 10


class ProfitsSaasClient:
    """Client for the 247profits.org SaaS Supabase."""

    def __init__(self):
        self.url = os.getenv("PROFITS_SUPABASE_URL", "")
        self.key = os.getenv("PROFITS_SUPABASE_KEY", "")

    def _get(self, table: str, params: dict) -> Optional[List]:
        if not self.url or not self.key:
            return None
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        query = {"select": "*"}
        query.update(params)
        try:
            r = requests.get(f"{self.url}/rest/v1/{table}", headers=headers,
                             params=query, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def get_user_by_discord(self, discord_user_id: str) -> Optional[Dict]:
        """Find a SaaS user by their Discord ID."""
        rows = self._get("users", {
            "discord_user_id": f"eq.{discord_user_id}",
            "select": "id,email,full_name,student_tier,plan,subscription_status",
            "limit": "1",
        })
        return rows[0] if rows else None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Find a SaaS user by email."""
        rows = self._get("users", {
            "email": f"ilike.{email}",
            "select": "id,email,full_name,student_tier,plan,subscription_status,discord_user_id",
            "limit": "1",
        })
        return rows[0] if rows else None

    def get_chat_history(self, user_id: str, limit: int = 5) -> List[Dict]:
        """Get student's past SaaS chat conversations with messages."""
        convos = self._get("academy_chat_conversations", {
            "user_id": f"eq.{user_id}",
            "select": "id,title,updated_at,current_module_id,current_lesson_id",
            "order": "updated_at.desc",
            "limit": str(limit),
        }) or []

        results = []
        for c in convos:
            msgs = self._get("academy_chat_messages", {
                "conversation_id": f"eq.{c['id']}",
                "select": "role,content,created_at",
                "order": "created_at.desc",
                "limit": "4",
            }) or []
            results.append({
                "title": c.get("title", ""),
                "updated_at": c.get("updated_at", ""),
                "messages": list(reversed(msgs)),  # chronological
            })
        return results

    def get_action_plan(self, user_id: str) -> Optional[Dict]:
        """Get student's current action plan."""
        rows = self._get("action_plans", {
            "user_id": f"eq.{user_id}",
            "status": "eq.published",
            "select": "edited_plan,generated_plan,status,created_at",
            "order": "created_at.desc",
            "limit": "1",
        })
        return rows[0] if rows else None

    def get_modules(self) -> List[Dict]:
        """Get all academy modules in order."""
        return self._get("academy_modules", {
            "select": "id,title,sort_order,week_start,week_end",
            "order": "sort_order.asc",
        }) or []

    def get_module_lessons(self, module_id: str) -> List[Dict]:
        """Get lessons for a specific module."""
        return self._get("academy_lessons", {
            "module_id": f"eq.{module_id}",
            "select": "id,title,slug,description,video_duration_seconds",
            "order": "sort_order.asc",
        }) or []

    def get_student_context(self, discord_user_id: str) -> str:
        """Build a complete context block for a student. Called by the query router."""
        user = self.get_user_by_discord(discord_user_id)
        if not user:
            # Fallback: look up email from local students.db, then find in SaaS
            try:
                import sqlite3
                from pathlib import Path
                db = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"
                if db.exists():
                    conn = sqlite3.connect(str(db), timeout=5)
                    row = conn.execute(
                        "SELECT email FROM students WHERE discord_user_id = ? AND email IS NOT NULL",
                        (str(discord_user_id),)
                    ).fetchone()
                    conn.close()
                    if row and row[0]:
                        user = self.get_user_by_email(row[0])
            except Exception:
                pass
        if not user:
            return ""

        uid = user["id"]
        parts = ["### 247profits SaaS Profile"]
        parts.append(f"- Name: {user.get('full_name', 'Unknown')}")
        parts.append(f"- Plan: {user.get('plan', 'Unknown')}")
        parts.append(f"- Tier: {user.get('student_tier', 'Not set')}")
        parts.append(f"- Status: {user.get('subscription_status', 'Unknown')}")

        # Action plan
        plan = self.get_action_plan(uid)
        if plan:
            plan_data = plan.get("edited_plan") or plan.get("generated_plan")
            if isinstance(plan_data, list):
                parts.append("\n**Action Plan:**")
                for step in plan_data[:8]:
                    if isinstance(step, dict):
                        parts.append(f"- Week {step.get('week', '?')}: {step.get('title', '')} — {step.get('description', '')[:100]}")
                    else:
                        parts.append(f"- {str(step)[:120]}")

        # Past SaaS chats (what they've asked about before)
        chats = self.get_chat_history(uid, limit=5)
        if chats:
            parts.append(f"\n**Recent SaaS Chat Topics ({len(chats)} conversations):**")
            for c in chats:
                title = c.get("title", "Untitled")[:80]
                date = (c.get("updated_at") or "")[:10]
                # Get the student's last question
                user_msgs = [m for m in c.get("messages", []) if m.get("role") == "user"]
                last_q = user_msgs[-1]["content"][:120] if user_msgs else ""
                parts.append(f"- {date}: \"{title}\"" + (f" — Last asked: \"{last_q}\"" if last_q and last_q != title else ""))

        return "\n".join(parts)
