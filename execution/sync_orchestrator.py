#!/usr/bin/env python3
"""
sync_orchestrator.py — Unified sync engine for all nomad-nebula ↔ SaaS data flows.

Bridges:
  1. Leads: nomad-nebula scraped leads → 247growth.org contacts
  2. Meta Ads: ad performance metrics → 247growth.org ad_metrics
  3. Students: bidirectional sync with 247profits.org (delegates to student_saas_sync.py)
  4. Testimonials: local testimonial DB → 247profits.org
  5. CSM → Sales Manager: churn alerts → 247growth.org activity_log
  6. Discord engagement → 247profits.org engagement signals

CLI:
    python execution/sync_orchestrator.py all                # Full sync everything
    python execution/sync_orchestrator.py leads              # Push scraped leads → 247growth
    python execution/sync_orchestrator.py ads [--days 7]     # Push ad metrics → 247growth
    python execution/sync_orchestrator.py students           # Bidirectional student sync
    python execution/sync_orchestrator.py testimonials       # Push testimonials → 247profits
    python execution/sync_orchestrator.py churn-alerts       # Push churn signals → 247growth
    python execution/sync_orchestrator.py discord            # Push Discord engagement → 247profits
    python execution/sync_orchestrator.py status             # Show sync health across all bridges
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
COACHING_DB = TMP_DIR / "coaching" / "students.db"
DISCORD_DB = TMP_DIR / "discord" / "discord_bot.db"
SOURCING_DB = TMP_DIR / "sourcing" / "results.db"

# Import sibling modules
sys.path.insert(0, str(PROJECT_ROOT))


def _get_dashboard_client():
    """Lazy import to avoid circular deps."""
    from execution.dashboard_client import DashboardClient
    return DashboardClient()


def _get_student_supabase():
    """Get 247profits.org Supabase credentials."""
    import requests
    url = os.getenv("STUDENT_SAAS_SUPABASE_URL", "")
    key = os.getenv("STUDENT_SAAS_SUPABASE_KEY", "")
    if not url or not key:
        url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return url, key


def _student_supabase_upsert(table: str, data: Any) -> Optional[Any]:
    """Upsert to 247profits.org Supabase."""
    import requests
    url, key = _get_student_supabase()
    if not url or not key:
        return None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    try:
        resp = requests.post(f"{url}/rest/v1/{table}", headers=headers, json=data, timeout=15)
        if resp.status_code in (200, 201):
            return resp.json()
        print(f"  [sync] Upsert {table}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  [sync] Upsert {table} failed: {e}", file=sys.stderr)
    return None


# ── Bridge 1: Leads → 247growth ─────────────────────────────────────────────
# DISABLED: GHL is the CRM for agency leads. We scrape hundreds of thousands
# of leads — only contacts already in the GHL sales process (synced via Lead
# Center) should appear in 247growth. Never push raw scraped CSVs.

def sync_leads() -> Dict:
    """DISABLED — GHL is the CRM for scraped leads, not 247growth."""
    print("[sync:leads] SKIPPED — leads use GHL as CRM, not 247growth. Only Lead Center contacts sync via GHL.")
    return {"total_found": 0, "pushed": 0, "skipped": 0, "errors": 0, "note": "disabled"}

def _sync_leads_UNUSED() -> Dict:
    """Push scraped leads from .tmp/ CSVs to 247growth.org contacts table. UNUSED."""
    client = _get_dashboard_client()
    results = {"total_found": 0, "pushed": 0, "skipped": 0, "errors": 0}

    # Find all lead CSVs in .tmp/
    csv_files = sorted(glob.glob(str(TMP_DIR / "*.csv")))
    csv_files += sorted(glob.glob(str(TMP_DIR / "leads" / "*.csv")))

    if not csv_files:
        print("[sync:leads] No CSV files found in .tmp/")
        return results

    all_leads = []
    for csv_file in csv_files:
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Normalize field names (different scrapers use different names)
                    lead = {
                        "full_name": row.get("name") or row.get("full_name") or row.get("business_name", ""),
                        "email": row.get("email") or row.get("Email", ""),
                        "phone": row.get("phone") or row.get("Phone", ""),
                        "company": row.get("business_name") or row.get("company", ""),
                        "website": row.get("website") or row.get("Website", ""),
                        "source": f"nomad-nebula:{Path(csv_file).stem}",
                        "offer": "coaching",  # Default — can override
                        "notes": row.get("address") or row.get("category", ""),
                    }
                    if lead["email"] or lead["phone"]:
                        all_leads.append(lead)
        except Exception as e:
            print(f"  [sync:leads] Error reading {csv_file}: {e}", file=sys.stderr)
            results["errors"] += 1

    results["total_found"] = len(all_leads)

    if all_leads:
        pushed = client.push_leads(all_leads)
        results["pushed"] = len(pushed)
        results["skipped"] = len(all_leads) - len(pushed)

    print(f"[sync:leads] Found {results['total_found']} leads in {len(csv_files)} CSVs → Pushed {results['pushed']} to 247growth")
    return results


# ── Bridge 2: Meta Ads → 247growth ──────────────────────────────────────────

def sync_ads(days: int = 7) -> Dict:
    """Pull Meta Ads metrics and push to 247growth ad_metrics table."""
    results = {"campaigns": 0, "pushed": 0, "errors": 0}

    try:
        from execution.meta_ads_client import get_campaigns, get_accounts, DEFAULT_ACCOUNT
    except ImportError:
        print("[sync:ads] Error: meta_ads_client not importable", file=sys.stderr)
        return results

    client = _get_dashboard_client()

    # Get all accounts
    accounts = []
    try:
        accts = get_accounts()
        accounts = [a["id"] for a in accts]
    except Exception as e:
        print(f"  [sync:ads] Error fetching accounts: {e}", file=sys.stderr)
        if DEFAULT_ACCOUNT:
            accounts = [DEFAULT_ACCOUNT]

    if not accounts:
        print("[sync:ads] No ad accounts found")
        return results

    all_metrics = []
    for account_id in accounts:
        try:
            campaigns = get_campaigns(account_id, days=days)
            results["campaigns"] += len(campaigns)

            for c in campaigns:
                insights = c.get("insights", {}).get("data", [])
                if not insights:
                    continue
                ins = insights[0]  # Most recent period

                # Extract conversions from actions
                conversions = 0
                for action in (ins.get("actions") or []):
                    if action.get("action_type") in ("purchase", "lead", "complete_registration"):
                        conversions += int(action.get("value", 0))

                all_metrics.append({
                    "campaign_name": c.get("name", ""),
                    "platform": "meta",
                    "spend": ins.get("spend", 0),
                    "impressions": ins.get("impressions", 0),
                    "clicks": ins.get("clicks", 0),
                    "ctr": ins.get("ctr", 0),
                    "cpm": ins.get("cpm", 0),
                    "conversions": conversions,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "account_id": account_id,
                })
        except Exception as e:
            print(f"  [sync:ads] Error fetching campaigns for {account_id}: {e}", file=sys.stderr)
            results["errors"] += 1

    if all_metrics:
        result = client.push_ad_metrics(all_metrics)
        if result:
            results["pushed"] = len(all_metrics)
        else:
            results["note"] = "ad_metrics table may not exist in 247growth Supabase — create it to enable sync"

    print(f"[sync:ads] {results['campaigns']} campaigns across {len(accounts)} accounts → Pushed {results['pushed']} metric rows to 247growth")
    if results.get("note"):
        print(f"  Note: {results['note']}")
    return results


# ── Bridge 3: Students (delegates to student_saas_sync.py) ──────────────────

def sync_students() -> Dict:
    """Run full bidirectional student sync with 247profits.org."""
    try:
        from execution.student_saas_sync import full_sync
        return full_sync()
    except ImportError:
        print("[sync:students] Error: student_saas_sync not importable", file=sys.stderr)
        return {"pushed": 0, "pulled": 0}


# ── Bridge 4: Testimonials → 247profits ─────────────────────────────────────

def sync_testimonials() -> Dict:
    """Push testimonials from local coaching DB to 247profits.org."""
    results = {"found": 0, "pushed": 0}

    if not COACHING_DB.exists():
        print("[sync:testimonials] Coaching DB not found")
        return results

    conn = sqlite3.connect(str(COACHING_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Check if testimonials table exists
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        if "testimonials" not in tables:
            print("[sync:testimonials] No testimonials table in coaching DB")
            return results

        testimonials = conn.execute("""
            SELECT t.*, s.name as student_name, s.email
            FROM testimonials t
            LEFT JOIN students s ON t.student_id = s.id
            WHERE t.status IN ('approved', 'collected', 'received')
            ORDER BY t.requested_at DESC
            LIMIT 100
        """).fetchall()

        results["found"] = len(testimonials)

        for t in testimonials:
            row = {
                "action": "testimonial_collected",
                "entity_type": "testimonial",
                "entity_id": str(t["id"]),
                "details": json.dumps({
                    "student_name": t["student_name"] or "Anonymous",
                    "type": t.get("type", "text"),
                    "content": t.get("content", ""),
                    "milestone": t.get("milestone", ""),
                    "collected_at": t["received_at"] or t["requested_at"],
                    "synced_at": datetime.utcnow().isoformat(),
                }),
            }
            result = _student_supabase_upsert("activity_log", row)
            if result:
                results["pushed"] += 1

        print(f"[sync:testimonials] Found {results['found']} testimonials → Pushed {results['pushed']} to 247profits")
    finally:
        conn.close()

    return results


# ── Bridge 5: CSM Churn Alerts → 247profits ─────────────────────────────────

def sync_churn_alerts() -> Dict:
    """Push at-risk and churning student alerts to 247profits for student dashboard."""
    results = {"alerts_found": 0, "pushed": 0}

    if not COACHING_DB.exists():
        print("[sync:churn] Coaching DB not found")
        return results

    conn = sqlite3.connect(str(COACHING_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Get at-risk students with recent health snapshots
        at_risk = conn.execute("""
            SELECT s.id, s.name, s.email, s.current_milestone, s.status,
                   h.score as health_score, h.risk_level
            FROM students s
            JOIN health_snapshots h ON h.student_id = s.id
            WHERE h.date = (SELECT MAX(date) FROM health_snapshots WHERE student_id = s.id)
            AND (h.risk_level IN ('high', 'critical') OR s.status = 'at_risk')
            ORDER BY h.score ASC
        """).fetchall()

        # Get recent churn events
        churn_events = conn.execute("""
            SELECT ce.*, s.name as student_name, s.email
            FROM churn_events ce
            JOIN students s ON ce.student_id = s.id
            WHERE ce.date >= date('now', '-7 days')
            ORDER BY ce.date DESC
        """).fetchall()

        alerts = []

        for s in at_risk:
            alerts.append({
                "student_id": str(s["id"]),
                "student_name": s["name"],
                "risk_level": s["risk_level"],
                "health_score": s["health_score"],
                "reason": f"At-risk: {s['risk_level']} risk, score {s['health_score']}, milestone: {s['current_milestone']}",
                "recommended_action": _recommend_action(s["risk_level"], s["current_milestone"]),
            })

        for ce in churn_events:
            reason = ce["reason_detail"] if ce["reason_detail"] else ce["reason_category"]
            alerts.append({
                "student_id": str(ce["student_id"]),
                "student_name": ce["student_name"],
                "risk_level": "churned",
                "health_score": 0,
                "reason": f"Churned: {reason}",
                "recommended_action": "Win-back sequence. Check exit interview data.",
            })

        results["alerts_found"] = len(alerts)

        for alert in alerts:
            row = {
                "action": "csm_churn_alert",
                "entity_type": "student",
                "entity_id": alert["student_id"],
                "details": json.dumps({
                    "student_name": alert["student_name"],
                    "risk_level": alert["risk_level"],
                    "health_score": alert["health_score"],
                    "reason": alert["reason"],
                    "recommended_action": alert["recommended_action"],
                    "synced_at": datetime.utcnow().isoformat(),
                }),
            }
            result = _student_supabase_upsert("activity_log", row)
            if result:
                results["pushed"] += 1

        print(f"[sync:churn] {len(at_risk)} at-risk + {len(churn_events)} churn events → Pushed {results['pushed']} alerts to 247profits")
    finally:
        conn.close()

    return results


def _recommend_action(risk_level: str, milestone: str) -> str:
    """Generate recommended action based on risk level and milestone."""
    if risk_level == "critical":
        return "Sabbo personal outreach. Schedule 1:1 call within 24 hours."
    elif risk_level == "high":
        if milestone in ("enrolled", "niche_selected"):
            return "Send targeted resource bundle for current milestone. DM check-in."
        elif milestone in ("product_selected", "supplier_contacted"):
            return "Connect with accountability pod. Share similar success story."
        else:
            return "Review recent engagement signals. Send encouragement + specific next step."
    return "Monitor. Send weekly check-in."


# ── Bridge 6: Discord Engagement → 247profits ───────────────────────────────

def sync_discord_engagement() -> Dict:
    """Push Discord engagement signals to 247profits.org for student visibility."""
    results = {"signals_found": 0, "pushed": 0}

    if not COACHING_DB.exists():
        print("[sync:discord] Coaching DB not found")
        return results

    conn = sqlite3.connect(str(COACHING_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Get recent Discord engagement signals
        signals = conn.execute("""
            SELECT es.*, s.name as student_name, s.email
            FROM engagement_signals es
            JOIN students s ON es.student_id = s.id
            WHERE es.channel = 'discord'
            AND es.date >= date('now', '-7 days')
            ORDER BY es.date DESC
        """).fetchall()

        results["signals_found"] = len(signals)

        # Group by student for batch push
        by_student = {}
        for sig in signals:
            sid = sig["student_id"]
            if sid not in by_student:
                by_student[sid] = {
                    "student_name": sig["student_name"],
                    "email": sig["email"],
                    "signals": [],
                }
            by_student[sid]["signals"].append({
                "type": sig["signal_type"],
                "value": sig["value"],
                "date": sig["date"],
                "notes": sig["notes"] if "notes" in sig.keys() else "",
            })

        for sid, data in by_student.items():
            row = {
                "action": "discord_engagement_sync",
                "entity_type": "student",
                "entity_id": str(sid),
                "details": json.dumps({
                    "student_name": data["student_name"],
                    "signal_count": len(data["signals"]),
                    "signals": data["signals"][:20],  # Cap at 20 per student
                    "period": "7d",
                    "synced_at": datetime.utcnow().isoformat(),
                }),
            }
            result = _student_supabase_upsert("activity_log", row)
            if result:
                results["pushed"] += 1

        print(f"[sync:discord] {results['signals_found']} signals for {len(by_student)} students → Pushed {results['pushed']} to 247profits")
    finally:
        conn.close()

    return results


# ── Status Check ─────────────────────────────────────────────────────────────

def sync_status() -> Dict:
    """Check health of all sync bridges."""
    import requests

    status = {}

    # 1. 247growth.org API health
    dashboard_url = os.getenv("DASHBOARD_URL", "https://247growth.org")
    try:
        resp = requests.get(f"{dashboard_url}/api/health", timeout=5)
        status["247growth_api"] = "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    except Exception:
        status["247growth_api"] = "UNREACHABLE"

    # 2. 247profits.org Supabase health
    stu_url, stu_key = _get_student_supabase()
    if stu_url and stu_key:
        try:
            headers = {"apikey": stu_key, "Authorization": f"Bearer {stu_key}"}
            resp = requests.get(f"{stu_url}/rest/v1/users?select=id&limit=1", headers=headers, timeout=5)
            status["247profits_supabase"] = "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}"
        except Exception:
            status["247profits_supabase"] = "UNREACHABLE"
    else:
        status["247profits_supabase"] = "NOT CONFIGURED"

    # 3. Local databases
    status["coaching_db"] = "OK" if COACHING_DB.exists() else "MISSING"
    status["discord_db"] = "OK" if DISCORD_DB.exists() else "MISSING"
    status["sourcing_db"] = "OK" if SOURCING_DB.exists() else "MISSING"

    # 4. Lead CSVs available
    csv_count = len(glob.glob(str(TMP_DIR / "*.csv"))) + len(glob.glob(str(TMP_DIR / "leads" / "*.csv")))
    status["lead_csvs"] = f"{csv_count} files"

    # 5. Meta Ads token
    status["meta_ads_token"] = "SET" if os.getenv("META_ACCESS_TOKEN") else "MISSING"

    # 6. Flask app
    try:
        resp = requests.get("http://localhost:5050/api/health", timeout=3)
        status["flask_app"] = "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    except Exception:
        status["flask_app"] = "DOWN"

    # 7. Student counts
    if COACHING_DB.exists():
        conn = sqlite3.connect(str(COACHING_DB))
        try:
            total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM students WHERE status='active'").fetchone()[0]
            at_risk = conn.execute("SELECT COUNT(*) FROM students WHERE status='at_risk'").fetchone()[0]
            status["students"] = f"{total} total, {active} active, {at_risk} at-risk"
        except Exception:
            status["students"] = "DB ERROR"
        finally:
            conn.close()

    # Print status
    print("═══ SYNC BRIDGE STATUS ═══")
    print()
    for key, val in status.items():
        indicator = "OK" if val == "OK" or val.startswith("SET") else "!!"
        label = key.replace("_", " ").title()
        print(f"  [{indicator}] {label}: {val}")
    print()

    return status


# ── Full Sync ────────────────────────────────────────────────────────────────

def sync_all() -> Dict:
    """Run all sync bridges."""
    print("═══ FULL SYNC — ALL BRIDGES ═══")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = {}

    # Bridge 1: Leads
    print("── Bridge 1: Leads → 247growth ──")
    results["leads"] = sync_leads()
    print()

    # Bridge 2: Meta Ads
    print("── Bridge 2: Meta Ads → 247growth ──")
    try:
        results["ads"] = sync_ads(days=7)
    except Exception as e:
        print(f"  [sync:ads] Skipped: {e}")
        results["ads"] = {"error": str(e)}
    print()

    # Bridge 3: Students (bidirectional)
    print("── Bridge 3: Students ↔ 247profits ──")
    results["students"] = sync_students()
    print()

    # Bridge 4: Testimonials
    print("── Bridge 4: Testimonials → 247profits ──")
    results["testimonials"] = sync_testimonials()
    print()

    # Bridge 5: Churn Alerts → Sales Manager
    print("── Bridge 5: Churn Alerts → 247growth ──")
    results["churn_alerts"] = sync_churn_alerts()
    print()

    # Bridge 6: Discord Engagement
    print("── Bridge 6: Discord Engagement → 247profits ──")
    results["discord"] = sync_discord_engagement()
    print()

    print("═══ SYNC COMPLETE ═══")
    print(json.dumps(results, indent=2, default=str))
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified sync orchestrator — all nomad-nebula ↔ SaaS data flows"
    )
    sub = parser.add_subparsers(dest="command", help="Sync bridge to run")

    sub.add_parser("all", help="Run all sync bridges")
    sub.add_parser("leads", help="Push scraped leads → 247growth contacts")

    ads_p = sub.add_parser("ads", help="Push Meta Ads metrics → 247growth")
    ads_p.add_argument("--days", type=int, default=7, help="Days of ad data to sync")

    sub.add_parser("students", help="Bidirectional student sync with 247profits")
    sub.add_parser("testimonials", help="Push testimonials → 247profits")
    sub.add_parser("churn-alerts", help="Push churn alerts → 247growth")
    sub.add_parser("discord", help="Push Discord engagement → 247profits")
    sub.add_parser("status", help="Show sync health across all bridges")

    args = parser.parse_args()

    commands = {
        "all": sync_all,
        "leads": sync_leads,
        "ads": lambda: sync_ads(days=args.days if hasattr(args, "days") else 7),
        "students": sync_students,
        "testimonials": sync_testimonials,
        "churn-alerts": sync_churn_alerts,
        "discord": sync_discord_engagement,
        "status": sync_status,
    }

    func = commands.get(args.command)
    if func:
        func()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
