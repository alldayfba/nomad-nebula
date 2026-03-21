#!/usr/bin/env python3
"""
Script: training_officer_webhook.py
Purpose: Modal webhook for scheduled Training Officer scans.
         Runs on a schedule (daily/hourly) without the Mac needing to be awake.

Deploy:
  modal deploy execution/training_officer_webhook.py

Endpoints:
  GET  /training-officer/scan     — Run a full scan
  GET  /training-officer/health   — Agent health check
  GET  /training-officer/pending  — List pending proposals
  GET  /training-officer/drift    — Run quality drift detection

Schedule:
  Runs daily at 6 AM UTC automatically via Modal cron.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    import modal
except ImportError:
    print("[training-officer-webhook] ERROR: modal not installed. Run: pip install modal")
    sys.exit(1)


def notify_discord(slug: str, success: bool, duration: float, error: str = "") -> None:
    """Send a Discord notification on webhook completion (success or failure).

    Reads DISCORD_WEBHOOK_URL or DISCORD_CLOUD_LOG_WEBHOOK from env.
    Silently no-ops if neither is set or if Discord is unreachable.
    Never raises — monitoring must never crash the monitored function.
    """
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_CLOUD_LOG_WEBHOOK", "")
    if not webhook_url:
        return
    if success:
        message = f"[MODAL] \u2705 {slug} completed in {duration:.1f}s"
    else:
        short_error = (error or "")[:200]
        message = f"[MODAL] \u274c {slug} FAILED: {short_error}"
    payload = urllib.parse.urlencode({"content": message}).encode()
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

app = modal.App("training-officer")

# Mount the project code into the Modal container
project_mount = modal.Mount.from_local_dir(
    "/Users/Shared/antigravity/projects/nomad-nebula",
    remote_path="/app",
    condition=lambda path: (
        not any(x in path for x in [".tmp", ".git", "__pycache__", ".venv", "node_modules"])
        and any(path.endswith(ext) for ext in [".py", ".md", ".yaml", ".yml", ".json", ".txt", ".env"])
    ),
)

image = modal.Image.debian_slim(python_version="3.11").pip_install("anthropic")


@app.function(
    image=image,
    mounts=[project_mount],
    secrets=[modal.Secret.from_name("anthropic-key")],
    timeout=600,
)
@modal.web_endpoint(method="GET", label="training-officer-scan")
def scan():
    """Run a full Training Officer scan."""
    _start = time.time()
    try:
        os.chdir("/app")
        os.environ.setdefault("NOMAD_NEBULA_ROOT", "/app")

        sys.path.insert(0, "/app/execution")
        from training_officer_scan import (
            load_env, ensure_dirs, load_last_scan, detect_changes,
            read_latest_ceo_brief, read_new_changelog_entries,
            load_learnings, match_agents, classify_upgrade_type,
            generate_proposal_content, get_next_proposal_id, write_proposal,
            get_monitored_files, save_last_scan, compute_agent_health,
            generate_report
        )

        load_env()
        ensure_dirs()

        last_scan = load_last_scan()
        last_scan_time = last_scan.get("last_scan")
        new_files, modified_files, deleted_files = detect_changes(last_scan)
        changed = new_files + modified_files

        ceo_brief = read_latest_ceo_brief()
        changelog_entries = read_new_changelog_entries(last_scan_time)
        learnings = load_learnings()

        proposals_generated = 0
        if changed:
            for filepath in changed:
                try:
                    content = Path(filepath).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if not content.strip():
                    continue
                agents = match_agents(content, filepath)
                upgrade_type = classify_upgrade_type(filepath, content)
                for agent in agents:
                    upgrade_data = generate_proposal_content(filepath, content, upgrade_type, agent, learnings)
                    if upgrade_data and upgrade_data.get("relevance_score", 0) >= 5:
                        pid = get_next_proposal_id()
                        write_proposal(pid, filepath, agent, upgrade_data, upgrade_type)
                        proposals_generated += 1

        current_files = get_monitored_files()
        save_last_scan({"last_scan": datetime.now().isoformat(), "file_hashes": current_files})

        health_data = compute_agent_health()
        report = generate_report(new_files, modified_files, deleted_files,
                                 proposals_generated, health_data, ceo_brief, changelog_entries)

        result = {
            "ok": True,
            "timestamp": datetime.now().isoformat(),
            "new_files": len(new_files),
            "modified_files": len(modified_files),
            "proposals_generated": proposals_generated,
            "report": report,
        }
        notify_discord("training-officer-scan", success=True, duration=time.time() - _start)
        return result
    except Exception as exc:
        notify_discord("training-officer-scan", success=False, duration=time.time() - _start, error=str(exc))
        raise


@app.function(image=image, mounts=[project_mount], timeout=60)
@modal.web_endpoint(method="GET", label="training-officer-health")
def health():
    """Agent health check."""
    _start = time.time()
    try:
        os.chdir("/app")
        os.environ.setdefault("NOMAD_NEBULA_ROOT", "/app")
        sys.path.insert(0, "/app/execution")
        from training_officer_scan import load_env, ensure_dirs, compute_agent_health
        load_env()
        ensure_dirs()
        result = compute_agent_health()
        notify_discord("training-officer-health", success=True, duration=time.time() - _start)
        return result
    except Exception as exc:
        notify_discord("training-officer-health", success=False, duration=time.time() - _start, error=str(exc))
        raise


@app.function(image=image, mounts=[project_mount], timeout=60)
@modal.web_endpoint(method="GET", label="training-officer-pending")
def pending():
    """List pending proposals."""
    _start = time.time()
    try:
        os.chdir("/app")
        os.environ.setdefault("NOMAD_NEBULA_ROOT", "/app")
        sys.path.insert(0, "/app/execution")
        from training_officer_scan import load_env, ensure_dirs, list_pending_proposals
        load_env()
        ensure_dirs()
        proposals = list_pending_proposals()
        result = {"count": len(proposals), "proposals": proposals}
        notify_discord("training-officer-pending", success=True, duration=time.time() - _start)
        return result
    except Exception as exc:
        notify_discord("training-officer-pending", success=False, duration=time.time() - _start, error=str(exc))
        raise


@app.function(
    image=image,
    mounts=[project_mount],
    timeout=60,
    schedule=modal.Cron("0 6 * * *"),  # Daily at 6 AM UTC
)
def scheduled_scan():
    """Scheduled daily scan — runs automatically via Modal cron."""
    result = scan.remote()
    print(f"[scheduled-scan] {result.get('proposals_generated', 0)} proposals generated")
    return result
