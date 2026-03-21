#!/usr/bin/env python3
"""
Script: project_manager.py
Purpose: Track projects, milestones, tasks, dependencies, blockers, and team assignments.
         Calculates health scores (0-100) across 6 dimensions.
         Flags at-risk projects. Runs congruence checks across the system.
         Feeds CEO morning briefing with project status.
Inputs:  CLI subcommands
Outputs: Health reports, at-risk alerts, congruence issues, briefing feed, JSON export

CLI:
    python execution/project_manager.py add-project --name "X" --business agency --owner CEO [--priority high] [--target-date 2026-04-15] [--path /path]
    python execution/project_manager.py update-project --name "X" --status paused [--notes "reason"]
    python execution/project_manager.py list-projects [--status active] [--business agency]
    python execution/project_manager.py project-detail --name "X"
    python execution/project_manager.py archive-project --name "X"

    python execution/project_manager.py add-milestone --project "X" --name "MVP" --due-date 2026-04-01 [--expected-days 14] [--owner WebBuild]
    python execution/project_manager.py update-milestone --project "X" --milestone "MVP" --status completed [--notes "done"]
    python execution/project_manager.py list-milestones --project "X" [--status in_progress]

    python execution/project_manager.py add-task --project "X" --milestone "MVP" --title "Build homepage" [--owner WebBuild] [--priority high] [--due-date 2026-03-25]
    python execution/project_manager.py update-task --id 42 --status done [--actual-hours 3.5] [--notes "shipped"]
    python execution/project_manager.py my-tasks --agent outreach [--status todo,in_progress]
    python execution/project_manager.py list-tasks --project "X" [--milestone "MVP"] [--status todo]

    python execution/project_manager.py add-dep --source-type milestone --source-project "X" --source-name "MVP" --target-type milestone --target-project "Y" --target-name "Deploy" --dep-type blocks
    python execution/project_manager.py list-deps --project "X"
    python execution/project_manager.py resolve-dep --id 5

    python execution/project_manager.py add-blocker --project "X" --title "API key missing" --severity high [--milestone "MVP"]
    python execution/project_manager.py resolve-blocker --id 3 --resolution "Key obtained"
    python execution/project_manager.py list-blockers [--status open] [--severity critical,high]

    python execution/project_manager.py assign --agent outreach --project "X" --role contributor [--allocation 50]
    python execution/project_manager.py unassign --agent outreach --project "X"
    python execution/project_manager.py workload [--agent outreach]

    python execution/project_manager.py health-report
    python execution/project_manager.py at-risk
    python execution/project_manager.py status-report [--project "X"]
    python execution/project_manager.py congruence
    python execution/project_manager.py dashboard-data
    python execution/project_manager.py briefing-feed
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / ".tmp" / "projects" / "projects.db"

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    business TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    priority TEXT DEFAULT 'medium',
    owner TEXT NOT NULL,
    description TEXT,
    start_date TEXT NOT NULL,
    target_date TEXT,
    completed_date TEXT,
    health_score INTEGER DEFAULT 100,
    path TEXT,
    repo_url TEXT,
    original_task_count INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'medium',
    owner TEXT,
    start_date TEXT,
    due_date TEXT,
    completed_date TEXT,
    days_on_milestone INTEGER DEFAULT 0,
    expected_days INTEGER DEFAULT 14,
    sort_order INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'todo',
    priority TEXT DEFAULT 'medium',
    owner TEXT,
    estimated_hours REAL,
    actual_hours REAL,
    due_date TEXT,
    completed_date TEXT,
    blocked_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (milestone_id) REFERENCES milestones(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    dep_type TEXT DEFAULT 'blocks',
    status TEXT DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(source_type, source_id, target_type, target_id)
);

CREATE TABLE IF NOT EXISTS blockers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    milestone_id INTEGER,
    task_id INTEGER,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    owner TEXT,
    escalated_to TEXT,
    escalated_at TEXT,
    resolved_at TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS team_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    role TEXT DEFAULT 'contributor',
    allocation_pct INTEGER DEFAULT 100,
    assigned_at TEXT NOT NULL,
    unassigned_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    UNIQUE(agent, project_id)
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    breakdown TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    details TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_milestones_status ON milestones(status);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
CREATE INDEX IF NOT EXISTS idx_blockers_project ON blockers(project_id);
CREATE INDEX IF NOT EXISTS idx_blockers_status ON blockers(status);
CREATE INDEX IF NOT EXISTS idx_assignments_agent ON team_assignments(agent);
CREATE INDEX IF NOT EXISTS idx_activity_project ON activity_log(project_id);
CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_health_project ON health_snapshots(project_id);
"""

# ── Health Scoring Weights ───────────────────────────────────────────────────

WEIGHTS = {
    "schedule":     25,
    "velocity":     20,
    "blockers":     20,
    "scope":        15,
    "engagement":   10,
    "dependencies": 10,
}

HEALTH_THRESHOLDS = {"healthy": 70, "at_risk": 40}

VALID_STATUSES = ["planning", "active", "paused", "blocked", "completed", "archived"]
VALID_PRIORITIES = ["critical", "high", "medium", "low"]
VALID_TASK_STATUSES = ["todo", "in_progress", "review", "done", "blocked"]
VALID_MILESTONE_STATUSES = ["pending", "in_progress", "completed", "blocked", "skipped"]
VALID_SEVERITIES = ["critical", "high", "medium", "low"]
VALID_ROLES = ["lead", "contributor", "reviewer", "consultant"]
VALID_BUSINESSES = ["agency", "amazon", "internal", "both"]


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def _now():
    return datetime.utcnow().isoformat()


def _today():
    return datetime.utcnow().strftime("%Y-%m-%d")


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _log_activity(conn, project_id, action, actor=None, details=None):
    conn.execute(
        "INSERT INTO activity_log (project_id, action, actor, details, date) VALUES (?, ?, ?, ?, ?)",
        (project_id, action, actor, details, _today()),
    )


# ── Project CRUD ─────────────────────────────────────────────────────────────

def add_project(name, business, owner, priority="medium", target_date=None,
                path=None, repo_url=None, description=None, notes=None):
    conn = get_db()
    try:
        now = _now()
        today = _today()
        slug = _slugify(name)
        conn.execute("""
            INSERT INTO projects
                (name, slug, business, status, priority, owner, description,
                 start_date, target_date, path, repo_url, notes, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, slug, business, priority, owner, description,
              today, target_date, path, repo_url, notes, now, now))
        project_id = conn.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()["id"]
        _log_activity(conn, project_id, "project_created", owner, f"Created project: {name}")
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_project(name, status=None, priority=None, target_date=None, notes=None, owner=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{name}' not found.")

        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_date = ?")
                params.append(_today())
        if priority:
            updates.append("priority = ?")
            params.append(priority)
        if target_date:
            updates.append("target_date = ?")
            params.append(target_date)
        if notes:
            updates.append("notes = ?")
            params.append(notes)
        if owner:
            updates.append("owner = ?")
            params.append(owner)

        if updates:
            updates.append("updated_at = ?")
            params.append(_now())
            params.append(project["id"])
            conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
            changes = ", ".join(f"{k}={v}" for k, v in zip(
                [u.split(" = ")[0] for u in updates if u != "updated_at = ?"],
                [p for p in params[:-2] if p != _now()]
            ))
            _log_activity(conn, project["id"], "project_updated", None, changes)
            conn.commit()

        return dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project["id"],)).fetchone())
    finally:
        conn.close()


def list_projects(status=None, business=None, include_archived=False):
    conn = get_db()
    try:
        query = "SELECT * FROM projects WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        elif not include_archived:
            query += " AND status != 'archived'"
        if business:
            query += " AND business = ?"
            params.append(business)
        query += " ORDER BY health_score ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def project_detail(name):
    conn = get_db()
    try:
        project = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        if not project:
            return None
        pid = project["id"]

        milestones = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY sort_order, id", (pid,)
        ).fetchall()
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY milestone_id, id", (pid,)
        ).fetchall()
        blockers = conn.execute(
            "SELECT * FROM blockers WHERE project_id = ? AND status = 'open' ORDER BY severity", (pid,)
        ).fetchall()
        team = conn.execute(
            "SELECT * FROM team_assignments WHERE project_id = ? AND unassigned_at IS NULL", (pid,)
        ).fetchall()
        activity = conn.execute(
            "SELECT * FROM activity_log WHERE project_id = ? ORDER BY date DESC, id DESC LIMIT 20", (pid,)
        ).fetchall()
        snapshots = conn.execute(
            "SELECT * FROM health_snapshots WHERE project_id = ? ORDER BY date DESC LIMIT 14", (pid,)
        ).fetchall()

        return {
            "project": dict(project),
            "milestones": [dict(m) for m in milestones],
            "tasks": [dict(t) for t in tasks],
            "open_blockers": [dict(b) for b in blockers],
            "team": [dict(t) for t in team],
            "recent_activity": [dict(a) for a in activity],
            "health_history": [dict(s) for s in snapshots],
        }
    finally:
        conn.close()


def archive_project(name):
    return update_project(name, status="archived")


# ── Milestone CRUD ───────────────────────────────────────────────────────────

def add_milestone(project_name, name, due_date=None, expected_days=14,
                  owner=None, description=None, sort_order=0):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        conn.execute("""
            INSERT INTO milestones
                (project_id, name, description, status, owner, start_date,
                 due_date, expected_days, sort_order, created_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
        """, (project["id"], name, description, owner, _today(),
              due_date, expected_days, sort_order, _now()))
        _log_activity(conn, project["id"], "milestone_added", owner, f"Added milestone: {name}")
        conn.commit()
        return {"project": project_name, "milestone": name, "due_date": due_date}
    finally:
        conn.close()


def update_milestone(project_name, milestone_name, status=None, notes=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        ms = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? AND name = ?",
            (project["id"], milestone_name)
        ).fetchone()
        if not ms:
            raise ValueError(f"Milestone '{milestone_name}' not found in project '{project_name}'.")

        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_date = ?")
                params.append(_today())
                if ms["start_date"]:
                    started = datetime.strptime(ms["start_date"], "%Y-%m-%d")
                    days = (datetime.utcnow() - started).days
                    updates.append("days_on_milestone = ?")
                    params.append(days)
            elif status == "in_progress" and not ms["start_date"]:
                updates.append("start_date = ?")
                params.append(_today())
        if notes:
            updates.append("notes = ?")
            params.append(notes)

        if updates:
            params.append(ms["id"])
            conn.execute(f"UPDATE milestones SET {', '.join(updates)} WHERE id = ?", params)
            _log_activity(conn, project["id"], "milestone_updated", None,
                          f"{milestone_name} -> {status or 'updated'}")
            conn.commit()

        return {"project": project_name, "milestone": milestone_name, "status": status}
    finally:
        conn.close()


def list_milestones(project_name, status=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        query = "SELECT * FROM milestones WHERE project_id = ?"
        params = [project["id"]]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY sort_order, id"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Task CRUD ────────────────────────────────────────────────────────────────

def add_task(project_name, milestone_name, title, owner=None, priority="medium",
             due_date=None, estimated_hours=None, description=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        ms = conn.execute(
            "SELECT id FROM milestones WHERE project_id = ? AND name = ?",
            (project["id"], milestone_name)
        ).fetchone()
        if not ms:
            raise ValueError(f"Milestone '{milestone_name}' not found in project '{project_name}'.")

        conn.execute("""
            INSERT INTO tasks
                (milestone_id, project_id, title, description, status, priority,
                 owner, estimated_hours, due_date, created_at)
            VALUES (?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?)
        """, (ms["id"], project["id"], title, description, priority,
              owner, estimated_hours, due_date, _now()))
        _log_activity(conn, project["id"], "task_added", owner, f"Added task: {title}")
        conn.commit()
        task = conn.execute("SELECT * FROM tasks WHERE project_id = ? AND title = ? ORDER BY id DESC LIMIT 1",
                            (project["id"], title)).fetchone()
        return dict(task)
    finally:
        conn.close()


def update_task(task_id, status=None, actual_hours=None, notes=None, owner=None):
    conn = get_db()
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise ValueError(f"Task #{task_id} not found.")

        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "done":
                updates.append("completed_date = ?")
                params.append(_today())
        if actual_hours is not None:
            updates.append("actual_hours = ?")
            params.append(actual_hours)
        if notes:
            updates.append("notes = ?")
            params.append(notes)
        if owner:
            updates.append("owner = ?")
            params.append(owner)

        if updates:
            params.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
            _log_activity(conn, task["project_id"], "task_updated", None,
                          f"Task #{task_id} '{task['title']}' -> {status or 'updated'}")
            conn.commit()

        return dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    finally:
        conn.close()


def my_tasks(agent, statuses=None):
    conn = get_db()
    try:
        query = "SELECT t.*, p.name as project_name, m.name as milestone_name FROM tasks t JOIN projects p ON t.project_id = p.id JOIN milestones m ON t.milestone_id = m.id WHERE t.owner = ?"
        params = [agent]
        if statuses:
            placeholders = ",".join("?" * len(statuses))
            query += f" AND t.status IN ({placeholders})"
            params.extend(statuses)
        query += " ORDER BY CASE t.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, t.due_date"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_tasks(project_name, milestone_name=None, status=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        query = "SELECT t.*, m.name as milestone_name FROM tasks t JOIN milestones m ON t.milestone_id = m.id WHERE t.project_id = ?"
        params = [project["id"]]
        if milestone_name:
            query += " AND m.name = ?"
            params.append(milestone_name)
        if status:
            query += " AND t.status = ?"
            params.append(status)
        query += " ORDER BY m.sort_order, t.id"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Dependencies ─────────────────────────────────────────────────────────────

def _resolve_entity(conn, entity_type, project_name, entity_name):
    project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
    if not project:
        raise ValueError(f"Project '{project_name}' not found.")
    if entity_type == "project":
        return project["id"]
    elif entity_type == "milestone":
        ms = conn.execute(
            "SELECT id FROM milestones WHERE project_id = ? AND name = ?",
            (project["id"], entity_name)
        ).fetchone()
        if not ms:
            raise ValueError(f"Milestone '{entity_name}' not found in '{project_name}'.")
        return ms["id"]
    elif entity_type == "task":
        task = conn.execute(
            "SELECT id FROM tasks WHERE project_id = ? AND title = ?",
            (project["id"], entity_name)
        ).fetchone()
        if not task:
            raise ValueError(f"Task '{entity_name}' not found in '{project_name}'.")
        return task["id"]
    else:
        raise ValueError(f"Invalid entity type: {entity_type}")


def add_dependency(source_type, source_project, source_name,
                   target_type, target_project, target_name, dep_type="blocks"):
    conn = get_db()
    try:
        source_id = _resolve_entity(conn, source_type, source_project, source_name)
        target_id = _resolve_entity(conn, target_type, target_project, target_name)
        conn.execute("""
            INSERT INTO dependencies (source_type, source_id, target_type, target_id, dep_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (source_type, source_id, target_type, target_id, dep_type, _now()))
        # Log on source project
        src_project = conn.execute("SELECT id FROM projects WHERE name = ?", (source_project,)).fetchone()
        if src_project:
            _log_activity(conn, src_project["id"], "dependency_added", None,
                          f"{source_type}:{source_name} {dep_type} {target_type}:{target_name}")
        conn.commit()
        return {"source": f"{source_type}:{source_name}", "target": f"{target_type}:{target_name}", "type": dep_type}
    finally:
        conn.close()


def list_dependencies(project_name):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        # Get all milestone and task IDs for this project
        ms_ids = [r["id"] for r in conn.execute("SELECT id FROM milestones WHERE project_id = ?", (project["id"],)).fetchall()]
        task_ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE project_id = ?", (project["id"],)).fetchall()]

        deps = []
        for row in conn.execute("SELECT * FROM dependencies WHERE status = 'active'").fetchall():
            involved = False
            if row["source_type"] == "project" and row["source_id"] == project["id"]:
                involved = True
            elif row["target_type"] == "project" and row["target_id"] == project["id"]:
                involved = True
            elif row["source_type"] == "milestone" and row["source_id"] in ms_ids:
                involved = True
            elif row["target_type"] == "milestone" and row["target_id"] in ms_ids:
                involved = True
            elif row["source_type"] == "task" and row["source_id"] in task_ids:
                involved = True
            elif row["target_type"] == "task" and row["target_id"] in task_ids:
                involved = True
            if involved:
                deps.append(dict(row))
        return deps
    finally:
        conn.close()


def resolve_dependency(dep_id):
    conn = get_db()
    try:
        conn.execute("UPDATE dependencies SET status = 'resolved' WHERE id = ?", (dep_id,))
        conn.commit()
        return {"id": dep_id, "status": "resolved"}
    finally:
        conn.close()


# ── Blockers ─────────────────────────────────────────────────────────────────

def add_blocker(project_name, title, severity="medium", milestone_name=None,
                description=None, owner=None):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        milestone_id = None
        if milestone_name:
            ms = conn.execute(
                "SELECT id FROM milestones WHERE project_id = ? AND name = ?",
                (project["id"], milestone_name)
            ).fetchone()
            if ms:
                milestone_id = ms["id"]

        conn.execute("""
            INSERT INTO blockers (project_id, milestone_id, title, description, severity, status, owner, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
        """, (project["id"], milestone_id, title, description, severity, owner, _now()))
        _log_activity(conn, project["id"], "blocker_added", owner,
                      f"[{severity.upper()}] {title}")
        conn.commit()
        return {"project": project_name, "title": title, "severity": severity}
    finally:
        conn.close()


def resolve_blocker(blocker_id, resolution):
    conn = get_db()
    try:
        blocker = conn.execute("SELECT * FROM blockers WHERE id = ?", (blocker_id,)).fetchone()
        if not blocker:
            raise ValueError(f"Blocker #{blocker_id} not found.")

        conn.execute("""
            UPDATE blockers SET status = 'resolved', resolution = ?, resolved_at = ? WHERE id = ?
        """, (resolution, _now(), blocker_id))
        _log_activity(conn, blocker["project_id"], "blocker_resolved", None,
                      f"Resolved: {blocker['title']} — {resolution}")
        conn.commit()
        return {"id": blocker_id, "status": "resolved", "resolution": resolution}
    finally:
        conn.close()


def list_blockers(status=None, severity=None):
    conn = get_db()
    try:
        query = "SELECT b.*, p.name as project_name FROM blockers b JOIN projects p ON b.project_id = p.id WHERE 1=1"
        params = []
        if status:
            query += " AND b.status = ?"
            params.append(status)
        if severity:
            sevs = severity.split(",")
            placeholders = ",".join("?" * len(sevs))
            query += f" AND b.severity IN ({placeholders})"
            params.extend(sevs)
        query += " ORDER BY CASE b.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Team Assignments ─────────────────────────────────────────────────────────

def assign_agent(agent, project_name, role="contributor", allocation=100):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        conn.execute("""
            INSERT OR REPLACE INTO team_assignments (agent, project_id, role, allocation_pct, assigned_at)
            VALUES (?, ?, ?, ?, ?)
        """, (agent, project["id"], role, allocation, _now()))
        _log_activity(conn, project["id"], "agent_assigned", agent,
                      f"{agent} assigned as {role} ({allocation}%)")
        conn.commit()
        return {"agent": agent, "project": project_name, "role": role, "allocation": allocation}
    finally:
        conn.close()


def unassign_agent(agent, project_name):
    conn = get_db()
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if not project:
            raise ValueError(f"Project '{project_name}' not found.")

        conn.execute("""
            UPDATE team_assignments SET unassigned_at = ? WHERE agent = ? AND project_id = ? AND unassigned_at IS NULL
        """, (_now(), agent, project["id"]))
        _log_activity(conn, project["id"], "agent_unassigned", agent, f"{agent} unassigned")
        conn.commit()
        return {"agent": agent, "project": project_name, "status": "unassigned"}
    finally:
        conn.close()


def workload(agent=None):
    conn = get_db()
    try:
        query = """
            SELECT ta.agent, ta.allocation_pct, ta.role, p.name as project_name, p.status as project_status
            FROM team_assignments ta
            JOIN projects p ON ta.project_id = p.id
            WHERE ta.unassigned_at IS NULL AND p.status NOT IN ('completed', 'archived')
        """
        params = []
        if agent:
            query += " AND ta.agent = ?"
            params.append(agent)
        query += " ORDER BY ta.agent, ta.allocation_pct DESC"
        rows = conn.execute(query, params).fetchall()

        # Group by agent
        result = {}
        for r in rows:
            a = r["agent"]
            if a not in result:
                result[a] = {"agent": a, "projects": [], "total_allocation": 0}
            result[a]["projects"].append({
                "project": r["project_name"],
                "role": r["role"],
                "allocation": r["allocation_pct"],
            })
            result[a]["total_allocation"] += r["allocation_pct"]

        for a in result.values():
            a["overloaded"] = a["total_allocation"] > 100

        return list(result.values())
    finally:
        conn.close()


# ── Health Scoring ───────────────────────────────────────────────────────────

def calculate_health_score(project_id):
    conn = get_db()
    try:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return None

        # ── 1. Schedule (25) ─────────────────────────────────────────────────
        milestones = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ?", (project_id,)
        ).fetchall()
        today = datetime.utcnow()
        schedule_score = WEIGHTS["schedule"]  # start at max

        overdue_count = 0
        for ms in milestones:
            if ms["status"] in ("completed", "skipped"):
                continue
            if ms["due_date"]:
                due = datetime.strptime(ms["due_date"], "%Y-%m-%d")
                if today > due:
                    overdue_count += 1
            if ms["start_date"] and ms["expected_days"]:
                started = datetime.strptime(ms["start_date"], "%Y-%m-%d")
                actual_days = (today - started).days
                if actual_days > ms["expected_days"]:
                    ratio = min(ms["expected_days"] / max(actual_days, 1), 1.0)
                    schedule_score = max(0, schedule_score - int((1 - ratio) * 10))

        schedule_score = max(0, schedule_score - (overdue_count * 5))

        # ── 2. Velocity (20) ────────────────────────────────────────────────
        cutoff_14d = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        done_recent = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ? AND status = 'done' AND completed_date >= ?",
            (project_id, cutoff_14d)
        ).fetchone()["cnt"]

        total_tasks = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ?", (project_id,)
        ).fetchone()["cnt"]
        remaining = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ? AND status NOT IN ('done')",
            (project_id,)
        ).fetchone()["cnt"]

        if total_tasks == 0:
            velocity_score = WEIGHTS["velocity"]  # no tasks yet = neutral
        else:
            # Expected: remaining / (days until deadline / 14) per 2-week window
            if project["target_date"]:
                target = datetime.strptime(project["target_date"], "%Y-%m-%d")
                days_left = max((target - today).days, 1)
                windows_left = max(days_left / 14, 1)
                expected_per_window = remaining / windows_left
            else:
                expected_per_window = max(total_tasks / 4, 1)  # assume ~4 windows total

            if expected_per_window > 0:
                velocity_ratio = min(done_recent / expected_per_window, 1.5)
            else:
                velocity_ratio = 1.0
            velocity_score = round(velocity_ratio * WEIGHTS["velocity"])
            velocity_score = min(velocity_score, WEIGHTS["velocity"])

        # ── 3. Blockers (20) ────────────────────────────────────────────────
        open_blockers = conn.execute(
            "SELECT severity FROM blockers WHERE project_id = ? AND status = 'open'",
            (project_id,)
        ).fetchall()
        blocker_penalty = 0
        for b in open_blockers:
            sev = b["severity"]
            blocker_penalty += {"critical": 8, "high": 5, "medium": 3, "low": 1}.get(sev, 2)
        blockers_score = max(0, WEIGHTS["blockers"] - blocker_penalty)

        # ── 4. Scope (15) ───────────────────────────────────────────────────
        original = project["original_task_count"] or total_tasks
        if original > 0 and total_tasks > 0:
            scope_ratio = min(original / total_tasks, 1.0)
            # Allow 10% growth with no penalty
            if total_tasks <= original * 1.1:
                scope_score = WEIGHTS["scope"]
            else:
                scope_score = round(scope_ratio * WEIGHTS["scope"])
        else:
            scope_score = WEIGHTS["scope"]

        # ── 5. Engagement (10) ──────────────────────────────────────────────
        last_activity = conn.execute(
            "SELECT date FROM activity_log WHERE project_id = ? ORDER BY date DESC LIMIT 1",
            (project_id,)
        ).fetchone()
        if last_activity and last_activity["date"]:
            try:
                last_date = datetime.strptime(last_activity["date"], "%Y-%m-%d")
                days_since = (today - last_date).days
                if days_since <= 3:
                    engagement_score = WEIGHTS["engagement"]
                else:
                    engagement_score = max(0, WEIGHTS["engagement"] - (days_since - 3) * 2)
            except (ValueError, TypeError):
                engagement_score = round(0.5 * WEIGHTS["engagement"])
        else:
            engagement_score = round(0.5 * WEIGHTS["engagement"])

        # ── 6. Dependencies (10) ────────────────────────────────────────────
        ms_ids = [m["id"] for m in milestones]
        task_ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE project_id = ?", (project_id,)).fetchall()]

        blocked_deps = 0
        for dep in conn.execute("SELECT * FROM dependencies WHERE status = 'active'").fetchall():
            # Check if this project's entities are targets of active blocking deps
            is_target = False
            if dep["target_type"] == "project" and dep["target_id"] == project_id:
                is_target = True
            elif dep["target_type"] == "milestone" and dep["target_id"] in ms_ids:
                is_target = True
            elif dep["target_type"] == "task" and dep["target_id"] in task_ids:
                is_target = True

            if is_target and dep["dep_type"] == "blocks":
                # Check if the source is not yet completed
                if dep["source_type"] == "milestone":
                    src = conn.execute("SELECT status FROM milestones WHERE id = ?", (dep["source_id"],)).fetchone()
                    if src and src["status"] != "completed":
                        blocked_deps += 1
                elif dep["source_type"] == "task":
                    src = conn.execute("SELECT status FROM tasks WHERE id = ?", (dep["source_id"],)).fetchone()
                    if src and src["status"] != "done":
                        blocked_deps += 1
                elif dep["source_type"] == "project":
                    src = conn.execute("SELECT status FROM projects WHERE id = ?", (dep["source_id"],)).fetchone()
                    if src and src["status"] != "completed":
                        blocked_deps += 1

        deps_score = max(0, WEIGHTS["dependencies"] - (blocked_deps * 3))

        # ── Total ────────────────────────────────────────────────────────────
        total = schedule_score + velocity_score + blockers_score + scope_score + engagement_score + deps_score
        total = max(0, min(100, total))

        breakdown = {
            "schedule": schedule_score,
            "velocity": velocity_score,
            "blockers": blockers_score,
            "scope": scope_score,
            "engagement": engagement_score,
            "dependencies": deps_score,
        }

        # Save snapshot
        conn.execute(
            "INSERT INTO health_snapshots (project_id, score, breakdown, date) VALUES (?, ?, ?, ?)",
            (project_id, total, json.dumps(breakdown), _today()),
        )

        # Update project status based on health
        status = project["status"]
        if status not in ("completed", "archived", "paused"):
            if total < HEALTH_THRESHOLDS["at_risk"]:
                status = "blocked"
            elif total < HEALTH_THRESHOLDS["healthy"]:
                status = "active"  # at-risk but still active
            else:
                status = "active"

        conn.execute(
            "UPDATE projects SET health_score = ?, status = ?, updated_at = ? WHERE id = ?",
            (total, status, _now(), project_id),
        )
        conn.commit()

        return {"score": total, "breakdown": breakdown, "status": status}
    finally:
        conn.close()


def refresh_all_scores():
    conn = get_db()
    try:
        projects = conn.execute(
            "SELECT id, name FROM projects WHERE status NOT IN ('completed', 'archived')"
        ).fetchall()
    finally:
        conn.close()

    results = []
    for p in projects:
        score_data = calculate_health_score(p["id"])
        if score_data:
            results.append({"name": p["name"], **score_data})
    return results


def get_at_risk():
    refresh_all_scores()
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM projects
            WHERE status NOT IN ('completed', 'archived')
            AND health_score < ?
            ORDER BY health_score ASC
        """, (HEALTH_THRESHOLDS["healthy"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Reports ──────────────────────────────────────────────────────────────────

def health_report():
    results = refresh_all_scores()
    if not results:
        return "No active projects found."

    lines = [
        "═══ PROJECT HEALTH REPORT ═══",
        "",
        f"{'Project':<25} {'Score':>6} {'Status':<10} {'Sch':>4} {'Vel':>4} {'Blk':>4} {'Scp':>4} {'Eng':>4} {'Dep':>4}",
        "─" * 75,
    ]

    for r in sorted(results, key=lambda x: x["score"]):
        b = r["breakdown"]
        status_icon = "OK" if r["score"] >= HEALTH_THRESHOLDS["healthy"] else (
            "WARN" if r["score"] >= HEALTH_THRESHOLDS["at_risk"] else "CRIT"
        )
        lines.append(
            f"{r['name']:<25} {r['score']:>5}  {status_icon:<10} "
            f"{b['schedule']:>3} {b['velocity']:>3} {b['blockers']:>3} "
            f"{b['scope']:>3} {b['engagement']:>3} {b['dependencies']:>3}"
        )

    at_risk = [r for r in results if r["score"] < HEALTH_THRESHOLDS["healthy"]]
    lines.append("")
    lines.append(f"Projects at risk: {len(at_risk)}/{len(results)}")
    for r in at_risk:
        level = "CRITICAL" if r["score"] < HEALTH_THRESHOLDS["at_risk"] else "AT RISK"
        lines.append(f"  [{level}] {r['name']} — score {r['score']}")

    return "\n".join(lines)


def status_report(project_name=None):
    if project_name:
        detail = project_detail(project_name)
        if not detail:
            return f"Project '{project_name}' not found."
        p = detail["project"]
        lines = [
            f"═══ {p['name'].upper()} — STATUS REPORT ═══",
            f"Business: {p['business']} | Owner: {p['owner']} | Priority: {p['priority']}",
            f"Status: {p['status']} | Health: {p['health_score']}/100",
            f"Started: {p['start_date']} | Target: {p['target_date'] or 'none'}",
            "",
            "MILESTONES:",
        ]
        for ms in detail["milestones"]:
            icon = {"completed": "+", "in_progress": ">", "blocked": "X", "pending": " ", "skipped": "-"}.get(ms["status"], "?")
            lines.append(f"  [{icon}] {ms['name']} — {ms['status']} (due: {ms['due_date'] or 'none'})")

        task_stats = {}
        for t in detail["tasks"]:
            task_stats[t["status"]] = task_stats.get(t["status"], 0) + 1
        lines.append(f"\nTASKS: {len(detail['tasks'])} total — " + ", ".join(f"{v} {k}" for k, v in task_stats.items()))

        if detail["open_blockers"]:
            lines.append(f"\nBLOCKERS ({len(detail['open_blockers'])} open):")
            for b in detail["open_blockers"]:
                lines.append(f"  [{b['severity'].upper()}] {b['title']}")

        if detail["team"]:
            lines.append(f"\nTEAM:")
            for t in detail["team"]:
                lines.append(f"  {t['agent']} — {t['role']} ({t['allocation_pct']}%)")

        return "\n".join(lines)
    else:
        return health_report()


def briefing_feed():
    results = refresh_all_scores()
    if not results:
        return {"section": "PROJECT STATUS", "content": "No active projects.", "at_risk": []}

    at_risk = [r for r in results if r["score"] < HEALTH_THRESHOLDS["healthy"]]
    active_count = len(results)
    blocked_count = len([r for r in results if r["score"] < HEALTH_THRESHOLDS["at_risk"]])

    # Get next milestones due
    conn = get_db()
    try:
        upcoming = conn.execute("""
            SELECT m.name as milestone_name, m.due_date, p.name as project_name
            FROM milestones m JOIN projects p ON m.project_id = p.id
            WHERE m.status IN ('pending', 'in_progress') AND m.due_date IS NOT NULL
            AND p.status NOT IN ('completed', 'archived')
            ORDER BY m.due_date ASC LIMIT 5
        """).fetchall()
    finally:
        conn.close()

    lines = [
        f" Active: {active_count}   At Risk: {len(at_risk)}   Blocked: {blocked_count}",
    ]
    for r in at_risk:
        level = "BLOCKED" if r["score"] < HEALTH_THRESHOLDS["at_risk"] else "AT RISK"
        lines.append(f" [{level}] {r['name']} — score {r['score']}")

    if upcoming:
        lines.append("")
        lines.append(" Next milestones due:")
        for u in upcoming:
            lines.append(f"   {u['due_date']}: {u['project_name']} / {u['milestone_name']}")

    return {
        "section": "PROJECT STATUS",
        "content": "\n".join(lines),
        "at_risk": at_risk,
        "active_count": active_count,
        "blocked_count": blocked_count,
        "upcoming_milestones": [dict(u) for u in upcoming] if upcoming else [],
    }


def dashboard_data():
    results = refresh_all_scores()
    blockers = list_blockers(status="open")
    wl = workload()

    conn = get_db()
    try:
        activity = conn.execute(
            "SELECT a.*, p.name as project_name FROM activity_log a JOIN projects p ON a.project_id = p.id ORDER BY a.date DESC, a.id DESC LIMIT 15"
        ).fetchall()
        upcoming = conn.execute("""
            SELECT m.*, p.name as project_name
            FROM milestones m JOIN projects p ON m.project_id = p.id
            WHERE m.status IN ('pending', 'in_progress') AND p.status NOT IN ('completed', 'archived')
            ORDER BY m.due_date ASC
        """).fetchall()
    finally:
        conn.close()

    at_risk = [r for r in results if r["score"] < HEALTH_THRESHOLDS["healthy"]]
    avg_health = round(sum(r["score"] for r in results) / len(results)) if results else 0

    return {
        "summary": {
            "active_projects": len(results),
            "at_risk": len(at_risk),
            "open_blockers": len(blockers),
            "avg_health": avg_health,
        },
        "projects": results,
        "blockers": blockers,
        "workload": wl,
        "recent_activity": [dict(a) for a in activity],
        "upcoming_milestones": [dict(u) for u in upcoming],
        "generated_at": _now(),
    }


# ── Congruence Check ─────────────────────────────────────────────────────────

def congruence_check():
    issues = []

    # 1. Directive→Script alignment
    directives_dir = PROJECT_ROOT / "directives"
    execution_dir = PROJECT_ROOT / "execution"
    if directives_dir.exists():
        for directive in directives_dir.glob("*.md"):
            content = directive.read_text(errors="replace")
            for match in re.findall(r'execution/([a-zA-Z0-9_]+\.py)', content):
                script_path = execution_dir / match
                if not script_path.exists():
                    issues.append({
                        "type": "missing_script",
                        "severity": "high",
                        "message": f"Directive {directive.name} references execution/{match} which does not exist",
                        "fix": f"Create execution/{match} or update {directive.name}",
                    })

    # 2. Bot file completeness
    bots_dir = PROJECT_ROOT / "bots"
    required_bot_files = ["identity.md", "memory.md", "tools.md", "skills.md", "heartbeat.md"]
    if bots_dir.exists():
        for bot_dir in sorted(bots_dir.iterdir()):
            if bot_dir.is_dir() and bot_dir.name not in ("creators", "clients"):
                for req_file in required_bot_files:
                    if not (bot_dir / req_file).exists():
                        issues.append({
                            "type": "missing_bot_file",
                            "severity": "medium",
                            "message": f"Bot {bot_dir.name} missing {req_file}",
                            "fix": f"Create bots/{bot_dir.name}/{req_file}",
                        })

    # 3. Agent directive existence
    agents_dir = PROJECT_ROOT / "SabboOS" / "Agents"
    if agents_dir.exists():
        agent_files = [f.stem for f in agents_dir.glob("*.md")]
        # Check if agents referenced in bots/ have directive files
        if bots_dir.exists():
            for bot_dir in sorted(bots_dir.iterdir()):
                if bot_dir.is_dir() and bot_dir.name not in ("creators", "clients"):
                    # kebab-case bot name -> PascalCase agent name check
                    # Not all bots have agent directives, so this is info-level
                    pass

    # 4. Skill file existence check
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    if skills_dir.exists():
        for skill in skills_dir.glob("*.md"):
            if skill.name.startswith("_"):
                continue
            content = skill.read_text(errors="replace")
            # Check if referenced directives exist
            for match in re.findall(r'directives/([a-zA-Z0-9_-]+\.md)', content):
                if not (directives_dir / match).exists():
                    issues.append({
                        "type": "missing_directive",
                        "severity": "high",
                        "message": f"Skill {skill.name} references directives/{match} which does not exist",
                        "fix": f"Create directives/{match} or update {skill.name}",
                    })

    # 5. Cross-project dependency health
    conn = get_db()
    try:
        active_deps = conn.execute("SELECT * FROM dependencies WHERE status = 'active'").fetchall()
        for dep in active_deps:
            if dep["source_type"] == "project":
                src = conn.execute("SELECT name, status FROM projects WHERE id = ?", (dep["source_id"],)).fetchone()
                tgt_id = dep["target_id"]
                if dep["target_type"] == "project":
                    tgt = conn.execute("SELECT name, status FROM projects WHERE id = ?", (tgt_id,)).fetchone()
                    if src and tgt and src["status"] in ("blocked", "paused"):
                        issues.append({
                            "type": "blocked_dependency",
                            "severity": "high",
                            "message": f"Project '{tgt['name']}' depends on '{src['name']}' which is {src['status']}",
                            "fix": f"Unblock '{src['name']}' or remove dependency",
                        })

        # 6. Stale agent comms
        inbox_dir = Path("/Users/Shared/antigravity/inbox")
        if inbox_dir.exists():
            cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
            for msg_file in inbox_dir.glob("*.json"):
                try:
                    stat = msg_file.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if (datetime.utcnow() - mtime).total_seconds() > 48 * 3600:
                        issues.append({
                            "type": "stale_inbox",
                            "severity": "medium",
                            "message": f"Inbox message {msg_file.name} is >48h old and unprocessed",
                            "fix": f"Process or archive {msg_file.name}",
                        })
                except (OSError, ValueError):
                    pass

        # 7. Memory system health
        memory_db = Path("/Users/Shared/antigravity/memory/ceo/memory.db")
        if not memory_db.exists():
            issues.append({
                "type": "memory_missing",
                "severity": "critical",
                "message": "CEO memory database not found at expected path",
                "fix": "Run memory_store.py to reinitialize the database",
            })
    finally:
        conn.close()

    # 8. Script count vs CLAUDE.md claims
    if execution_dir.exists():
        actual_count = len(list(execution_dir.glob("*.py")))
        claude_md = PROJECT_ROOT / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(errors="replace")
            match = re.search(r'(\d+)\+?\s*(?:scripts|files)', content)
            if match:
                claimed = int(match.group(1))
                if abs(actual_count - claimed) > 5:
                    issues.append({
                        "type": "doc_drift",
                        "severity": "low",
                        "message": f"CLAUDE.md claims {claimed}+ scripts but found {actual_count} .py files in execution/",
                        "fix": "Update the script count in .claude/CLAUDE.md",
                    })

    return {
        "checked_at": _now(),
        "total_issues": len(issues),
        "critical": len([i for i in issues if i["severity"] == "critical"]),
        "high": len([i for i in issues if i["severity"] == "high"]),
        "medium": len([i for i in issues if i["severity"] == "medium"]),
        "low": len([i for i in issues if i["severity"] == "low"]),
        "issues": issues,
    }


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_add_project(args):
    try:
        result = add_project(
            args.name, args.business, args.owner, args.priority,
            args.target_date, args.path, args.repo_url, args.description, args.notes,
        )
        print(f"[project_manager] Created project: {result['name']} ({result['business']}, owner: {result['owner']})")
    except sqlite3.IntegrityError:
        print(f"[project_manager] Error: project '{args.name}' already exists.", file=sys.stderr)
        sys.exit(1)


def cli_update_project(args):
    try:
        result = update_project(args.name, args.status, args.priority, args.target_date, args.notes, args.owner)
        print(f"[project_manager] Updated: {result['name']} (status: {result['status']}, health: {result['health_score']})")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_list_projects(args):
    projects = list_projects(args.status, args.business)
    if not projects:
        print("[project_manager] No projects found.")
        return
    for p in projects:
        icon = {"active": "+", "paused": "~", "blocked": "X", "completed": "v", "archived": "-"}.get(p["status"], "?")
        print(f"  [{icon}] {p['name']:<25} {p['business']:<10} score:{p['health_score']:>3} {p['status']:<10} owner:{p['owner']}")


def cli_project_detail(args):
    detail = project_detail(args.name)
    if not detail:
        print(f"[project_manager] Project '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(detail, indent=2, default=str))


def cli_archive_project(args):
    result = archive_project(args.name)
    print(f"[project_manager] Archived: {result['name']}")


def cli_add_milestone(args):
    try:
        result = add_milestone(args.project, args.name, args.due_date, args.expected_days, args.owner)
        print(f"[project_manager] Added milestone: {result['milestone']} (due: {result['due_date']})")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_update_milestone(args):
    try:
        result = update_milestone(args.project, args.milestone, args.status, args.notes)
        print(f"[project_manager] Updated milestone: {result['milestone']} -> {result['status']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_list_milestones(args):
    try:
        milestones = list_milestones(args.project, args.status)
        if not milestones:
            print("[project_manager] No milestones found.")
            return
        for m in milestones:
            icon = {"completed": "+", "in_progress": ">", "blocked": "X", "pending": " ", "skipped": "-"}.get(m["status"], "?")
            print(f"  [{icon}] {m['name']:<30} {m['status']:<12} due: {m['due_date'] or 'none':<12} owner: {m['owner'] or '-'}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_add_task(args):
    try:
        result = add_task(args.project, args.milestone, args.title, args.owner, args.priority, args.due_date, args.estimated_hours)
        print(f"[project_manager] Added task #{result['id']}: {result['title']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_update_task(args):
    try:
        result = update_task(args.id, args.status, args.actual_hours, args.notes, args.owner)
        print(f"[project_manager] Updated task #{result['id']}: {result['title']} -> {result['status']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_my_tasks(args):
    statuses = args.status.split(",") if args.status else None
    tasks = my_tasks(args.agent, statuses)
    if not tasks:
        print(f"[project_manager] No tasks for {args.agent}.")
        return
    for t in tasks:
        icon = {"todo": " ", "in_progress": ">", "review": "?", "done": "+", "blocked": "X"}.get(t["status"], "?")
        print(f"  [{icon}] #{t['id']:<4} [{t['priority']:<8}] {t['title']:<40} {t['project_name']} / {t['milestone_name']}")


def cli_list_tasks(args):
    try:
        tasks = list_tasks(args.project, args.milestone, args.status)
        if not tasks:
            print("[project_manager] No tasks found.")
            return
        for t in tasks:
            icon = {"todo": " ", "in_progress": ">", "review": "?", "done": "+", "blocked": "X"}.get(t["status"], "?")
            print(f"  [{icon}] #{t['id']:<4} [{t['priority']:<8}] {t['title']:<40} {t['milestone_name']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_add_dep(args):
    try:
        result = add_dependency(
            args.source_type, args.source_project, args.source_name,
            args.target_type, args.target_project, args.target_name, args.dep_type,
        )
        print(f"[project_manager] Added dependency: {result['source']} {result['type']} {result['target']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_list_deps(args):
    try:
        deps = list_dependencies(args.project)
        if not deps:
            print("[project_manager] No dependencies found.")
            return
        for d in deps:
            print(f"  #{d['id']}: {d['source_type']}:{d['source_id']} {d['dep_type']} {d['target_type']}:{d['target_id']} [{d['status']}]")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_resolve_dep(args):
    result = resolve_dependency(args.id)
    print(f"[project_manager] Resolved dependency #{result['id']}")


def cli_add_blocker(args):
    try:
        result = add_blocker(args.project, args.title, args.severity, args.milestone, args.description, args.owner)
        print(f"[project_manager] Added blocker: [{result['severity'].upper()}] {result['title']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_resolve_blocker(args):
    try:
        result = resolve_blocker(args.id, args.resolution)
        print(f"[project_manager] Resolved blocker #{result['id']}: {result['resolution']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_list_blockers(args):
    blockers = list_blockers(args.status, args.severity)
    if not blockers:
        print("[project_manager] No blockers found.")
        return
    for b in blockers:
        age = ""
        if b["created_at"]:
            try:
                created = datetime.fromisoformat(b["created_at"])
                age = f" ({(datetime.utcnow() - created).days}d old)"
            except (ValueError, TypeError):
                pass
        print(f"  #{b['id']} [{b['severity'].upper():<8}] {b['project_name']}: {b['title']}{age} [{b['status']}]")


def cli_assign(args):
    try:
        result = assign_agent(args.agent, args.project, args.role, args.allocation)
        print(f"[project_manager] Assigned {result['agent']} to {result['project']} as {result['role']} ({result['allocation']}%)")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_unassign(args):
    try:
        result = unassign_agent(args.agent, args.project)
        print(f"[project_manager] Unassigned {result['agent']} from {result['project']}")
    except ValueError as e:
        print(f"[project_manager] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_workload(args):
    wl = workload(args.agent)
    if not wl:
        print("[project_manager] No assignments found.")
        return
    for a in wl:
        flag = " OVERLOADED" if a["overloaded"] else ""
        print(f"  {a['agent']}: {a['total_allocation']}% allocated{flag}")
        for p in a["projects"]:
            print(f"    - {p['project']} ({p['role']}, {p['allocation']}%)")


def cli_health_report(args):
    print(health_report())


def cli_at_risk(args):
    at_risk = get_at_risk()
    if not at_risk:
        print("[project_manager] No at-risk projects.")
        return
    print(json.dumps(at_risk, indent=2, default=str))


def cli_status_report(args):
    print(status_report(args.project))


def cli_congruence(args):
    result = congruence_check()
    print(f"═══ CONGRUENCE CHECK ═══")
    print(f"Checked at: {result['checked_at']}")
    print(f"Total issues: {result['total_issues']} (critical: {result['critical']}, high: {result['high']}, medium: {result['medium']}, low: {result['low']})")
    if result["issues"]:
        print()
        for issue in result["issues"]:
            print(f"  [{issue['severity'].upper():<8}] {issue['message']}")
            print(f"            Fix: {issue['fix']}")
    else:
        print("\nAll systems congruent.")


def cli_dashboard_data(args):
    result = dashboard_data()
    print(json.dumps(result, indent=2, default=str))


def cli_briefing_feed(args):
    result = briefing_feed()
    print(json.dumps(result, indent=2, default=str))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Project Manager — track projects, milestones, tasks, blockers, dependencies, congruence"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── Project commands ─────────────────────────────────────────────────────
    p = subparsers.add_parser("add-project", help="Create a new project")
    p.add_argument("--name", required=True)
    p.add_argument("--business", required=True, choices=VALID_BUSINESSES)
    p.add_argument("--owner", required=True)
    p.add_argument("--priority", default="medium", choices=VALID_PRIORITIES)
    p.add_argument("--target-date", default=None)
    p.add_argument("--path", default=None)
    p.add_argument("--repo-url", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cli_add_project)

    p = subparsers.add_parser("update-project", help="Update a project")
    p.add_argument("--name", required=True)
    p.add_argument("--status", default=None, choices=VALID_STATUSES)
    p.add_argument("--priority", default=None, choices=VALID_PRIORITIES)
    p.add_argument("--target-date", default=None)
    p.add_argument("--owner", default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cli_update_project)

    p = subparsers.add_parser("list-projects", help="List projects")
    p.add_argument("--status", default=None, choices=VALID_STATUSES)
    p.add_argument("--business", default=None, choices=VALID_BUSINESSES)
    p.set_defaults(func=cli_list_projects)

    p = subparsers.add_parser("project-detail", help="Detailed project view")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cli_project_detail)

    p = subparsers.add_parser("archive-project", help="Archive a project")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cli_archive_project)

    # ── Milestone commands ───────────────────────────────────────────────────
    p = subparsers.add_parser("add-milestone", help="Add a milestone to a project")
    p.add_argument("--project", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--due-date", default=None)
    p.add_argument("--expected-days", type=int, default=14)
    p.add_argument("--owner", default=None)
    p.set_defaults(func=cli_add_milestone)

    p = subparsers.add_parser("update-milestone", help="Update a milestone")
    p.add_argument("--project", required=True)
    p.add_argument("--milestone", required=True)
    p.add_argument("--status", default=None, choices=VALID_MILESTONE_STATUSES)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cli_update_milestone)

    p = subparsers.add_parser("list-milestones", help="List milestones for a project")
    p.add_argument("--project", required=True)
    p.add_argument("--status", default=None, choices=VALID_MILESTONE_STATUSES)
    p.set_defaults(func=cli_list_milestones)

    # ── Task commands ────────────────────────────────────────────────────────
    p = subparsers.add_parser("add-task", help="Add a task")
    p.add_argument("--project", required=True)
    p.add_argument("--milestone", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--owner", default=None)
    p.add_argument("--priority", default="medium", choices=VALID_PRIORITIES)
    p.add_argument("--due-date", default=None)
    p.add_argument("--estimated-hours", type=float, default=None)
    p.set_defaults(func=cli_add_task)

    p = subparsers.add_parser("update-task", help="Update a task")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--status", default=None, choices=VALID_TASK_STATUSES)
    p.add_argument("--actual-hours", type=float, default=None)
    p.add_argument("--owner", default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cli_update_task)

    p = subparsers.add_parser("my-tasks", help="List tasks for an agent")
    p.add_argument("--agent", required=True)
    p.add_argument("--status", default=None, help="Comma-separated statuses")
    p.set_defaults(func=cli_my_tasks)

    p = subparsers.add_parser("list-tasks", help="List tasks for a project")
    p.add_argument("--project", required=True)
    p.add_argument("--milestone", default=None)
    p.add_argument("--status", default=None, choices=VALID_TASK_STATUSES)
    p.set_defaults(func=cli_list_tasks)

    # ── Dependency commands ──────────────────────────────────────────────────
    p = subparsers.add_parser("add-dep", help="Add a dependency")
    p.add_argument("--source-type", required=True, choices=["project", "milestone", "task"])
    p.add_argument("--source-project", required=True)
    p.add_argument("--source-name", required=True)
    p.add_argument("--target-type", required=True, choices=["project", "milestone", "task"])
    p.add_argument("--target-project", required=True)
    p.add_argument("--target-name", required=True)
    p.add_argument("--dep-type", default="blocks", choices=["blocks", "depends_on", "related"])
    p.set_defaults(func=cli_add_dep)

    p = subparsers.add_parser("list-deps", help="List dependencies for a project")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cli_list_deps)

    p = subparsers.add_parser("resolve-dep", help="Resolve a dependency")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=cli_resolve_dep)

    # ── Blocker commands ─────────────────────────────────────────────────────
    p = subparsers.add_parser("add-blocker", help="Add a blocker")
    p.add_argument("--project", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--severity", default="medium", choices=VALID_SEVERITIES)
    p.add_argument("--milestone", default=None)
    p.add_argument("--description", default=None)
    p.add_argument("--owner", default=None)
    p.set_defaults(func=cli_add_blocker)

    p = subparsers.add_parser("resolve-blocker", help="Resolve a blocker")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--resolution", required=True)
    p.set_defaults(func=cli_resolve_blocker)

    p = subparsers.add_parser("list-blockers", help="List blockers")
    p.add_argument("--status", default=None, choices=["open", "escalated", "resolved"])
    p.add_argument("--severity", default=None, help="Comma-separated severities")
    p.set_defaults(func=cli_list_blockers)

    # ── Team commands ────────────────────────────────────────────────────────
    p = subparsers.add_parser("assign", help="Assign an agent to a project")
    p.add_argument("--agent", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--role", default="contributor", choices=VALID_ROLES)
    p.add_argument("--allocation", type=int, default=100)
    p.set_defaults(func=cli_assign)

    p = subparsers.add_parser("unassign", help="Unassign an agent")
    p.add_argument("--agent", required=True)
    p.add_argument("--project", required=True)
    p.set_defaults(func=cli_unassign)

    p = subparsers.add_parser("workload", help="Show agent workload")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cli_workload)

    # ── Reporting commands ───────────────────────────────────────────────────
    p = subparsers.add_parser("health-report", help="All projects health report")
    p.set_defaults(func=cli_health_report)

    p = subparsers.add_parser("at-risk", help="List at-risk projects")
    p.set_defaults(func=cli_at_risk)

    p = subparsers.add_parser("status-report", help="Status report")
    p.add_argument("--project", default=None)
    p.set_defaults(func=cli_status_report)

    p = subparsers.add_parser("congruence", help="Run system congruence check")
    p.set_defaults(func=cli_congruence)

    p = subparsers.add_parser("dashboard-data", help="JSON for web dashboard")
    p.set_defaults(func=cli_dashboard_data)

    p = subparsers.add_parser("briefing-feed", help="JSON for morning briefing")
    p.set_defaults(func=cli_briefing_feed)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
