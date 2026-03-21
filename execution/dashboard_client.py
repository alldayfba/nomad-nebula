#!/usr/bin/env python3
"""
dashboard_client.py — Bridge between nomad-nebula and the 247growth.org dashboard.

Primary data source for the Sales Manager agent. Wraps all 247growth API
endpoints and falls back to direct Supabase REST queries when needed.

Usage (CLI):
    python execution/dashboard_client.py kpi                     # MTD snapshot
    python execution/dashboard_client.py team                    # Team performance
    python execution/dashboard_client.py funnel [--offer X]      # Sales funnel
    python execution/dashboard_client.py scorecard               # Weekly scorecard
    python execution/dashboard_client.py report                  # Full daily report
    python execution/dashboard_client.py commissions             # Commission calc
    python execution/dashboard_client.py submissions [--role X]  # EOD submissions
    python execution/dashboard_client.py contacts [--query X]    # Search contacts
    python execution/dashboard_client.py calls                   # Upcoming calls
    python execution/dashboard_client.py health                  # Data health check
    python execution/dashboard_client.py noshow                  # No-show analysis
    python execution/dashboard_client.py objections              # Objection data
    python execution/dashboard_client.py roster                  # Team roster
    python execution/dashboard_client.py journey --contact-id X  # Contact journey
    python execution/dashboard_client.py utm                     # Lead source attribution

Usage (import):
    from execution.dashboard_client import DashboardClient
    client = DashboardClient()
    kpi = client.get_kpi_snapshot()

Env vars:
    DASHBOARD_URL             — Base URL (default: https://247growth.org)
    NEXT_PUBLIC_SUPABASE_URL  — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY — Service role key (bypasses RLS)
    DASHBOARD_ORG_ID          — Organization ID for multi-tenant queries
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class DashboardClient:
    """Client for the 247growth.org dashboard API + Supabase fallback."""

    def __init__(self):
        self.dashboard_url = os.getenv("DASHBOARD_URL", "https://247growth.org").rstrip("/")
        self.supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.org_id = os.getenv("DASHBOARD_ORG_ID", "")
        self.ghl_api_key = os.getenv("GHL_API_KEY", "")
        self.ghl_base_url = "https://rest.gohighlevel.com/v1"
        self.timeout = 15

    # ── Internal helpers ─────────────────────────────────────────────────

    def _ghl_get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        """GET from GoHighLevel v1 API. Returns parsed JSON or None."""
        if not self.ghl_api_key:
            return None
        url = f"{self.ghl_base_url}{path}"
        try:
            resp = requests.get(url, headers={"Authorization": f"Bearer {self.ghl_api_key}"},
                                params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            print(f"  [dashboard] GHL {path} returned {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  [dashboard] GHL {path} failed: {e}", file=sys.stderr)
        return None

    def get_ghl_contacts(self, limit: int = 20, query: Optional[str] = None) -> Optional[List]:
        """Search GHL contacts — live CRM data."""
        params = {"limit": limit}
        if query:
            params["query"] = query
        data = self._ghl_get("/contacts/", params)
        if data and "contacts" in data:
            return data["contacts"]
        return None

    def get_ghl_pipelines(self) -> Optional[List]:
        """Get all GHL pipeline stages + opportunities."""
        data = self._ghl_get("/pipelines/")
        if data and "pipelines" in data:
            return data["pipelines"]
        return None

    def get_ghl_opportunities(self, pipeline_id: Optional[str] = None, limit: int = 20) -> Optional[List]:
        """Get GHL opportunities (deals in pipeline)."""
        params = {"limit": limit}
        if pipeline_id:
            params["pipelineId"] = pipeline_id
        data = self._ghl_get("/pipelines/opportunities/", params)  # v1 endpoint
        # v1 opportunities endpoint is at /opportunities/search
        if not data:
            data = self._ghl_get("/opportunities/search", params)
        if data and "opportunities" in data:
            return data["opportunities"]
        return data if isinstance(data, list) else None

    def get_ghl_calendars(self) -> Optional[List]:
        """Get GHL calendars + upcoming appointments."""
        data = self._ghl_get("/calendars/")
        if data and "calendars" in data:
            return data["calendars"]
        return None

    def get_ghl_appointments(self, calendar_id: Optional[str] = None,
                             start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> Optional[List]:
        """Get GHL calendar appointments."""
        params = {}
        if calendar_id:
            params["calendarId"] = calendar_id
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        data = self._ghl_get("/appointments/", params)
        if data and "appointments" in data:
            return data["appointments"]
        return data if isinstance(data, list) else None

    def get_ghl_contact_notes(self, contact_id: str) -> Optional[List]:
        """Get notes for a GHL contact (AI call summaries, manual notes)."""
        data = self._ghl_get(f"/contacts/{contact_id}/notes")
        if data and "notes" in data:
            return data["notes"]
        return data if isinstance(data, list) else None

    def search_ghl_contacts_by_name(self, name: str, limit: int = 5) -> Optional[List]:
        """Search GHL contacts by name/email/phone."""
        data = self._ghl_get("/contacts/", {"query": name, "limit": limit})
        if data and "contacts" in data:
            return data["contacts"]
        return None

    def _get_ghl_todays_appointments(self, today: str) -> List[Dict]:
        """Get today's GHL appointments by checking contacts in 'Sales Call Booked' stage."""
        if not self.ghl_api_key:
            return []
        results = []
        # Get opportunities in Sales Call Booked stage
        pipeline_id = "sFxWPIwC0fTGZBNRO0Lf"
        stage_id = "694954ce-8782-4165-9e07-d8d3b57d5fc3"
        data = self._ghl_get(f"/pipelines/{pipeline_id}/opportunities",
                             {"stageId": stage_id, "limit": 50})
        if not data:
            return []
        opps = data.get("opportunities", []) if isinstance(data, dict) else data
        if not isinstance(opps, list):
            return []
        for opp in opps:
            contact = opp.get("contact", {})
            contact_id = contact.get("id") or opp.get("contactId", "")
            if not contact_id:
                continue
            apt_data = self._ghl_get(f"/contacts/{contact_id}/appointments")
            if not apt_data:
                continue
            apts = apt_data.get("events", apt_data.get("appointments", []))
            if not isinstance(apts, list):
                continue
            for apt in apts:
                start = apt.get("startTime", "")
                if start.startswith(today):
                    results.append({
                        "contact_name": opp.get("name", "Unknown"),
                        "start_time": start,
                        "scheduled_for": start,
                        "offer": "",
                        "status": apt.get("appointmentStatus", "confirmed"),
                        "source": "ghl",
                        "closer": apt.get("title", ""),
                    })
        return results

    def _api_get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """GET from 247growth API. Returns parsed JSON or None on failure."""
        url = f"{self.dashboard_url}/api{path}"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            print(f"  [dashboard] API {path} returned {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  [dashboard] API {path} failed: {e}", file=sys.stderr)
        return None

    def _supabase_query(self, table: str, params: Optional[Dict] = None) -> Optional[List]:
        """Direct Supabase REST query. Fallback when API is unavailable."""
        if not self.supabase_url or not self.supabase_key:
            print("  [dashboard] Missing SUPABASE_URL or SERVICE_ROLE_KEY for fallback", file=sys.stderr)
            return None

        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.supabase_url}/rest/v1/{table}"
        query_params = {"select": "*"}
        if self.org_id:
            query_params["organization_id"] = f"eq.{self.org_id}"
        if params:
            query_params.update(params)
        # Allow callers to suppress the org filter by passing organization_id=None
        if query_params.get("organization_id") is None:
            query_params.pop("organization_id", None)

        try:
            resp = requests.get(url, headers=headers, params=query_params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            print(f"  [dashboard] Supabase {table} returned {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  [dashboard] Supabase {table} failed: {e}", file=sys.stderr)
        return None

    @staticmethod
    def _format_currency(amount: Any) -> str:
        if amount is None:
            return "$0"
        return f"${float(amount):,.0f}"

    @staticmethod
    def _format_pct(value: Any) -> str:
        if value is None:
            return "0%"
        return f"{float(value):.1f}%"

    @staticmethod
    def _rag_status(value: float, green_threshold: float, red_threshold: float) -> str:
        """Return RAG indicator. Green >= green_threshold, Red < red_threshold."""
        if value >= green_threshold:
            return "GREEN"
        elif value >= red_threshold:
            return "AMBER"
        return "RED"

    # ── API methods ──────────────────────────────────────────────────────

    def get_kpi_snapshot(self, period: str = "mtd") -> Optional[Dict]:
        """MTD pipeline metrics, setter stats, closer performance, unit economics."""
        data = self._api_get("/analytics/kpi", {"period": period})
        if data:
            return data
        # Fallback: aggregate from Supabase tables
        return self._fallback_kpi()

    def get_team_performance(self, period: str = "mtd") -> Optional[Dict]:
        """Per-rep performance breakdown."""
        data = self._api_get("/analytics/calls", {"period": period})
        if data:
            return data
        return self._fallback_team_performance()

    def get_funnel_data(self, period: str = "mtd", offer: Optional[str] = None) -> Optional[Dict]:
        """Full funnel: dials -> conversations -> bookings -> shows -> closes."""
        params = {"period": period}
        if offer:
            params["offer"] = offer
        data = self._api_get("/analytics/funnel", params)
        if data:
            return data
        return self._fallback_funnel(offer=offer)

    def get_closer_submissions(self, start: Optional[str] = None, end: Optional[str] = None,
                                member_id: Optional[str] = None) -> Optional[List]:
        """Closer EOD reports."""
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if member_id:
            params["member_id"] = member_id
        data = self._api_get("/submissions/closer", params)
        if data:
            return data if isinstance(data, list) else data.get("data", data.get("submissions", []))
        # Fallback
        supa_params = {}
        if start:
            supa_params["submission_date"] = f"gte.{start}"
        if end:
            supa_params["submission_date"] = f"lte.{end}"
        if member_id:
            supa_params["team_member_id"] = f"eq.{member_id}"
        return self._supabase_query("closer_submissions", supa_params)

    def get_sdr_submissions(self, start: Optional[str] = None, end: Optional[str] = None,
                             member_id: Optional[str] = None) -> Optional[List]:
        """SDR EOD reports."""
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if member_id:
            params["member_id"] = member_id
        data = self._api_get("/submissions/sdr", params)
        if data:
            return data if isinstance(data, list) else data.get("data", data.get("submissions", []))
        supa_params = {}
        if start:
            supa_params["submission_date"] = f"gte.{start}"
        if end:
            supa_params["submission_date"] = f"lte.{end}"
        if member_id:
            supa_params["team_member_id"] = f"eq.{member_id}"
        return self._supabase_query("sdr_submissions", supa_params)

    def get_commissions(self) -> Optional[Dict]:
        """MTD commission tiers, per-rep breakdown."""
        data = self._api_get("/commissions")
        if data:
            return data
        return self._fallback_commissions()

    def get_quotas(self) -> Optional[Dict]:
        """Team quotas vs actual."""
        data = self._api_get("/quotas")
        if data:
            return data
        return self._fallback_quotas()

    def get_upcoming_calls(self) -> Optional[List]:
        """Scheduled calls from Calendly + GHL + manual, with contact names resolved."""
        data = self._api_get("/upcoming-calls")
        if data:
            return data if isinstance(data, list) else data.get("calls", [])
        # Fallback — join sales_calls_booked with contacts to get names
        calls = self._supabase_query("sales_calls_booked", {
            "status": "in.(scheduled,rescheduled)",
            "scheduled_for": f"gte.{datetime.now().strftime('%Y-%m-%d')}",
            "order": "scheduled_for.asc",
            "select": "id,contact_id,scheduled_for,offer,status,closer_id",
        })
        if not calls:
            return calls
        # Resolve contact names in a single query
        contact_ids = list({c["contact_id"] for c in calls if c.get("contact_id")})
        contacts_by_id: Dict[str, str] = {}
        if contact_ids:
            id_filter = "in.(" + ",".join(contact_ids) + ")"
            rows = self._supabase_query("contacts", {
                "id": id_filter,
                "select": "id,full_name,email",
                "organization_id": None,  # contacts table uses different org filter
            })
            if rows:
                contacts_by_id = {r["id"]: r.get("full_name") or r.get("email") or r["id"] for r in rows}
        for call in calls:
            cid = call.get("contact_id")
            call["contact_name"] = contacts_by_id.get(cid, "Unknown") if cid else "Unknown"
            call["start_time"] = call.get("scheduled_for", "")
        # Also include rescheduled calls inferred from EOC reports (showed_not_closed, last 48h)
        yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        eoc_reschedules = self._supabase_query("eoc_reports", {
            "outcome": "eq.showed_not_closed",
            "report_date": f"gte.{yesterday}",
            "select": "contact_id,team_member_id,offer,report_date,notes",
        })
        if eoc_reschedules:
            # Get contacts already in the calls list to avoid duplicates
            existing_cids = {c.get("contact_id") for c in (calls or [])}
            # Resolve closer names
            closer_ids = list({e["team_member_id"] for e in eoc_reschedules if e.get("team_member_id")})
            closers_by_id = {}
            if closer_ids:
                members = self._supabase_query("team_members", {
                    "id": f"in.({','.join(closer_ids)})",
                    "select": "id,full_name",
                })
                if members:
                    closers_by_id = {m["id"]: m.get("full_name", "Unknown") for m in members}

            for eoc in eoc_reschedules:
                cid = eoc.get("contact_id")
                if not cid or cid in existing_cids:
                    continue
                # Resolve contact name (may already be in contacts_by_id from above)
                cname = contacts_by_id.get(cid)
                if not cname:
                    c_rows = self._supabase_query("contacts", {
                        "id": f"eq.{cid}",
                        "select": "id,full_name,email",
                        "organization_id": None,
                    })
                    if c_rows:
                        cname = c_rows[0].get("full_name") or c_rows[0].get("email") or cid

                # Reschedule date = day after EOC
                report_date = eoc.get("report_date", "")
                try:
                    rd = datetime.strptime(report_date, "%Y-%m-%d")
                    sched_date = (rd + timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")
                except ValueError:
                    sched_date = ""

                closer_name = closers_by_id.get(eoc.get("team_member_id", ""), "")
                if calls is None:
                    calls = []
                calls.append({
                    "contact_id": cid,
                    "contact_name": cname or "Unknown",
                    "start_time": sched_date,
                    "scheduled_for": sched_date,
                    "offer": eoc.get("offer", ""),
                    "status": "rescheduled",
                    "source": "eoc_reschedule",
                    "closer": closer_name,
                })
                existing_cids.add(cid)

        # Also merge GHL appointments for today (source of truth for Calendly/manual bookings)
        today = datetime.now().strftime("%Y-%m-%d")
        ghl_contacts_with_apts = self._get_ghl_todays_appointments(today)
        if ghl_contacts_with_apts:
            existing_names = {c.get("contact_name", "").lower() for c in (calls or [])}
            if calls is None:
                calls = []
            for apt in ghl_contacts_with_apts:
                # Deduplicate by name (GHL contacts may not have Supabase contact_ids)
                apt_name = apt.get("contact_name", "").lower()
                if apt_name and apt_name != "unknown" and apt_name not in existing_names:
                    calls.append(apt)
                    existing_names.add(apt_name)

        # Sort by start_time
        if calls:
            calls.sort(key=lambda c: c.get("start_time", "") or "")

        return calls

    def get_recent_calls(self, days: int = 30) -> Optional[List]:
        """Recent completed calls with contact names resolved."""
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        calls = self._supabase_query("sales_calls_booked", {
            "scheduled_for": f"gte.{since}",
            "order": "scheduled_for.desc",
            "limit": "50",
            "select": "id,contact_id,scheduled_for,offer,status,closer_id",
        })
        if not calls:
            return calls
        contact_ids = list({c["contact_id"] for c in calls if c.get("contact_id")})
        contacts_by_id: Dict[str, str] = {}
        if contact_ids:
            id_filter = "in.(" + ",".join(contact_ids) + ")"
            rows = self._supabase_query("contacts", {
                "id": id_filter,
                "select": "id,full_name,email",
                "organization_id": None,
            })
            if rows:
                contacts_by_id = {r["id"]: r.get("full_name") or r.get("email") or r["id"] for r in rows}
        for call in calls:
            cid = call.get("contact_id")
            call["contact_name"] = contacts_by_id.get(cid, "Unknown") if cid else "Unknown"
            call["start_time"] = call.get("scheduled_for", "")
        return calls

    def get_contact_journey(self, contact_id: str) -> Optional[Dict]:
        """Full contact journey (calls, EOD, GHL logs, payments)."""
        return self._api_get(f"/contacts/{contact_id}/journey")

    def get_lead_sources(self, period: str = "mtd") -> Optional[Dict]:
        """UTM attribution + ROAS."""
        data = self._api_get("/analytics/utm", {"period": period})
        if data:
            return data
        return self._fallback_lead_sources()

    def get_data_health(self) -> Optional[Dict]:
        """Submission compliance, data gaps."""
        data = self._api_get("/analytics/data-health")
        if data:
            return data
        return self._fallback_data_health()

    def get_noshow_analysis(self) -> Optional[Dict]:
        """No-show patterns + prevention metrics."""
        data = self._api_get("/analytics/noshow")
        if data:
            return data
        return self._fallback_noshow_analysis()

    def get_objection_data(self) -> Optional[Dict]:
        """Objection frequency + resolution rates."""
        data = self._api_get("/analytics/objections")
        if data:
            return data
        return self._fallback_objection_data()

    def get_team_roster(self) -> Optional[List]:
        """Active team members with roles + targets."""
        data = self._api_get("/team")
        if data:
            return data if isinstance(data, list) else data.get("members", [])
        return self._supabase_query("team_members", {"is_active": "eq.true"})

    def get_insights(self) -> Optional[Dict]:
        """AI-generated insights (revenue pace, close rate, team leaders)."""
        data = self._api_get("/analytics/insights")
        if data:
            return data
        return self._fallback_insights()

    def get_revenue_metrics(self) -> Optional[Dict]:
        """Revenue analytics (EOC + payment records)."""
        data = self._api_get("/metrics/revenue")
        if data:
            return data
        return self._fallback_revenue_metrics()

    def search_contacts(self, query: str) -> Optional[List]:
        """Search contacts by name/email/phone."""
        data = self._api_get("/contacts", {"q": query})
        if data:
            return data if isinstance(data, list) else data.get("contacts", [])
        return self._fallback_search_contacts(query)

    # ── Write methods (push data TO 247growth) ────────────────────────────

    def _supabase_upsert(self, table: str, data: Any, on_conflict: str = "id") -> Optional[Any]:
        """Upsert rows to Supabase REST API."""
        if not self.supabase_url or not self.supabase_key:
            print("  [dashboard] Missing Supabase creds for write", file=sys.stderr)
            return None
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        try:
            resp = requests.post(
                f"{self.supabase_url}/rest/v1/{table}",
                headers=headers, json=data, timeout=self.timeout,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code == 409:
                # Duplicate key — already exists, treat as success
                return [data] if isinstance(data, dict) else data
            print(f"  [dashboard] Upsert {table}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  [dashboard] Upsert {table} failed: {e}", file=sys.stderr)
        return None

    def push_leads(self, leads: List[Dict]) -> List[Dict]:
        """Push scraped leads to 247growth contacts table.

        Each lead dict should have: full_name, email, phone, source, offer.
        Optional: company, website, address, notes.
        Deduplicates by email.
        """
        pushed = []
        invalid_emails = {"", "N/A", "n/a", "NA", "na", "none", "None", None}
        for lead in leads:
            email = lead.get("email", "")
            phone = lead.get("phone", "")
            # Skip leads with no valid contact info
            if email in invalid_emails and (not phone or phone in invalid_emails):
                continue
            # Clean email
            if email in invalid_emails:
                lead["email"] = None
            contact = {
                "full_name": lead.get("full_name") or lead.get("name", "Unknown"),
                "email": lead.get("email"),
                "phone": lead.get("phone"),
                "source": lead.get("source", "nomad-nebula"),
                "offer": lead.get("offer", "coaching"),
                "status": lead.get("status", "new"),
            }
            if self.org_id:
                contact["organization_id"] = self.org_id
            if lead.get("company"):
                contact["company_name"] = lead["company"]
            if lead.get("website"):
                contact["company_domain"] = lead["website"]
            if lead.get("notes"):
                contact["notes"] = lead["notes"]

            result = self._supabase_upsert("contacts", contact)
            if result:
                pushed.append(contact)
        return pushed

    def push_ad_metrics(self, metrics: List[Dict]) -> Optional[Any]:
        """Push Meta Ads performance metrics to 247growth ad_metrics table.

        Each metric dict: campaign_name, spend, impressions, clicks, ctr, cpm,
                          conversions, date, account_id, platform.
        """
        rows = []
        for m in metrics:
            row = {
                "campaign_name": m.get("campaign_name", ""),
                "platform": m.get("platform", "meta"),
                "spend": float(m.get("spend", 0)),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "ctr": float(m.get("ctr", 0)),
                "cpm": float(m.get("cpm", 0)),
                "conversions": int(m.get("conversions", 0)),
                "date": m.get("date", datetime.now().strftime("%Y-%m-%d")),
                "account_id": m.get("account_id", ""),
            }
            if self.org_id:
                row["organization_id"] = self.org_id
            rows.append(row)
        if rows:
            return self._supabase_upsert("ad_metrics", rows)
        return None

    def push_churn_alert(self, alert: Dict) -> Optional[Any]:
        """Push CSM churn alert to 247growth for Sales Manager visibility.

        Alert dict: student_name, risk_level, health_score, reason, recommended_action.
        """
        row = {
            "action": "csm_churn_alert",
            "entity_type": "student",
            "entity_id": alert.get("student_id", ""),
            "details": json.dumps({
                "student_name": alert.get("student_name", ""),
                "risk_level": alert.get("risk_level", ""),
                "health_score": alert.get("health_score", 0),
                "reason": alert.get("reason", ""),
                "recommended_action": alert.get("recommended_action", ""),
                "synced_at": datetime.now().isoformat(),
            }),
        }
        if self.org_id:
            row["organization_id"] = self.org_id
        return self._supabase_upsert("activity_logs", row)

    # ── Fallback methods (direct Supabase) ───────────────────────────────

    def _fallback_kpi(self) -> Optional[Dict]:
        """Build KPI snapshot from eoc_reports (single source of truth)."""
        today = datetime.now()
        mtd_start = today.replace(day=1).strftime("%Y-%m-%d")

        # eoc_reports is the source of truth — each row = 1 call
        eocs = self._supabase_query("eoc_reports", {
            "report_date": f"gte.{mtd_start}",
            "select": "outcome,revenue_collected",
        })
        sdrs = self._supabase_query("sdr_submissions", {
            "submission_date": f"gte.{mtd_start}",
        })

        if eocs is None:
            return None

        total_calls = len(eocs)
        total_showed = sum(1 for e in eocs if e.get("outcome") in ("showed_closed", "showed_not_closed"))
        total_closed = sum(1 for e in eocs if e.get("outcome") == "showed_closed")
        total_revenue = sum(float(e.get("revenue_collected", 0) or 0) for e in eocs)

        return {
            "source": "eoc_reports",
            "period": "mtd",
            "closer": {
                "calls_taken": total_calls,
                "showed": total_showed,
                "closed": total_closed,
                "revenue_collected": total_revenue,
                "show_rate": (total_showed / total_calls * 100) if total_calls else 0,
                "close_rate": (total_closed / total_showed * 100) if total_showed else 0,
            },
            "sdr": {
                "total_dials": sum(r.get("dials", 0) for r in (sdrs or [])),
                "total_bookings": sum(r.get("bookings", 0) for r in (sdrs or [])),
                "total_conversations": sum(r.get("conversations", 0) for r in (sdrs or [])),
            },
        }

    def _fallback_team_performance(self) -> Optional[Dict]:
        """Build per-rep performance from eoc_reports (single source of truth)."""
        today = datetime.now()
        mtd_start = today.replace(day=1).strftime("%Y-%m-%d")

        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        # eoc_reports is source of truth — each row = 1 call
        eocs = self._supabase_query("eoc_reports", {
            "report_date": f"gte.{mtd_start}",
            "select": "team_member_id,outcome,revenue_collected",
        })

        if members is None or eocs is None:
            return None

        member_map = {m["id"]: m.get("full_name", "Unknown") for m in members}
        by_rep: Dict[str, Dict] = {}
        for e in eocs:
            mid = e.get("team_member_id", "unknown")
            name = member_map.get(mid, mid)
            if name not in by_rep:
                by_rep[name] = {"calls": 0, "showed": 0, "closed": 0, "revenue": 0}
            by_rep[name]["calls"] += 1
            if e.get("outcome") in ("showed_closed", "showed_not_closed"):
                by_rep[name]["showed"] += 1
            if e.get("outcome") == "showed_closed":
                by_rep[name]["closed"] += 1
                by_rep[name]["revenue"] += float(e.get("revenue_collected", 0) or 0)

        reps = []
        for name, stats in by_rep.items():
            reps.append({
                "name": name,
                **stats,
                "show_rate": (stats["showed"] / stats["calls"] * 100) if stats["calls"] else 0,
                "close_rate": (stats["closed"] / stats["showed"] * 100) if stats["showed"] else 0,
            })
        reps.sort(key=lambda x: x["revenue"], reverse=True)

        return {"source": "eoc_reports", "period": "mtd", "reps": reps}

    def _fallback_funnel(self, offer: Optional[str] = None) -> Optional[Dict]:
        """Build funnel data from eoc_reports — group outcomes by type."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        params: Dict[str, str] = {"report_date": f"gte.{mtd_start}"}
        if offer:
            params["offer"] = f"eq.{offer}"
        eoc = self._supabase_query("eoc_reports", params)
        if eoc is None:
            return None

        no_show = sum(1 for r in eoc if r.get("outcome") == "no_show")
        showed_not_closed = sum(1 for r in eoc if r.get("outcome") == "showed_not_closed")
        showed_closed = sum(1 for r in eoc if r.get("outcome") == "showed_closed")
        total = len(eoc)

        # Also pull SDR bookings for top-of-funnel
        sdrs = self._supabase_query("sdr_submissions", {"submission_date": f"gte.{mtd_start}"})
        total_bookings = sum(r.get("bookings", 0) for r in (sdrs or []))
        total_dials = sum(r.get("dials", 0) for r in (sdrs or []))

        # Group by offer
        by_offer: Dict[str, Dict[str, int]] = {}
        for r in eoc:
            o = r.get("offer", "unknown") or "unknown"
            if o not in by_offer:
                by_offer[o] = {"no_show": 0, "showed_not_closed": 0, "showed_closed": 0, "total": 0}
            outcome = r.get("outcome", "")
            if outcome in by_offer[o]:
                by_offer[o][outcome] += 1
            by_offer[o]["total"] += 1

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "dials": total_dials,
            "bookings": total_bookings,
            "total_calls": total,
            "no_show": no_show,
            "showed_not_closed": showed_not_closed,
            "showed_closed": showed_closed,
            "show_rate": ((total - no_show) / total * 100) if total else 0,
            "close_rate": (showed_closed / (total - no_show) * 100) if (total - no_show) else 0,
            "by_offer": by_offer,
        }

    def _fallback_commissions(self) -> Optional[Dict]:
        """Build commission breakdown from eoc_reports + team_members."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        eoc = self._supabase_query("eoc_reports", {
            "report_date": f"gte.{mtd_start}",
            "outcome": "eq.showed_closed",
        })
        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        if eoc is None:
            return None

        member_map = {m["id"]: m.get("full_name", "Unknown") for m in (members or [])}

        # Aggregate revenue per team member
        by_rep: Dict[str, float] = {}
        for r in eoc:
            mid = r.get("team_member_id", "unknown")
            name = member_map.get(mid, mid)
            by_rep[name] = by_rep.get(name, 0.0) + float(r.get("revenue_collected", 0) or 0)

        # Commission tiers: 0-5K=10%, 5K-10K=12%, 10K+=15%
        reps = []
        total_commission = 0.0
        for name, revenue in sorted(by_rep.items(), key=lambda x: x[1], reverse=True):
            if revenue <= 5000:
                rate = 0.10
            elif revenue <= 10000:
                rate = 0.12
            else:
                rate = 0.15
            commission = revenue * rate
            total_commission += commission
            reps.append({
                "name": name,
                "revenue_collected": revenue,
                "commission_rate": rate,
                "commission_earned": round(commission, 2),
                "tier": "10%" if revenue <= 5000 else ("12%" if revenue <= 10000 else "15%"),
            })

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "tiers": {"0-5K": "10%", "5K-10K": "12%", "10K+": "15%"},
            "reps": reps,
            "total_commission": round(total_commission, 2),
        }

    def _fallback_quotas(self) -> Optional[Dict]:
        """Build quota vs actual from team_members + closer_submissions."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        closers = self._supabase_query("closer_submissions", {"submission_date": f"gte.{mtd_start}"})
        sdrs = self._supabase_query("sdr_submissions", {"submission_date": f"gte.{mtd_start}"})
        if members is None:
            return None

        # Aggregate actuals by member
        closer_rev: Dict[str, float] = {}
        for r in (closers or []):
            mid = r.get("team_member_id", "unknown")
            closer_rev[mid] = closer_rev.get(mid, 0.0) + float(r.get("revenue_collected", 0) or 0)

        sdr_bookings: Dict[str, int] = {}
        for r in (sdrs or []):
            mid = r.get("team_member_id", "unknown")
            sdr_bookings[mid] = sdr_bookings.get(mid, 0) + r.get("bookings", 0)

        # Default quotas: closer=10K/mo revenue, sdr=30 bookings/mo
        reps = []
        for m in members:
            mid = m["id"]
            role = (m.get("role") or "").lower()
            name = m.get("full_name", "Unknown")
            quota = float(m.get("quota", 0) or m.get("target", 0) or 0)
            if role in ("closer", "sales"):
                if not quota:
                    quota = 10000.0
                actual = closer_rev.get(mid, 0.0)
                pct = (actual / quota * 100) if quota else 0
                reps.append({
                    "name": name, "role": role, "quota": quota,
                    "actual": actual, "pct_to_quota": round(pct, 1),
                    "unit": "revenue",
                })
            elif role in ("sdr", "setter"):
                if not quota:
                    quota = 30.0
                actual = float(sdr_bookings.get(mid, 0))
                pct = (actual / quota * 100) if quota else 0
                reps.append({
                    "name": name, "role": role, "quota": quota,
                    "actual": actual, "pct_to_quota": round(pct, 1),
                    "unit": "bookings",
                })

        return {"source": "supabase_fallback", "period": "mtd", "reps": reps}

    def _fallback_noshow_analysis(self) -> Optional[Dict]:
        """Build no-show analysis from eoc_reports where outcome=no_show."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        eoc_all = self._supabase_query("eoc_reports", {"report_date": f"gte.{mtd_start}"})
        if eoc_all is None:
            return None

        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        member_map = {m["id"]: m.get("full_name", "Unknown") for m in (members or [])}

        no_shows = [r for r in eoc_all if r.get("outcome") == "no_show"]
        total_calls = len(eoc_all)
        no_show_count = len(no_shows)
        no_show_rate = (no_show_count / total_calls * 100) if total_calls else 0

        # By offer
        by_offer: Dict[str, int] = {}
        for r in no_shows:
            o = r.get("offer", "unknown") or "unknown"
            by_offer[o] = by_offer.get(o, 0) + 1

        # By day of week
        by_day: Dict[str, int] = {}
        for r in no_shows:
            rd = r.get("report_date", "")
            if rd:
                try:
                    day_name = datetime.strptime(rd[:10], "%Y-%m-%d").strftime("%A")
                    by_day[day_name] = by_day.get(day_name, 0) + 1
                except ValueError:
                    pass

        # By team member
        by_member: Dict[str, int] = {}
        for r in no_shows:
            mid = r.get("team_member_id", "unknown")
            name = member_map.get(mid, mid)
            by_member[name] = by_member.get(name, 0) + 1

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "total_calls": total_calls,
            "no_show_count": no_show_count,
            "no_show_rate": round(no_show_rate, 1),
            "by_offer": by_offer,
            "by_day_of_week": by_day,
            "by_team_member": by_member,
        }

    def _fallback_objection_data(self) -> Optional[Dict]:
        """Build objection frequency from eoc_reports.objections array."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        eoc = self._supabase_query("eoc_reports", {"report_date": f"gte.{mtd_start}"})
        if eoc is None:
            return None

        objection_counts: Dict[str, int] = {}
        total_with_objections = 0
        for r in eoc:
            objs = r.get("objections")
            if not objs:
                continue
            if isinstance(objs, str):
                try:
                    objs = json.loads(objs)
                except (json.JSONDecodeError, TypeError):
                    objs = [objs]
            if not isinstance(objs, list):
                continue
            total_with_objections += 1
            for obj in objs:
                obj_str = str(obj).strip()
                if obj_str:
                    objection_counts[obj_str] = objection_counts.get(obj_str, 0) + 1

        # Sort by frequency
        ranked = sorted(objection_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "total_calls_with_objections": total_with_objections,
            "total_calls": len(eoc),
            "objections": [{"objection": k, "count": v} for k, v in ranked],
        }

    def _fallback_insights(self) -> Optional[Dict]:
        """Build computed insights: revenue pace, close rate trend, top/bottom performer."""
        today = datetime.now()
        mtd_start = today.replace(day=1).strftime("%Y-%m-%d")
        days_elapsed = today.day
        # Days in current month
        if today.month == 12:
            days_in_month = 31
        else:
            days_in_month = (today.replace(month=today.month + 1, day=1) - timedelta(days=1)).day

        eoc = self._supabase_query("eoc_reports", {"report_date": f"gte.{mtd_start}"})
        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        if eoc is None:
            return None

        member_map = {m["id"]: m.get("full_name", "Unknown") for m in (members or [])}

        # Revenue pace
        mtd_revenue = sum(float(r.get("revenue_collected", 0) or 0) for r in eoc if r.get("outcome") == "showed_closed")
        projected = (mtd_revenue / days_elapsed * days_in_month) if days_elapsed else 0

        # Close rate
        showed = sum(1 for r in eoc if r.get("outcome") in ("showed_closed", "showed_not_closed"))
        closed = sum(1 for r in eoc if r.get("outcome") == "showed_closed")
        close_rate = (closed / showed * 100) if showed else 0

        # Per-rep revenue for top/bottom
        by_rep: Dict[str, float] = {}
        for r in eoc:
            if r.get("outcome") == "showed_closed":
                mid = r.get("team_member_id", "unknown")
                name = member_map.get(mid, mid)
                by_rep[name] = by_rep.get(name, 0.0) + float(r.get("revenue_collected", 0) or 0)

        sorted_reps = sorted(by_rep.items(), key=lambda x: x[1], reverse=True)
        top_performer = sorted_reps[0] if sorted_reps else ("N/A", 0)
        bottom_performer = sorted_reps[-1] if sorted_reps else ("N/A", 0)

        # Biggest objection
        objection_counts: Dict[str, int] = {}
        for r in eoc:
            objs = r.get("objections")
            if not objs:
                continue
            if isinstance(objs, str):
                try:
                    objs = json.loads(objs)
                except (json.JSONDecodeError, TypeError):
                    objs = [objs]
            if isinstance(objs, list):
                for obj in objs:
                    obj_str = str(obj).strip()
                    if obj_str:
                        objection_counts[obj_str] = objection_counts.get(obj_str, 0) + 1
        biggest_objection = max(objection_counts, key=objection_counts.get) if objection_counts else "N/A"

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "revenue_pace": {
                "mtd_collected": round(mtd_revenue, 2),
                "projected_eom": round(projected, 2),
                "days_elapsed": days_elapsed,
                "days_in_month": days_in_month,
            },
            "close_rate": round(close_rate, 1),
            "top_performer": {"name": top_performer[0], "revenue": top_performer[1]},
            "bottom_performer": {"name": bottom_performer[0], "revenue": bottom_performer[1]},
            "biggest_objection": biggest_objection,
        }

    def _fallback_revenue_metrics(self) -> Optional[Dict]:
        """Build revenue metrics from eoc_reports + payment_records."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        eoc = self._supabase_query("eoc_reports", {
            "report_date": f"gte.{mtd_start}",
            "outcome": "eq.showed_closed",
        })
        payments = self._supabase_query("payment_records", {
            "payment_date": f"gte.{mtd_start}",
        })
        if eoc is None:
            return None

        cash_collected = sum(float(r.get("revenue_collected", 0) or 0) for r in eoc)
        revenue_contracted = sum(float(r.get("revenue_contracted", 0) or 0) for r in eoc)

        # Payment records breakdown
        payment_collected = sum(float(p.get("amount", 0) or 0) for p in (payments or []) if p.get("status") == "completed")
        payment_pending = sum(float(p.get("amount", 0) or 0) for p in (payments or []) if p.get("status") in ("pending", "scheduled"))
        payment_failed = sum(float(p.get("amount", 0) or 0) for p in (payments or []) if p.get("status") == "failed")

        # By payment type from EOC
        by_type: Dict[str, int] = {}
        for r in eoc:
            pt = r.get("payment_type", "unknown") or "unknown"
            by_type[pt] = by_type.get(pt, 0) + 1

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "cash_collected": round(cash_collected, 2),
            "revenue_contracted": round(revenue_contracted, 2),
            "deals_closed": len(eoc),
            "avg_deal_size": round(cash_collected / len(eoc), 2) if eoc else 0,
            "payment_plans": {
                "collected": round(payment_collected, 2),
                "pending": round(payment_pending, 2),
                "failed": round(payment_failed, 2),
            },
            "by_payment_type": by_type,
        }

    def _fallback_search_contacts(self, query: str) -> Optional[List]:
        """Search contacts by name or email using ilike."""
        pattern = f"%{query}%"
        # Try name search first
        results = self._supabase_query("contacts", {
            "full_name": f"ilike.{pattern}",
            "select": "id,full_name,email,phone,source,offer,status,company_name",
            "limit": "25",
        })
        if results:
            return results
        # Try email search
        results = self._supabase_query("contacts", {
            "email": f"ilike.{pattern}",
            "select": "id,full_name,email,phone,source,offer,status,company_name",
            "limit": "25",
        })
        return results

    def _fallback_lead_sources(self) -> Optional[Dict]:
        """Build lead source breakdown from contacts table grouped by source."""
        mtd_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        contacts = self._supabase_query("contacts", {
            "created_at": f"gte.{mtd_start}",
            "select": "id,source,offer,status",
        })
        if contacts is None:
            return None

        by_source: Dict[str, int] = {}
        by_offer: Dict[str, int] = {}
        for c in contacts:
            src = c.get("source", "unknown") or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
            offer = c.get("offer", "unknown") or "unknown"
            by_offer[offer] = by_offer.get(offer, 0) + 1

        ranked = sorted(by_source.items(), key=lambda x: x[1], reverse=True)

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "total_leads": len(contacts),
            "by_source": [{"source": k, "count": v} for k, v in ranked],
            "by_offer": by_offer,
        }

    def _fallback_data_health(self) -> Optional[Dict]:
        """Check data completeness: missing EOC days, non-submitting members."""
        today = datetime.now()
        mtd_start = today.replace(day=1).strftime("%Y-%m-%d")

        members = self._supabase_query("team_members", {"is_active": "eq.true"})
        eoc = self._supabase_query("eoc_reports", {"report_date": f"gte.{mtd_start}"})
        if members is None or eoc is None:
            return None

        # Which members are closers/sales?
        closer_members = [m for m in members if (m.get("role") or "").lower() in ("closer", "sales")]
        closer_ids = {m["id"] for m in closer_members}
        member_map = {m["id"]: m.get("full_name", "Unknown") for m in members}

        # Days with submissions per member
        member_dates: Dict[str, set] = {mid: set() for mid in closer_ids}
        for r in eoc:
            mid = r.get("team_member_id")
            rd = r.get("report_date", "")[:10]
            if mid in member_dates and rd:
                member_dates[mid].add(rd)

        # Business days this month (Mon-Fri)
        business_days = []
        d = today.replace(day=1)
        while d <= today:
            if d.weekday() < 5:  # Mon-Fri
                business_days.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

        # Missing days per member
        missing_by_member: Dict[str, List[str]] = {}
        for mid in closer_ids:
            name = member_map.get(mid, mid)
            submitted = member_dates.get(mid, set())
            missing = [day for day in business_days if day not in submitted]
            if missing:
                missing_by_member[name] = missing

        total_expected = len(business_days) * len(closer_ids)
        total_submitted = sum(len(dates) for dates in member_dates.values())
        completeness = (total_submitted / total_expected * 100) if total_expected else 100

        return {
            "source": "supabase_fallback",
            "period": "mtd",
            "business_days_so_far": len(business_days),
            "active_closers": len(closer_ids),
            "total_eoc_reports": len(eoc),
            "expected_reports": total_expected,
            "completeness_pct": round(completeness, 1),
            "missing_by_member": missing_by_member,
        }

    # ── Composite reports ────────────────────────────────────────────────

    def generate_daily_report(self) -> Dict:
        """Aggregated daily summary for the Sales Manager agent."""
        kpi = self.get_kpi_snapshot() or {}
        funnel = self.get_funnel_data() or {}
        health = self.get_data_health() or {}
        calls = self.get_upcoming_calls() or []
        insights = self.get_insights() or {}

        return {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "report_type": "daily_sales_summary",
            "kpi_snapshot": kpi,
            "funnel": funnel,
            "data_health": health,
            "upcoming_calls_count": len(calls),
            "upcoming_calls": calls[:10],  # Next 10 calls
            "ai_insights": insights,
        }

    def generate_weekly_scorecard(self) -> Dict:
        """Per-rep weekly scorecard with RAG status."""
        team = self.get_team_performance(period="wtd") or {}
        commissions = self.get_commissions() or {}
        noshow = self.get_noshow_analysis() or {}
        objections = self.get_objection_data() or {}

        reps = team.get("reps", [])
        scorecards = []
        for rep in reps:
            show_rate = rep.get("show_rate", 0)
            close_rate = rep.get("close_rate", 0)
            scorecards.append({
                "name": rep.get("name", "Unknown"),
                "calls": rep.get("calls", 0),
                "showed": rep.get("showed", 0),
                "closed": rep.get("closed", 0),
                "revenue": rep.get("revenue", 0),
                "show_rate": show_rate,
                "close_rate": close_rate,
                "show_rate_status": self._rag_status(show_rate, 80, 60),
                "close_rate_status": self._rag_status(close_rate, 35, 20),
            })

        return {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "report_type": "weekly_scorecard",
            "scorecards": scorecards,
            "commissions": commissions,
            "noshow_analysis": noshow,
            "objection_trends": objections,
        }


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="247growth dashboard client — pull live sales data")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    sub.add_parser("kpi", help="MTD KPI snapshot")
    sub.add_parser("team", help="Team performance")

    funnel_p = sub.add_parser("funnel", help="Sales funnel")
    funnel_p.add_argument("--offer", default=None, help="Filter by offer (agency|coaching)")

    sub.add_parser("scorecard", help="Weekly scorecard")
    sub.add_parser("report", help="Full daily report")
    sub.add_parser("commissions", help="Commission breakdown")

    submissions_p = sub.add_parser("submissions", help="EOD submissions")
    submissions_p.add_argument("--role", default="closer", choices=["closer", "sdr"])
    submissions_p.add_argument("--start", default=None)
    submissions_p.add_argument("--end", default=None)
    submissions_p.add_argument("--member-id", default=None)

    contacts_p = sub.add_parser("contacts", help="Search contacts")
    contacts_p.add_argument("--query", "-q", required=True)

    sub.add_parser("calls", help="Upcoming calls")
    sub.add_parser("health", help="Data health check")
    sub.add_parser("noshow", help="No-show analysis")
    sub.add_parser("objections", help="Objection data")
    sub.add_parser("roster", help="Team roster")
    sub.add_parser("utm", help="Lead source attribution")
    sub.add_parser("insights", help="AI-generated insights")
    sub.add_parser("revenue", help="Revenue metrics")

    journey_p = sub.add_parser("journey", help="Contact journey")
    journey_p.add_argument("--contact-id", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    client = DashboardClient()

    commands = {
        "kpi": lambda: client.get_kpi_snapshot(),
        "team": lambda: client.get_team_performance(),
        "funnel": lambda: client.get_funnel_data(offer=args.offer if hasattr(args, "offer") else None),
        "scorecard": lambda: client.generate_weekly_scorecard(),
        "report": lambda: client.generate_daily_report(),
        "commissions": lambda: client.get_commissions(),
        "calls": lambda: client.get_upcoming_calls(),
        "health": lambda: client.get_data_health(),
        "noshow": lambda: client.get_noshow_analysis(),
        "objections": lambda: client.get_objection_data(),
        "roster": lambda: client.get_team_roster(),
        "utm": lambda: client.get_lead_sources(),
        "insights": lambda: client.get_insights(),
        "revenue": lambda: client.get_revenue_metrics(),
        "journey": lambda: client.get_contact_journey(args.contact_id),
        "contacts": lambda: client.search_contacts(args.query),
        "submissions": lambda: (
            client.get_closer_submissions(args.start, args.end, args.member_id)
            if args.role == "closer"
            else client.get_sdr_submissions(args.start, args.end, args.member_id)
        ),
    }

    result = commands[args.command]()
    if result is None:
        print("No data returned. Check env vars and network connection.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
