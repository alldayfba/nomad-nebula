#!/usr/bin/env python3
"""Work session time tracker with heartbeat-based auto clock-out."""
from __future__ import annotations

import argparse
import datetime
import json
import os

TIMELOG = "/Users/Shared/antigravity/memory/timelog.md"
HEARTBEAT = "/Users/Shared/antigravity/memory/.timeclock_heartbeat"


def now():
    return datetime.datetime.now()


def _parse_duration(dur_str: str) -> int:
    """Parse duration string like '1h 16m' or '45m' into total minutes."""
    total = 0
    dur_str = dur_str.strip()
    if "h" in dur_str and "m" in dur_str:
        h, m = dur_str.replace("m", "").split("h")
        total = int(h.strip()) * 60 + int(m.strip())
    elif "h" in dur_str:
        total = int(dur_str.replace("h", "").strip()) * 60
    elif "m" in dur_str:
        total = int(dur_str.replace("m", "").strip())
    return total


def _fmt_duration(total_mins: int) -> str:
    """Format minutes into 'Xh Ym'."""
    h = total_mins // 60
    m = total_mins % 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _calc_duration(in_dt: datetime.datetime, out_dt: datetime.datetime) -> str:
    """Calculate duration between two datetimes."""
    delta = out_dt - in_dt
    total_secs = int(delta.total_seconds())
    if total_secs < 0:
        total_secs = 0
    total_mins = total_secs // 60
    return _fmt_duration(total_mins)


def _get_heartbeat_time() -> datetime.datetime | None:
    """Get the last heartbeat timestamp."""
    if not os.path.exists(HEARTBEAT):
        return None
    try:
        mtime = os.path.getmtime(HEARTBEAT)
        return datetime.datetime.fromtimestamp(mtime)
    except OSError:
        return None


def heartbeat():
    """Touch heartbeat file to record last active time."""
    with open(HEARTBEAT, "w") as f:
        f.write(now().isoformat())


def _close_stale_sessions():
    """Auto-close any open sessions using heartbeat or +4h cap."""
    if not os.path.exists(TIMELOG):
        return
    with open(TIMELOG, "r") as f:
        lines = f.readlines()

    changed = False
    for i in range(len(lines) - 1, -1, -1):
        if "| — | — |" not in lines[i]:
            continue
        parts = lines[i].split("|")
        date_str = parts[1].strip()
        in_time_str = parts[2].strip()
        in_dt = datetime.datetime.strptime(f"{date_str} {in_time_str}", "%Y-%m-%d %H:%M")

        # Use heartbeat if available and after clock-in, otherwise cap at +4h
        hb = _get_heartbeat_time()
        if hb and hb > in_dt:
            out_dt = hb
        else:
            out_dt = in_dt + datetime.timedelta(hours=4)

        # Only auto-close if session is stale (>30 min since heartbeat or >4h old)
        age = now() - in_dt
        if age.total_seconds() < 1800:  # less than 30 min, probably still active
            continue

        out_time = out_dt.strftime("%H:%M")
        duration = _calc_duration(in_dt, out_dt)
        existing_notes = parts[5].strip().rstrip("|").strip()
        notes = f"{existing_notes} (auto-closed)".strip()

        lines[i] = f"| {date_str} | {in_time_str} | {out_time} | {duration} | {notes} |\n"
        changed = True
        print(f"  Auto-closed stale session from {date_str} {in_time_str} → {out_time} ({duration})")

    if changed:
        with open(TIMELOG, "w") as f:
            f.writelines(lines)


def clock_in(notes: str = ""):
    """Clock in. Auto-closes any stale open sessions first."""
    _close_stale_sessions()
    ts = now()
    line = f"| {ts.strftime('%Y-%m-%d')} | {ts.strftime('%H:%M')} | — | — | {notes} |"
    with open(TIMELOG, "a") as f:
        f.write(line + "\n")
    heartbeat()
    print(f"Clocked in at {ts.strftime('%H:%M')} on {ts.strftime('%Y-%m-%d')}")


def clock_out(notes: str = ""):
    """Clock out the current open session."""
    with open(TIMELOG, "r") as f:
        lines = f.readlines()

    updated = False
    for i in range(len(lines) - 1, -1, -1):
        if "| — | — |" in lines[i]:
            parts = lines[i].split("|")
            date_str = parts[1].strip()
            in_time_str = parts[2].strip()
            ts = now()
            out_time = ts.strftime("%H:%M")
            in_dt = datetime.datetime.strptime(f"{date_str} {in_time_str}", "%Y-%m-%d %H:%M")
            duration = _calc_duration(in_dt, ts)

            existing_notes = parts[5].strip().rstrip("|").strip()
            combined_notes = f"{existing_notes} {notes}".strip() if notes else existing_notes

            lines[i] = f"| {date_str} | {in_time_str} | {out_time} | {duration} | {combined_notes} |\n"
            updated = True
            print(f"Clocked out at {out_time}. Session: {duration}")
            break

    if updated:
        with open(TIMELOG, "w") as f:
            f.writelines(lines)
    else:
        print("No open clock-in found.")


def status():
    """Show current status + today's total."""
    if not os.path.exists(TIMELOG):
        print("No timelog found.")
        return

    with open(TIMELOG, "r") as f:
        lines = f.readlines()

    today = now().strftime("%Y-%m-%d")
    total_mins = 0
    sessions = []
    active_session = None

    for line in lines:
        if not line.startswith("|") or "Date" in line or "---" in line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        date_str = parts[1].strip()
        if date_str != today:
            continue

        in_time = parts[2].strip()
        out_time = parts[3].strip()
        dur = parts[4].strip()
        notes = parts[5].strip().rstrip("|").strip()

        if "— " in out_time or out_time == "—":
            # Active session
            in_dt = datetime.datetime.strptime(f"{date_str} {in_time}", "%Y-%m-%d %H:%M")
            active_mins = int((now() - in_dt).total_seconds()) // 60
            active_session = {"in": in_time, "mins": active_mins, "notes": notes}
            total_mins += active_mins
        else:
            closed_mins = _parse_duration(dur)
            total_mins += closed_mins
            sessions.append({"in": in_time, "out": out_time, "dur": dur, "notes": notes})

    # Print summary
    print(f"=== {today} ===")
    for s in sessions:
        print(f"  {s['in']} → {s['out']}  ({s['dur']})  {s['notes']}")
    if active_session:
        print(f"  {active_session['in']} → NOW     ({_fmt_duration(active_session['mins'])})  {active_session['notes']}  ◀ ACTIVE")
    print(f"  TOTAL: {_fmt_duration(total_mins)}")


def tally(date_str: str = ""):
    """End-of-day tally with all sessions listed."""
    target = date_str or now().strftime("%Y-%m-%d")
    if not os.path.exists(TIMELOG):
        print("No timelog found.")
        return

    with open(TIMELOG, "r") as f:
        lines = f.readlines()

    total_mins = 0
    sessions = []

    for line in lines:
        if not line.startswith("|") or "Date" in line or "---" in line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        if parts[1].strip() != target:
            continue

        in_time = parts[2].strip()
        out_time = parts[3].strip()
        dur = parts[4].strip()
        notes = parts[5].strip().rstrip("|").strip()

        if "—" not in out_time:
            closed_mins = _parse_duration(dur)
            total_mins += closed_mins
            sessions.append({"in": in_time, "out": out_time, "dur": dur, "notes": notes})

    print(f"=== DAILY TALLY: {target} ===")
    if not sessions:
        print("  No completed sessions.")
        return
    for i, s in enumerate(sessions, 1):
        print(f"  Session {i}: {s['in']} → {s['out']}  ({s['dur']})  {s['notes']}")
    print(f"  ────────────────────────")
    print(f"  TOTAL: {_fmt_duration(total_mins)}")
    return total_mins


def quick_total() -> str:
    """Return just today's total as a string for status line use."""
    if not os.path.exists(TIMELOG):
        return "0m"

    with open(TIMELOG, "r") as f:
        lines = f.readlines()

    today = now().strftime("%Y-%m-%d")
    total_mins = 0

    for line in lines:
        if not line.startswith("|") or "Date" in line or "---" in line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        if parts[1].strip() != today:
            continue

        out_time = parts[3].strip()
        dur = parts[4].strip()
        in_time = parts[2].strip()

        if "—" in out_time or out_time == "—":
            in_dt = datetime.datetime.strptime(f"{today} {in_time}", "%Y-%m-%d %H:%M")
            total_mins += int((now() - in_dt).total_seconds()) // 60
        else:
            total_mins += _parse_duration(dur)

    return _fmt_duration(total_mins)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Work time tracker")
    parser.add_argument("action", choices=["in", "out", "status", "tally", "heartbeat", "quick"],
                        help="Clock in, out, status, daily tally, heartbeat, or quick total")
    parser.add_argument("--notes", "-n", default="", help="Session notes")
    parser.add_argument("--date", "-d", default="", help="Date for tally (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.action == "in":
        clock_in(args.notes)
    elif args.action == "out":
        clock_out(args.notes)
    elif args.action == "status":
        status()
    elif args.action == "tally":
        tally(args.date)
    elif args.action == "heartbeat":
        heartbeat()
        print("Heartbeat recorded.")
    elif args.action == "quick":
        print(quick_total())
