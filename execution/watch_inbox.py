#!/usr/bin/env python3
"""
Script: watch_inbox.py
Purpose: Watch /Users/Shared/antigravity/inbox/ for task files from OpenClaw and process them
Inputs:  None (runs as daemon, polls inbox every 5 seconds)
Outputs: Result JSON files written to /Users/Shared/antigravity/outbox/
"""

import fcntl
import json
import itertools
import os
import sys
import time
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

INBOX = Path("/Users/Shared/antigravity/inbox")
OUTBOX = Path("/Users/Shared/antigravity/outbox")
MEMORY = Path("/Users/Shared/antigravity/memory")
PROPOSALS = Path("/Users/Shared/antigravity/proposals")
SYNC_DIR = Path("/Users/Shared/antigravity/memory/sync")
NOTIFICATIONS_FILE = SYNC_DIR / "notifications.json"
POLL_INTERVAL = 5  # seconds
PROCESSED_SUFFIX = ".done"

# Telegram notifications
SABBO_CHAT_ID = "2135766059"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
_TELEGRAM_BOT_TOKEN = None  # loaded at startup

# All supported task types for validation + auto-routing
KNOWN_TASK_TYPES = {
    "build_skill", "run_scraper", "filter_icp", "generate_emails",
    "generate_ad_scripts", "generate_vsl", "reindex", "heartbeat",
    "propose_edit", "source_products", "training_scan", "training_approve",
    "training_benchmark", "run_ide_task", "ping", "sync_trigger",
    "sync_memory",  # MED-7: was missing, caused spurious Unknown Task Type alerts
    "search_knowledge",  # OC delegates memory/codebase searches to CC
}

# Task types that are too noisy to send Telegram alerts for
QUIET_TASK_TYPES = {"heartbeat", "ping", "reindex", "sync_memory", "search_knowledge"}

# Deduplication: track recently processed task IDs to prevent double-processing
_processed_ids = set()  # in-memory set, cleared on restart (fine — .done suffix prevents re-reads anyway)
MAX_PROCESSED_IDS = 500  # cap memory usage
ERROR_SUFFIX = ".error"  # rename broken files here instead of crash-looping

# Dynamic project root — resolves to nomad-nebula/ regardless of which Mac user is running
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
BOTS_DIR = PROJECT_ROOT / "bots"
DIRECTIVES_DIR = PROJECT_ROOT / "directives"
SABBO_OS_DIR = PROJECT_ROOT / "SabboOS"
CLAUDE_AGENTS_DIR = Path.home() / ".claude" / "agents"

# Security: allowed directories for file path inputs
ALLOWED_PATH_ROOTS = [
    Path("/Users/Shared/antigravity"),
    Path("/Users/sabbojb/Documents/nomad-nebula"),
    Path("/Users/sabbojb/Documents/saas-dashboard"),
    Path("/Users/sabbojb/Documents/automation-engine"),
    Path("/Users/sabbojb/Documents/ultraviolet-curiosity"),
    Path("/Users/sabbojb/Documents/fba-saas"),
]
ALLOWED_URL_SCHEMES = {"https"}
MAX_TASKS_PER_CYCLE = 10
MAX_SYNC_FILES = 50


def _validate_path(filepath: str, label: str) -> Path:
    """Validate a file path stays within allowed directories. Raises ValueError if unsafe."""
    p = Path(filepath).resolve()
    for root in ALLOWED_PATH_ROOTS:
        try:
            if p.is_relative_to(root.resolve()):
                return p
        except (ValueError, OSError):
            continue
    raise ValueError(f"Path traversal blocked on '{label}': {filepath}")


def _validate_bot_name(bot: str) -> str:
    """Validate bot name contains only safe characters."""
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', bot):
        raise ValueError(f"Invalid bot name: {bot}")
    return bot


def _validate_url(url: str) -> str:
    """Validate URL is https and not internal/file."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme not allowed, must be https")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    hostname = parsed.hostname.lower()
    blocked = ("localhost", "127.0.0.1", "0.0.0.0", "169.254.", "10.", "192.168.", "172.16.")
    for b in blocked:
        if hostname.startswith(b):
            raise ValueError("Internal/private URL blocked")
    return url


def _sanitize_for_telegram(msg: str) -> str:
    """Strip sensitive paths from messages before sending to Telegram."""
    msg = msg.replace("/Users/sabbojb", "~")
    msg = msg.replace("/Users/Shared/antigravity", "~/bridge")
    return msg[:300]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _load_telegram_token():
    """Load Telegram bot token from OpenClaw config at startup."""
    global _TELEGRAM_BOT_TOKEN
    if _TELEGRAM_BOT_TOKEN:
        return _TELEGRAM_BOT_TOKEN
    try:
        with open(OPENCLAW_CONFIG) as f:
            config = json.load(f)
        _TELEGRAM_BOT_TOKEN = config.get("channels", {}).get("telegram", {}).get("botToken", "")
    except Exception as e:
        log(f"Could not load Telegram token: {e}")
        _TELEGRAM_BOT_TOKEN = ""
    return _TELEGRAM_BOT_TOKEN


def send_telegram_alert(message: str):
    """Push a notification to Sabbo via Telegram. Silent failure — never crashes the daemon."""
    message = _sanitize_for_telegram(message)
    token = _load_telegram_token()
    if not token:
        log("Telegram alert skipped: no bot token")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": SABBO_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log(f"Telegram alert sent: {message[:60]}...")
    except Exception as e:
        log(f"Telegram alert failed: {e}")


def infer_task_type(task: dict) -> str:
    """Infer the correct task type from task fields when 'task' field is wrong or missing."""
    # Check 'type' field first (OpenClaw often puts the real type here)
    if task.get("type") in KNOWN_TASK_TYPES:
        return task["type"]
    # Field-based inference
    if "prompt" in task and "project" in task:
        return "run_ide_task"
    if "prompt" in task and not task.get("project"):
        return "run_ide_task"  # prompt alone implies IDE task
    if "bot" in task and "status" in task:
        return "heartbeat"
    if "query" in task and "location" in task:
        return "run_scraper"
    if "input_csv" in task and "platform" in task:
        return "generate_ad_scripts"
    if "input_csv" in task and "single" in task:
        return "generate_vsl"
    if "input_csv" in task and "threshold" in task:
        return "filter_icp"
    if "input_csv" in task:
        return "generate_emails"
    if "target_file" in task and "proposed_change" in task:
        return "propose_edit"
    if "url" in task and "min_roi" in task:
        return "source_products"
    if "proposal_id" in task:
        return "training_approve"
    return ""


def process_task(task_file: Path):
    """Read a task JSON, run the appropriate action, write result to outbox."""
    log(f"Processing: {task_file.name}")

    # Dedup: skip if we already processed this task ID
    task_id = task_file.stem
    if task_id in _processed_ids:
        log(f"Skipping duplicate task: {task_id}")
        task_file.rename(task_file.with_suffix(PROCESSED_SUFFIX))
        return
    _processed_ids.add(task_id)
    # Cap memory usage
    if len(_processed_ids) > MAX_PROCESSED_IDS:
        _processed_ids.clear()

    try:
        with open(task_file) as f:
            task = json.load(f)
    except Exception as e:
        log(f"ERROR reading task file: {e}")
        send_telegram_alert(f"*Bridge Error*: Could not read task file `{task_file.name}`\n`{e}`")
        # Rename to .error so it doesn't crash-loop
        try:
            task_file.rename(task_file.with_suffix(ERROR_SUFFIX))
            log(f"Moved broken file to {task_file.stem}{ERROR_SUFFIX}")
        except Exception:
            pass
        return

    # Route on "task" field first, fall back to "type" field
    raw_task_type = task.get("task", task.get("type", "unknown"))
    task_type = raw_task_type
    auto_fixed = False

    # If task_type is not recognized, try to infer it
    if task_type not in KNOWN_TASK_TYPES:
        inferred = infer_task_type(task)
        if inferred:
            log(f"Auto-fix: '{task_type}' -> '{inferred}'")
            task_type = inferred
            auto_fixed = True

    description = task.get("description", "")
    context = task.get("context", "")
    agent = task.get("agent", "unknown")

    result = {
        "task_id": task_file.stem,
        "task": task_type,
        "agent": agent,
        "received_at": datetime.now().isoformat(),
        "status": "error",
        "output": None,
        "error": None,
    }

    try:
        if task_type == "build_skill":
            output = handle_build_skill(description, context)
        elif task_type == "run_scraper":
            output = handle_run_scraper(task)
        elif task_type == "filter_icp":
            output = handle_filter_icp(task)
        elif task_type == "generate_emails":
            output = handle_generate_emails(task)
        elif task_type == "generate_ad_scripts":
            output = handle_generate_ad_scripts(task)
        elif task_type == "generate_vsl":
            output = handle_generate_vsl(task)
        elif task_type == "reindex":
            output = handle_reindex(task)
        elif task_type == "heartbeat":
            output = handle_heartbeat(task)
        elif task_type == "propose_edit":
            output = handle_propose_edit(task)
        elif task_type == "source_products":
            output = handle_source_products(task)
        elif task_type == "training_scan":
            output = handle_training_scan(task)
        elif task_type == "training_approve":
            output = handle_training_approve(task)
        elif task_type == "training_benchmark":
            output = handle_training_benchmark(task)
        elif task_type == "run_ide_task":
            output = handle_run_ide_task(task)
        elif task_type == "sync_trigger":
            output = handle_sync_trigger(task)
        elif task_type == "sync_memory":
            output = handle_sync_memory(task)
        elif task_type == "search_knowledge":
            output = handle_search_knowledge(task)
        elif task_type == "ping":
            output = {"message": "pong", "timestamp": datetime.now().isoformat()}
        else:
            output = {"message": f"Unknown task type: {task_type}. No handler."}
            send_telegram_alert(
                f"*Unknown Task Type*\n"
                f"Task: `{raw_task_type}`\n"
                f"File: `{task_file.name}`\n"
                f"Could not auto-route. Check task format."
            )

        result["status"] = "success"
        result["output"] = output
        log(f"✓ Task complete: {task_type}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log(f"✗ Task failed: {e}")
        # Alert on errors
        send_telegram_alert(
            f"*Task Failed*\n"
            f"Type: `{task_type}`\n"
            f"Error: `{str(e)[:200]}`"
        )

    # Write result to outbox
    out_file = OUTBOX / f"{task_file.stem}-result.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2)
    os.chmod(out_file, 0o660)
    log(f"Result written: {out_file.name}")

    # Write notification for OpenClaw to read during heartbeat
    summary = ""
    if result["status"] == "success" and result["output"]:
        summary = str(result["output"])[:200] if isinstance(result["output"], dict) else str(result["output"])[:200]
    elif result["error"]:
        summary = f"ERROR: {result['error']}"
    _write_notification(task_file.stem, task_type, result["status"], summary)

    # Send Telegram alerts for important events (skip noisy ones)
    if task_type not in QUIET_TASK_TYPES:
        if auto_fixed:
            send_telegram_alert(
                f"*Auto-Fixed Task Format*\n"
                f"`{raw_task_type}` -> `{task_type}`\n"
                f"Result: {result['status']}"
            )
        elif result["status"] == "success" and task_type == "run_ide_task":
            prompt_preview = task.get("prompt", "")[:100]
            send_telegram_alert(
                f"*IDE Task Complete*\n"
                f"Project: `{task.get('project', 'unknown')}`\n"
                f"Prompt: {prompt_preview}\n"
                f"Status: success"
            )
        elif result["status"] == "success" and task_type == "build_skill":
            send_telegram_alert(
                f"*New Skill Built*\n"
                f"Skill: `{description[:80]}`\n"
                f"Status: success"
            )

    # Mark as processed
    task_file.rename(task_file.with_suffix(PROCESSED_SUFFIX))


def handle_build_skill(description: str, context: str) -> dict:
    """Write a new skill file to the Claude agents directory for the current user."""
    import re
    raw_name = description.lower().replace(" ", "-")
    skill_name = re.sub(r'[^a-z0-9\-]', '', raw_name)[:40]
    CLAUDE_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    skill_file = CLAUDE_AGENTS_DIR / f"{skill_name}.md"

    content = f"""---
name: {skill_name}
description: {description}
tools: Read, Write, Edit, Bash, Glob
---

# {description}

{context if context else "No additional context provided."}
"""
    with open(skill_file, "w") as f:
        f.write(content)
    os.chmod(skill_file, 0o644)

    return {"skill_file": str(skill_file), "skill_name": skill_name}


def handle_run_scraper(task: dict) -> dict:
    """Run the nomad-nebula scraper and return output path."""
    query = task.get("query", "")
    location = task.get("location", "")
    max_results = min(int(task.get("max_results", 20)), 200)

    if not query or not location:
        raise ValueError("run_scraper requires 'query' and 'location' fields")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = OUTBOX / f"leads_{ts}.csv"

    script = PROJECT_ROOT / "execution" / "run_scraper.py"
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

    cmd = [python, str(script), "--query", query, "--location", location,
           "--max", str(max_results), "--output", str(out_file)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        raise RuntimeError(f"[CQ-004] Scraper subprocess failed: {e}")

    if result.returncode != 0:
        raise RuntimeError(f"Scraper failed: {result.stderr}")

    os.chmod(out_file, 0o660)
    return {"output_csv": str(out_file), "stdout": result.stdout.strip()}


def _run_script(script_name: str, args: list, timeout: int = 300) -> dict:
    """Helper to run an execution script in the venv and return stdout."""
    script = PROJECT_ROOT / "execution" / script_name
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    cmd = [python, str(script)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        raise RuntimeError(f"[CQ-004] {script_name} subprocess failed: {e}")
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed: {result.stderr}")
    return {"stdout": result.stdout.strip()}


def handle_filter_icp(task: dict) -> dict:
    """Filter a leads CSV by ICP using Claude."""
    input_csv = task.get("input_csv", "")
    threshold = str(task.get("threshold", 6))
    if not input_csv:
        raise ValueError("filter_icp requires 'input_csv' field")
    _validate_path(input_csv, "input_csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = str(OUTBOX / f"filtered_leads_{ts}.csv")
    result = _run_script("filter_icp.py", ["--input", input_csv, "--output", output_csv, "--threshold", threshold])
    result["output_csv"] = output_csv
    return result


def handle_generate_emails(task: dict) -> dict:
    """Generate personalized outreach emails for a filtered leads CSV."""
    input_csv = task.get("input_csv", "")
    if not input_csv:
        raise ValueError("generate_emails requires 'input_csv' field")
    _validate_path(input_csv, "input_csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = str(OUTBOX / f"emails_{ts}.csv")
    result = _run_script("generate_emails.py", ["--input", input_csv, "--output", output_csv], timeout=600)
    result["output_csv"] = output_csv
    return result


def handle_generate_ad_scripts(task: dict) -> dict:
    """Generate Meta/YouTube ad scripts for a filtered leads CSV."""
    input_csv = task.get("input_csv", "")
    platform = task.get("platform", "meta")
    if not input_csv:
        raise ValueError("generate_ad_scripts requires 'input_csv' field")
    _validate_path(input_csv, "input_csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = str(OUTBOX / f"ad_scripts_{ts}.csv")
    result = _run_script("generate_ad_scripts.py",
                         ["--input", input_csv, "--output", output_csv, "--platform", platform], timeout=600)
    result["output_csv"] = output_csv
    return result


def handle_generate_vsl(task: dict) -> dict:
    """Generate VSL scripts for a filtered leads CSV."""
    input_csv = task.get("input_csv", "")
    single = task.get("single", None)
    if not input_csv:
        raise ValueError("generate_vsl requires 'input_csv' field")
    _validate_path(input_csv, "input_csv")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = str(OUTBOX / f"vsl_{ts}.csv")
    args = ["--input", input_csv, "--output", output_csv]
    if single:
        args += ["--single", single]
    result = _run_script("generate_vsl.py", args, timeout=600)
    result["output_csv"] = output_csv
    return result


def handle_reindex(task: dict) -> dict:
    """Scan directives and SabboOS for recently changed files and return a summary."""
    hours = task.get("hours", 48)  # default: files changed in last 48 hours
    cutoff = datetime.now().timestamp() - (hours * 3600)

    changed = []
    scan_dirs = [DIRECTIVES_DIR, SABBO_OS_DIR, BOTS_DIR]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*.md"):
            if f.stat().st_mtime > cutoff:
                changed.append({
                    "file": str(f.relative_to(PROJECT_ROOT)),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "size_lines": sum(1 for _ in open(f, errors="ignore")),
                })

    changed.sort(key=lambda x: x["modified"], reverse=True)

    summary_file = OUTBOX / f"reindex_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump({"scanned_hours": hours, "changed_files": changed, "count": len(changed)}, f, indent=2)
    os.chmod(summary_file, 0o660)

    # Regenerate OpenClaw workspace files so OC always reflects the live codebase
    try:
        regen = PROJECT_ROOT / "execution" / "regenerate_oc_workspace.py"
        result = subprocess.run(
            [str(VENV_PYTHON), str(regen)],
            timeout=30,
            capture_output=True,
        )
        if result.returncode != 0:  # MED-3: log failures instead of swallowing them
            log(f"WARN: regenerate_oc_workspace failed (rc={result.returncode}): {result.stderr[:200]}")
    except Exception as e:
        log(f"WARN: regenerate_oc_workspace exception: {e}")  # Non-fatal — reindex still succeeds

    return {
        "changed_count": len(changed),
        "summary_file": str(summary_file),
        "files": [c["file"] for c in changed],
    }


def handle_heartbeat(task: dict) -> dict:
    """Update a bot's heartbeat.md with current timestamp and status."""
    bot = task.get("bot", "")
    status = task.get("status", "IDLE")
    current_task = task.get("current_task", "none")
    queue_items = task.get("queue", [])

    if not bot:
        raise ValueError("heartbeat requires 'bot' field (e.g. 'ads-copy')")
    _validate_bot_name(bot)

    heartbeat_file = BOTS_DIR / bot / "heartbeat.md"
    if not heartbeat_file.exists():
        raise FileNotFoundError(f"No heartbeat file for bot '{bot}' at {heartbeat_file}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = heartbeat_file.read_text()

    # Update the status block
    import re
    content = re.sub(r"Last heartbeat:.*", f"Last heartbeat: {now}", content)
    content = re.sub(r"Status:.*", f"Status: {status}", content)
    content = re.sub(r"Current task:.*", f"Current task: {current_task}", content)

    heartbeat_file.write_text(content)
    os.chmod(heartbeat_file, 0o644)

    return {"bot": bot, "updated_at": now, "status": status}


def handle_source_products(task: dict) -> dict:
    """Run the FBA sourcing pipeline on a retail URL."""
    url = task.get("url", "")
    min_roi = str(task.get("min_roi", 30))
    min_profit = str(task.get("min_profit", 3.0))
    max_price = str(task.get("max_price", 50.0))
    max_products = str(min(int(task.get("max_products", 50)), 200))

    if not url:
        raise ValueError("source_products requires 'url' field")
    _validate_url(url)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = str(OUTBOX / f"sourcing_{ts}.json")

    result = _run_script("run_sourcing_pipeline.py", [
        "--url", url,
        "--min-roi", min_roi,
        "--min-profit", min_profit,
        "--max-price", max_price,
        "--max-products", max_products,
        "--output", out_file,
    ], timeout=600)

    result["output_json"] = out_file
    return result


def handle_propose_edit(task: dict) -> dict:
    """
    Queue a file edit proposal from OpenClaw for Sabbo's review.
    OpenClaw proposes — Claude Code applies after approval.
    Proposals are written to /Users/Shared/antigravity/proposals/.
    """
    # MIN-3: accept both canonical names and the OC template field names
    target_file = task.get("target_file") or task.get("file", "")
    proposed_change = task.get("proposed_change") or task.get("proposed_content", "")
    reason = task.get("reason") or task.get("change_description", "No reason given")

    if not target_file or not proposed_change:
        raise ValueError("propose_edit requires 'target_file'/'file' and 'proposed_change'/'proposed_content' fields")
    _validate_path(target_file, "target_file")

    PROPOSALS.mkdir(parents=True, exist_ok=True)
    os.chmod(PROPOSALS, 0o770)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    proposal_file = PROPOSALS / f"{ts}-proposal.md"

    content = f"""# Edit Proposal — {ts}

**Target file:** `{target_file}`
**Proposed by:** OpenClaw / {task.get("agent", "unknown")}
**Reason:** {reason}
**Status:** PENDING APPROVAL

## Proposed Change

{proposed_change}

---
*Apply this change in Claude Code after reviewing. Delete this file when done.*
"""
    with open(proposal_file, "w") as f:
        f.write(content)
    os.chmod(proposal_file, 0o660)

    return {
        "proposal_file": str(proposal_file),
        "target_file": target_file,
        "status": "queued_for_approval",
    }


def handle_run_ide_task(task: dict) -> dict:
    """Let OpenClaw trigger Claude Code CLI to work on a project."""
    import shutil

    # MED-6: accept both 'prompt' (canonical) and 'instruction' (legacy OC template name)
    prompt = task.get("prompt") or task.get("instruction", "")
    project = task.get("project", "nomad-nebula")

    if not prompt:
        raise ValueError("run_ide_task requires 'prompt' or 'instruction' field")

    # Map project names to paths
    project_paths = {
        "nomad-nebula": "/Users/Shared/antigravity/projects/nomad-nebula",
        "saas-dashboard": "/Users/sabbojb/Documents/saas-dashboard",
        "automation-engine": "/Users/sabbojb/Documents/automation-engine",
        "ultraviolet-curiosity": "/Users/sabbojb/Documents/ultraviolet-curiosity",
        "fba-saas": "/Users/sabbojb/Documents/fba-saas",
    }
    project_dir = project_paths.get(project, project_paths["nomad-nebula"])

    # Find claude CLI
    claude_path = shutil.which("claude")
    if not claude_path:
        # Common locations
        for candidate in ["/usr/local/bin/claude", "/opt/homebrew/bin/claude",
                          str(Path.home() / ".claude" / "bin" / "claude")]:
            if Path(candidate).exists():
                claude_path = candidate
                break
    if not claude_path:
        raise FileNotFoundError("Claude Code CLI not found in PATH")

    log(f"Running Claude Code on project '{project}': {prompt[:80]}...")
    cmd = [claude_path, "-p", prompt, "--output-format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=600, cwd=project_dir)
    except Exception as e:
        raise RuntimeError(f"[CQ-004] Claude Code subprocess failed: {e}")

    output = result.stdout.strip() if result.stdout else ""
    # Try to parse JSON output from claude
    try:
        parsed = json.loads(output)
        summary = parsed.get("result", output[:500])
    except (json.JSONDecodeError, TypeError):
        summary = output[:500]

    return {"stdout": output[:2000], "project": project, "summary": summary}


def handle_sync_trigger(task: dict) -> dict:
    """
    Manually push file changes to changes.json — bypasses TCC blind spot.
    Claude Code calls this after editing files in ~/Documents/ that the
    change watcher daemon can't see due to macOS TCC restrictions.
    """
    files_changed = task.get("files", [])[:MAX_SYNC_FILES]
    action = task.get("action", "modified")
    source = task.get("source", "claude-code")

    if not files_changed:
        return {"message": "No files specified", "synced": 0}

    changes_file = SYNC_DIR / "changes.json"
    existing = []
    if changes_file.exists():
        try:
            with open(changes_file) as f:
                data = json.load(f)
                existing = data.get("recentChanges", [])
        except (json.JSONDecodeError, KeyError):
            pass

    now = datetime.now().isoformat()
    for filepath in files_changed:
        existing.append({
            "file": filepath,
            "action": action,
            "timestamp": now,
            "source": source,
            "size": 0,
        })

    existing = existing[-100:]
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    with open(changes_file, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump({"lastUpdated": now, "recentChanges": existing}, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    try:
        os.chmod(changes_file, 0o660)
    except PermissionError:
        pass

    return {"synced": len(files_changed), "files": files_changed}


def _write_notification(task_id: str, task_type: str, status: str, summary: str):
    """Append a notification for OpenClaw to read during heartbeat."""
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SYNC_DIR, 0o770)
    except PermissionError:
        pass

    # Load existing notifications
    notifications = []
    if NOTIFICATIONS_FILE.exists():
        try:
            with open(NOTIFICATIONS_FILE) as f:
                data = json.load(f)
                notifications = data.get("unread", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Append new notification
    notifications.append({
        "id": task_id,
        "task": task_type,
        "status": status,
        "summary": summary[:200],
        "timestamp": datetime.now().isoformat(),
    })

    # Keep last 50
    notifications = notifications[-50:]

    with open(NOTIFICATIONS_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump({
                "lastUpdated": datetime.now().isoformat(),
                "unread": notifications,
            }, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    try:
        os.chmod(NOTIFICATIONS_FILE, 0o660)
    except PermissionError:
        pass


def handle_training_scan(task: dict) -> dict:
    """Run the Training Officer scan via inbox task."""
    dry_run = task.get("dry_run", False)
    args = []
    if dry_run:
        args.append("--dry-run")
    result = _run_script("training_officer_scan.py", args, timeout=600)
    return result


def handle_training_approve(task: dict) -> dict:
    """Approve or reject a Training Officer proposal via inbox task."""
    proposal_id = task.get("proposal_id", "")
    action = task.get("action", "approve")  # "approve" or "reject"
    reason = task.get("reason", "Approved via inbox")

    if not proposal_id:
        raise ValueError("training_approve requires 'proposal_id' field")

    if action == "approve":
        result = _run_script("apply_proposal.py", ["--approve", proposal_id])
    elif action == "reject":
        result = _run_script("apply_proposal.py", ["--reject", proposal_id, "--reason", reason])
    else:
        raise ValueError(f"Unknown action: {action}. Use 'approve' or 'reject'.")

    return result


def handle_sync_memory(task: dict) -> dict:
    """Store OpenClaw conversation/decision entries into Claude Code's memory.db.

    Task format:
        {
            "task": "sync_memory",
            "entries": [
                {
                    "type": "decision|learning|preference|event|idea",
                    "category": "agency|amazon|general|...",
                    "title": "one-line summary",
                    "content": "full detail",
                    "tags": "comma,separated"
                }
            ],
            "source": "openclaw"  // optional label
        }
    """
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from execution.memory_store import MemoryStore, DB_PATH

        entries = task.get("entries", [])
        if not entries:
            # Also support flat single-entry format
            single = {k: task[k] for k in ("type", "category", "title", "content", "tags") if k in task}
            if single.get("title"):
                entries = [single]

        if not entries:
            return {"status": "error", "message": "No entries provided"}

        store   = MemoryStore(DB_PATH)
        source  = task.get("source", "openclaw")
        stored  = 0
        for entry in entries:
            store.add(
                type=entry.get("type", "event"),
                category=entry.get("category", "general"),
                title=entry["title"],
                content=entry.get("content", ""),
                source=source,
                tags=entry.get("tags", "openclaw"),
            )
            stored += 1

        # CRIT-4: do NOT echo back to openclaw_bridge.write_event here.
        # write_event → _update_oc_memory_md would label OC's own decisions as
        # "Claude Code activity" and fill MEMORY.md with mislabeled content.
        # memory.db is the shared truth — that's sufficient.

        return {"status": "success", "stored": stored}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def handle_search_knowledge(task: dict) -> dict:
    """OC delegates a knowledge search to CC. Queries memory.db via BM25 + returns results.

    Task format:
        {
            "task": "search_knowledge",
            "query": "Kabrin infrastructure",
            "limit": 5,           // optional, default 5, max 20
            "type": "person"      // optional type filter
        }
    """
    query = task.get("query", "").strip()
    if not query:
        return {"status": "error", "message": "search_knowledge requires 'query'"}
    limit = min(int(task.get("limit", 5)), 20)
    type_filter = task.get("type", "")
    cmd = [str(VENV_PYTHON), "execution/memory_recall.py", "--query", query, "--limit", str(limit)]
    if type_filter:
        cmd += ["--type", type_filter]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30)
    return {"status": "success", "query": query, "results": result.stdout, "error": result.stderr or None}


def handle_training_benchmark(task: dict) -> dict:
    """Run agent benchmarks via inbox task."""
    agent = task.get("agent", None)
    args = ["--run"]
    if agent:
        args += ["--agent", agent]
    result = _run_script("agent_benchmark.py", args, timeout=600)
    return result


def main():
    log("watch_inbox.py started")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Watching:     {INBOX}")
    log(f"Output:       {OUTBOX}")

    for d in [INBOX, OUTBOX, MEMORY, PROPOSALS]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o770)
        except PermissionError:
            pass  # dirs already exist with correct permissions, owned by another user

    while True:
        task_files = sorted(INBOX.glob("*.json"))[:MAX_TASKS_PER_CYCLE]
        for task_file in task_files:
            try:
                process_task(task_file)
            except Exception as e:
                # Catch-all: never let one bad task kill the daemon
                log(f"FATAL in process_task: {e}")
                send_telegram_alert(f"*Daemon Error*: Unhandled exception in inbox watcher\n`{str(e)[:200]}`")
                try:
                    task_file.rename(task_file.with_suffix(ERROR_SUFFIX))
                except Exception:
                    pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
