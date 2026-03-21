"""Profile Cog — student self-linking + profile viewing."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

STUDENTS_DB = Path(__file__).parent.parent.parent / ".tmp" / "coaching" / "students.db"

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _get_conn():
    if not STUDENTS_DB.exists():
        return None
    return sqlite3.connect(str(STUDENTS_DB), timeout=5)


def _valid_email(email: str) -> str | None:
    """Validate and normalize email. Returns normalized or None."""
    email = (email or "").strip()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return None
    return email


class ProfileCog(commands.Cog):
    """Student self-linking and profile viewing."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="link", description="Link your Discord to your 24/7 Profits student account")
    @app_commands.describe(email="The email you signed up with")
    async def link(self, interaction: discord.Interaction, email: str):
        await interaction.response.defer(ephemeral=True)

        # Validate email format
        clean_email = _valid_email(email)
        if not clean_email:
            await interaction.followup.send(
                "That doesn't look like a valid email address. Please check and try again.",
                ephemeral=True)
            return

        conn = _get_conn()
        if not conn:
            await interaction.followup.send("Student database not available. Please contact the team.", ephemeral=True)
            return

        try:
            conn.row_factory = sqlite3.Row
            # Find student by email (case-insensitive)
            student = conn.execute(
                "SELECT id, name, discord_user_id, status FROM students WHERE LOWER(email) = LOWER(?) AND status = 'active'",
                (clean_email,)
            ).fetchone()

            if not student:
                await interaction.followup.send(
                    "No active student account found with that email. "
                    "Make sure you're using the same email you signed up with. "
                    "If you need help, open a /ticket.", ephemeral=True)
                conn.close()
                return

            # Check if already linked to someone else
            if student["discord_user_id"] and student["discord_user_id"] != str(interaction.user.id):
                await interaction.followup.send(
                    "This account is already linked to a different Discord user. "
                    "If this is an error, please open a /ticket.", ephemeral=True)
                conn.close()
                return

            # Atomic link — prevents race condition
            cursor = conn.execute(
                "UPDATE students SET discord_user_id = ? WHERE id = ? "
                "AND (discord_user_id IS NULL OR discord_user_id = '' OR discord_user_id = ?)",
                (str(interaction.user.id), student["id"], str(interaction.user.id))
            )
            conn.commit()

            if cursor.rowcount == 0:
                await interaction.followup.send(
                    "This account was just linked by another user. "
                    "If this is an error, please open a /ticket.", ephemeral=True)
                conn.close()
                return

            # Audit log
            try:
                from .database import BotDatabase
                db = BotDatabase()
                db.log_audit(str(interaction.user.id), "account_linked",
                             f"student_id={student['id']} email={clean_email[:3]}***")
            except Exception:
                pass

            conn.close()

            await interaction.followup.send(
                f"Linked! Welcome, **{student['name']}**. "
                f"Use `/profile` to see your progress, and `/ask` for personalized coaching.",
                ephemeral=True)

        except Exception:
            conn.close()
            await interaction.followup.send("Something went wrong. Please try again or open a /ticket.", ephemeral=True)

    @app_commands.command(name="profile", description="View your student profile and progress")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = _get_conn()
        if not conn:
            await interaction.followup.send("Student database not available.", ephemeral=True)
            return

        try:
            conn.row_factory = sqlite3.Row
            student = conn.execute(
                "SELECT * FROM students WHERE discord_user_id = ? AND status = 'active'",
                (str(interaction.user.id),)
            ).fetchone()

            if not student:
                await interaction.followup.send(
                    "Your Discord isn't linked to a student account yet. "
                    "Use `/link` with your signup email to connect.", ephemeral=True)
                conn.close()
                return

            # Get milestones
            milestones = conn.execute(
                "SELECT milestone, status, completed_at FROM milestones WHERE student_id = ? ORDER BY completed_at DESC",
                (student["id"],)
            ).fetchall()

            completed = [m for m in milestones if m["status"] == "completed"]
            pending = [m for m in milestones if m["status"] != "completed"]

            lines = [f"**Your 24/7 Profits Profile**\n"]
            lines.append(f"**Name:** {student['name']}")
            lines.append(f"**Tier:** {student['tier'] or 'Not set'}")
            lines.append(f"**Current Milestone:** {student['current_milestone'] or 'Not set'}")
            lines.append(f"**Health Score:** {student['health_score'] or 'N/A'}/100")
            lines.append(f"**Start Date:** {student['start_date'] or 'Unknown'}")

            if completed:
                lines.append(f"\n**Completed ({len(completed)}):**")
                for m in completed[:8]:
                    date = f" ({m['completed_at'][:10]})" if m.get('completed_at') else ""
                    lines.append(f"✅ {m['milestone']}{date}")

            if pending:
                lines.append(f"\n**Upcoming ({len(pending)}):**")
                for m in pending[:5]:
                    lines.append(f"⬜ {m['milestone']}")

            conn.close()
            await interaction.followup.send("\n".join(lines), ephemeral=True)

        except Exception:
            conn.close()
            await interaction.followup.send("Something went wrong. Please try again.", ephemeral=True)

    # ── GDPR / Privacy ─────────────────────────────────────────────────────

    @app_commands.command(name="my-data", description="See what data Nova stores about you")
    async def my_data(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        lines = ["**Your Data in Nova**\n"]

        # Chat history count
        try:
            from .database import BotDatabase
            db = BotDatabase()
            chat_count = db.conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            lines.append(f"- Chat messages stored: {chat_count}")
        except Exception:
            pass

        # Student profile
        conn = _get_conn()
        if conn:
            try:
                conn.row_factory = sqlite3.Row
                student = conn.execute(
                    "SELECT name, tier, current_milestone, health_score, start_date, email "
                    "FROM students WHERE discord_user_id = ?", (user_id,)
                ).fetchone()
                if student:
                    lines.append(f"\n**Student Profile:**")
                    lines.append(f"- Name: {student['name']}")
                    email = student['email'] or ''
                    if email and '@' in email:
                        lines.append(f"- Email: {email[:3]}***@{email.split('@')[1]}")
                    elif email:
                        lines.append(f"- Email: {email[:3]}***")
                    else:
                        lines.append("- Email: not set")
                    lines.append(f"- Tier: {student['tier'] or 'Not set'}")
                    lines.append(f"- Start date: {student['start_date'] or 'Unknown'}")
                else:
                    lines.append("\n**Student Profile:** Not linked (use /link)")
                conn.close()
            except Exception:
                conn.close()

        # Learning interactions
        try:
            from .learning_engine import StudentLearningEngine
            le = StudentLearningEngine()
            count = le.conn.execute(
                "SELECT COUNT(*) FROM interactions WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            lines.append(f"\n- Learning interactions logged: {count}")
        except Exception:
            pass

        lines.append(f"\nTo request data deletion, use `/delete-my-data`.")

        # Audit: log that user viewed their data
        try:
            from .database import BotDatabase
            BotDatabase().log_audit(user_id, "my_data_viewed", "User viewed their stored data")
        except Exception:
            pass

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="delete-my-data", description="Delete your data from Nova")
    async def delete_my_data(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        deleted_items = []

        # 1. Delete from discord_bot.db (chat history)
        try:
            from .database import BotDatabase
            bot_db = BotDatabase()
            bot_db.log_audit(user_id, "data_deletion_executed",
                             f"User {interaction.user.display_name} data deletion")
            count = bot_db.conn.execute(
                "DELETE FROM chat_history WHERE user_id = ?", (user_id,)
            ).rowcount
            bot_db.conn.commit()
            if count:
                deleted_items.append(f"Chat messages: {count}")
        except Exception:
            pass

        # 2. Delete from nova.db (shared: chat_log, abuse_log, feedback)
        try:
            from nova_core.database import get_conn
            nova_conn = get_conn()
            for table in ("chat_log", "abuse_log", "feedback"):
                try:
                    count = nova_conn.execute(
                        f"DELETE FROM {table} WHERE user_id = ?", (user_id,)
                    ).rowcount
                    if count:
                        deleted_items.append(f"{table}: {count}")
                except Exception:
                    pass
            nova_conn.commit()
        except Exception:
            pass

        # 3. Delete from learning engine
        try:
            from .learning_engine import StudentLearningEngine
            le = StudentLearningEngine()
            count = le.conn.execute(
                "DELETE FROM interactions WHERE user_id = ?", (user_id,)
            ).rowcount
            le.conn.commit()
            if count:
                deleted_items.append(f"Learning interactions: {count}")
        except Exception:
            pass

        # 4. Unlink Discord from student record (don't delete student — business data)
        conn = _get_conn()
        if conn:
            try:
                conn.execute(
                    "UPDATE students SET discord_user_id = NULL WHERE discord_user_id = ?",
                    (user_id,)
                )
                conn.commit()
                deleted_items.append("Account unlinked")
            except Exception:
                pass
            finally:
                conn.close()

        summary = "\n".join(f"- {item}" for item in deleted_items) if deleted_items else "No data found."
        await interaction.followup.send(
            f"**Data deletion complete.**\n\n{summary}\n\n"
            "Your audit log entry is kept for security compliance. "
            "If you need further assistance, open a `/ticket`.",
            ephemeral=True
        )

    # ── Admin Linking ────────────────────────────────────────────────────

    @app_commands.command(name="student-link", description="[Admin] Link a student's Discord to their account")
    @app_commands.describe(member="Discord user to link", email="Student's signup email")
    async def admin_link(self, interaction: discord.Interaction, member: discord.Member, email: str):
        # Check admin role
        admin_role_id = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))
        if not any(r.id == admin_role_id for r in interaction.user.roles):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        # Validate email
        clean_email = _valid_email(email)
        if not clean_email:
            await interaction.response.send_message("Invalid email format.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        conn = _get_conn()
        if not conn:
            await interaction.followup.send("Student database not available.", ephemeral=True)
            return

        try:
            conn.row_factory = sqlite3.Row
            student = conn.execute(
                "SELECT id, name FROM students WHERE LOWER(email) = LOWER(?)",
                (clean_email,)
            ).fetchone()

            if not student:
                await interaction.followup.send(f"No student found with email: {email}", ephemeral=True)
                conn.close()
                return

            conn.execute(
                "UPDATE students SET discord_user_id = ? WHERE id = ?",
                (str(member.id), student["id"])
            )
            conn.commit()
            conn.close()

            # Audit log
            try:
                from .database import BotDatabase
                BotDatabase().log_audit(str(interaction.user.id), "admin_link",
                                        f"admin={interaction.user.display_name} linked {member.display_name} → student_id={student['id']}")
            except Exception:
                pass

            await interaction.followup.send(
                f"Linked **{member.display_name}** to **{student['name']}** ({email})",
                ephemeral=True)

        except Exception:
            conn.close()
            await interaction.followup.send("Something went wrong.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
