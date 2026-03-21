#!/usr/bin/env python3
"""Daily database backup — copies all bot DBs to backup directory with integrity checks."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BACKUP_DIR = Path("/Users/Shared/antigravity/memory/backups")
RETENTION_DAYS = 14

# All databases to back up
DB_FILES = [
    PROJECT_ROOT / ".tmp" / "discord" / "discord_bot.db",
    PROJECT_ROOT / ".tmp" / "discord" / "nova_sales.db",
    PROJECT_ROOT / ".tmp" / "discord" / "nova_student_learning.db",
    PROJECT_ROOT / ".tmp" / "discord" / "nova_sales_learning.db",
    PROJECT_ROOT / ".tmp" / "coaching" / "students.db",
]

# Shared nova.db
NOVA_DB = PROJECT_ROOT / "execution" / "nova_core" / "nova.db"
if not NOVA_DB.exists():
    # Try alternate locations
    for p in [PROJECT_ROOT / ".tmp" / "nova.db", PROJECT_ROOT / "nova.db"]:
        if p.exists():
            NOVA_DB = p
            break
DB_FILES.append(NOVA_DB)


def log(msg: str):
    print(f"[backup] {msg}", file=sys.stderr)


def check_integrity(db_path: Path) -> bool:
    """Run PRAGMA integrity_check on a SQLite database."""
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return result and result[0] == "ok"
    except Exception as e:
        log(f"  Integrity check failed for {db_path.name}: {e}")
        return False


def backup_databases():
    today = datetime.now().strftime("%Y-%m-%d")
    backup_subdir = BACKUP_DIR / today
    backup_subdir.mkdir(parents=True, exist_ok=True)

    backed_up = 0
    errors = 0

    for db_path in DB_FILES:
        if not db_path.exists():
            continue

        name = db_path.name
        dest = backup_subdir / name

        # Skip if already backed up today
        if dest.exists():
            log(f"  SKIP {name} — already backed up today")
            continue

        # Check integrity before backing up
        if not check_integrity(db_path):
            log(f"  WARNING: {name} failed integrity check — backing up anyway")
            errors += 1

        try:
            # Use SQLite online backup for consistency (avoids copying mid-write)
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(dest))
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            size_kb = dest.stat().st_size // 1024
            log(f"  OK {name} → {dest} ({size_kb} KB)")
            backed_up += 1
        except Exception as e:
            log(f"  ERROR {name}: {e}")
            errors += 1

    log(f"Done: {backed_up} backed up, {errors} errors")
    return backed_up, errors


def cleanup_old_backups():
    """Remove backups older than RETENTION_DAYS."""
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = 0
    for subdir in sorted(BACKUP_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        try:
            dir_date = datetime.strptime(subdir.name, "%Y-%m-%d")
            if dir_date < cutoff:
                shutil.rmtree(subdir)
                log(f"  Cleaned up old backup: {subdir.name}")
                removed += 1
        except ValueError:
            continue  # Not a date-named directory
    if removed:
        log(f"Cleaned up {removed} old backups (>{RETENTION_DAYS} days)")


def main():
    log(f"Starting backup — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    backed_up, errors = backup_databases()
    cleanup_old_backups()

    # Return exit code for cron monitoring
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
