"""
Telegram Control Bot -- nomad-nebula
Lets Sabbo control the entire system from his phone.

Usage:
    /Users/Shared/antigravity/projects/nomad-nebula/.venv/bin/python \
        execution/telegram_control.py
"""

import itertools
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Union

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -- Config -------------------------------------------------------------------

PROJECT_ROOT = Path("/Users/Shared/antigravity/projects/nomad-nebula")
VENV_PYTHON  = str(PROJECT_ROOT / ".venv/bin/python")
LOG_FILE     = PROJECT_ROOT / ".tmp/telegram-control.log"
ENV_FILE     = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

if not BOT_TOKEN:
    sys.exit(
        "TELEGRAM_BOT_TOKEN is empty in .env -- "
        "add your BotFather token to "
        "/Users/Shared/antigravity/projects/nomad-nebula/.env, "
        "then reload the service: "
        "launchctl load ~/Library/LaunchAgents/com.sabbo.telegram-control.plist"
    )
if not ALLOWED_CHAT:
    sys.exit(
        "TELEGRAM_CHAT_ID is empty in .env -- "
        "send any message to @userinfobot on Telegram to get your chat ID, "
        "then add it to .env and reload the service."
    )

# -- Logging ------------------------------------------------------------------

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# -- Helpers ------------------------------------------------------------------

MAX_CHARS = 4000


def _log_command(chat_id: Union[int, str], command: str) -> None:
    log.info("CMD from %s: %s", chat_id, command)


def _truncate(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) > limit:
        # Use islice to avoid slice-syntax linter false positive on Python 3.9 stubs
        return "".join(itertools.islice(iter(text), limit)) + "\n...(truncated)"
    return text


def _run(cmd: List[str], timeout: int = 120) -> str:
    """Run a subprocess, return combined stdout+stderr, truncated to MAX_CHARS."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip()
        if not output:
            output = "(no output)"
    except subprocess.TimeoutExpired:
        output = "[TIMEOUT after {}s]".format(timeout)
    except Exception as exc:
        output = "[ERROR] {}".format(exc)

    return _truncate(output)


def _security_check(update: Update) -> bool:
    """Return True if the message comes from the allowed chat."""
    if update.effective_chat is None:
        return False
    chat_id = str(update.effective_chat.id)
    if chat_id != str(ALLOWED_CHAT):
        log.warning("Rejected message from unauthorized chat %s", chat_id)
        return False
    return True


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _starts_with_error(text: str) -> bool:
    """Check if the first 50 chars of text suggest an error."""
    prefix = "".join(itertools.islice(iter(text), 50))
    return "error" in prefix.lower()


# -- Command Handlers ---------------------------------------------------------

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/help")  # type: ignore[union-attr]
    text = (
        "nomad-nebula Control Bot\n\n"
        "/status   -- budget + active/queued/blocked tasks\n"
        "/run <skill> -- force-run a scheduled skill\n"
        "/skills   -- list all scheduled skills\n"
        "/health   -- agent health scan (Training Officer)\n"
        "/students -- at-risk student list\n"
        "/pipeline -- weekly pipeline analytics report\n"
        "/brain    -- last 10 lines of CEO brain\n"
        "/budget   -- today's token/API usage report\n"
        "/help     -- this message"
    )
    await update.message.reply_text(text)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/status")  # type: ignore[union-attr]
    await update.message.reply_text("Running /status... ({})".format(_ts()))

    budget_out = _run([VENV_PYTHON, "execution/token_tracker.py", "budget"])
    deadline_out = _run(
        ["python3", "/Users/Shared/antigravity/tools/deadlines.py", "quick"]
    )

    reply = "BUDGET\n{}\n\nTASKS\n{}".format(budget_out, deadline_out)
    await update.message.reply_text(_truncate(reply))


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /run <skill_name>")
        return
    skill = ctx.args[0]
    _log_command(update.effective_chat.id, "/run {}".format(skill))  # type: ignore[union-attr]
    await update.message.reply_text("Running skill '{}'... ({})".format(skill, _ts()))
    output = _run(
        [VENV_PYTHON, "execution/run_scheduled_skills.py", "force", "--skill", skill],
        timeout=300,
    )
    await update.message.reply_text(output)


async def cmd_skills(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/skills")  # type: ignore[union-attr]
    output = _run([VENV_PYTHON, "execution/run_scheduled_skills.py", "list"])
    await update.message.reply_text(output)


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/health")  # type: ignore[union-attr]
    await update.message.reply_text("Running agent health scan... ({})".format(_ts()))
    # Try --quick first; fall back to full scan if the flag is not recognised
    output = _run(
        [VENV_PYTHON, "execution/training_officer_scan.py", "--quick"],
        timeout=180,
    )
    if "unrecognized" in output.lower() or _starts_with_error(output):
        output = _run(
            [VENV_PYTHON, "execution/training_officer_scan.py"],
            timeout=300,
        )
    await update.message.reply_text(output)


async def cmd_students(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/students")  # type: ignore[union-attr]
    await update.message.reply_text("Fetching at-risk students... ({})".format(_ts()))
    output = _run(
        [VENV_PYTHON, "execution/student_health_monitor.py", "at-risk"],
        timeout=120,
    )
    await update.message.reply_text(output)


async def cmd_pipeline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/pipeline")  # type: ignore[union-attr]
    await update.message.reply_text(
        "Generating weekly pipeline report... ({})".format(_ts())
    )
    output = _run(
        [VENV_PYTHON, "execution/pipeline_analytics.py", "report", "--period", "weekly"],
        timeout=120,
    )
    await update.message.reply_text(output)


async def cmd_brain(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/brain")  # type: ignore[union-attr]
    brain_path = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
    try:
        lines = brain_path.read_text().splitlines()
        # Collect last 10 lines without slice syntax (linter workaround)
        last_ten: List[str] = []
        for line in lines:
            last_ten.append(line)
            if len(last_ten) > 10:
                last_ten.pop(0)
        snippet = "\n".join(last_ten)
        output = "CEO Brain (last 10 lines):\n\n{}".format(snippet)
    except Exception as exc:
        output = "[ERROR reading brain.md] {}".format(exc)
    await update.message.reply_text(output)


async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _security_check(update):
        return
    if update.message is None:
        return
    _log_command(update.effective_chat.id, "/budget")  # type: ignore[union-attr]
    await update.message.reply_text(
        "Fetching today's token usage... ({})".format(_ts())
    )
    output = _run(
        [VENV_PYTHON, "execution/token_tracker.py", "report", "--period", "day"]
    )
    await update.message.reply_text(output)


# -- Main ---------------------------------------------------------------------

def main() -> None:
    log.info("Telegram Control Bot starting -- allowed chat: %s", ALLOWED_CHAT)

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("start",    cmd_help))   # /start alias
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("run",      cmd_run))
    app.add_handler(CommandHandler("skills",   cmd_skills))
    app.add_handler(CommandHandler("health",   cmd_health))
    app.add_handler(CommandHandler("students", cmd_students))
    app.add_handler(CommandHandler("pipeline", cmd_pipeline))
    app.add_handler(CommandHandler("brain",    cmd_brain))
    app.add_handler(CommandHandler("budget",   cmd_budget))

    log.info("Polling started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
