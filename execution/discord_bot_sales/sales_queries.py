"""Sales Query Router — detects data intent and fetches relevant sales data on demand."""

from __future__ import annotations

import json
import re
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


# GHL Pipeline stages for 24/7 Profits
PIPELINE_ID = "sFxWPIwC0fTGZBNRO0Lf"
STAGE_MAP = {
    "opt_in": "a2018e4a-e6eb-4fc4-a6f0-e5f4167be189",
    "free_training": "a2018e4a-e6eb-4fc4-a6f0-e5f4167be189",
    "application": "8a87671c-caa6-4669-a47d-69040cac6195",
    "typeform": "8a87671c-caa6-4669-a47d-69040cac6195",
    "no_answer": "2021b735-a8e2-4de7-9baa-a716de2dcf92",
    "not_interested": "0bdc3637-c6fd-4433-8ab9-330cbf759356",
    "cooked": "8366d5e0-d56f-408a-b297-40169688380f",
    "brokie": "65b83199-4c89-430f-b4e9-86ee26701c49",
    "follow_up": "ab4db504-899b-4de1-a9e5-2bb223f41a18",
    "send_more_info": "b19c6d28-d564-4785-9bf2-f6f5720ec42e",
    "booked": "694954ce-8782-4165-9e07-d8d3b57d5fc3",
    "no_show": "7d0a0d59-b9b5-4b04-8bd7-3566aacef9bd",
    "cancelled": "2709e911-d833-40a9-96c9-3dde62690869",
    "no_close": "5365a36e-db70-4299-9a0e-659e49102446",
    "closed": "2d86f722-1b69-4662-afaf-9ebe5986a7cd",
}

STAGE_NAMES = {v: k.replace("_", " ").title() for k, v in STAGE_MAP.items()}


class SalesQueryRouter:
    """Detects data queries in user questions and fetches relevant data."""

    def __init__(self, dashboard_client):
        self.dc = dashboard_client
        self._team_cache = None
        self._team_cache_ts = 0
        # GHL contact search cache: name -> (contacts_list, timestamp)
        self._ghl_cache: Dict[str, Any] = {}
        self._ghl_cache_ttl = 120  # 2 min

    def _ghl_search_cached(self, name: str) -> List:
        """GHL contact search with 2-min cache to avoid duplicate lookups."""
        key = name.lower().strip()
        cached = self._ghl_cache.get(key)
        if cached and _time.time() - cached[1] < self._ghl_cache_ttl:
            return cached[0]
        result = self.dc._ghl_get("/contacts/", {"query": name, "limit": 3})
        contacts = result.get("contacts", []) if result else []
        self._ghl_cache[key] = (contacts, _time.time())
        return contacts

    def _get_team_map(self) -> Dict[str, str]:
        """Get team member id->name map with caching."""
        import time
        now = time.time()
        if self._team_cache and now - self._team_cache_ts < 600:
            return self._team_cache
        members = self.dc._supabase_query("team_members", {"is_active": "eq.true"}) or []
        self._team_cache = {m["id"]: m.get("full_name", "Unknown") for m in members}
        self._team_cache_ts = now
        return self._team_cache

    def _get_team_names(self) -> List[str]:
        """Get list of team member first names (lowercase)."""
        team = self._get_team_map()
        names = []
        for name in team.values():
            names.append(name.lower())
            first = name.split()[0].lower() if name else ""
            if first:
                names.append(first)
        return names

    def _reverse_team_map(self) -> Dict[str, str]:
        """Name -> member_id mapping."""
        team = self._get_team_map()
        reverse = {}
        for mid, name in team.items():
            reverse[name.lower()] = mid
            first = name.split()[0].lower() if name else ""
            if first:
                reverse[first] = mid
        return reverse

    def _parse_date_range(self, question: str) -> Tuple[str, str]:
        """Extract date range from question. Returns (start, end) as YYYY-MM-DD."""
        q = question.lower()
        today = datetime.now()

        if "today" in q:
            d = today.strftime("%Y-%m-%d")
            return d, d
        if "yesterday" in q:
            d = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            return d, d
        if "this week" in q:
            start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
            return start, today.strftime("%Y-%m-%d")
        if "last week" in q:
            start = (today - timedelta(days=today.weekday() + 7)).strftime("%Y-%m-%d")
            end = (today - timedelta(days=today.weekday() + 1)).strftime("%Y-%m-%d")
            return start, end
        if "this month" in q or "mtd" in q:
            return today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
        if "last month" in q:
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            first_prev = last_prev.replace(day=1)
            return first_prev.strftime("%Y-%m-%d"), last_prev.strftime("%Y-%m-%d")
        # Match "march", "february" etc
        months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                  "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
        for name, num in months.items():
            if name in q:
                year = today.year
                start = datetime(year, num, 1)
                if num == 12:
                    end = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end = datetime(year, num + 1, 1) - timedelta(days=1)
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

        # Default: this month
        return today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

    def _extract_names(self, question: str) -> List[str]:
        """Extract potential person names from question (not team members)."""
        q = question.lower()
        team_names = set(self._get_team_names())
        # Find capitalized words that aren't common words
        skip = {"who", "what", "when", "where", "how", "why", "show", "tell", "get", "find",
                "the", "for", "with", "about", "from", "this", "that", "last", "next", "all",
                "me", "my", "our", "his", "her", "ask", "nova", "sales", "call", "calls",
                "today", "yesterday", "week", "month", "inner", "circle", "semi", "profits",
                "payment", "payments", "revenue", "pipeline", "booked", "closed", "objections",
                "notes", "convo", "conversation", "read", "check", "look", "up"}
        # Also check the original casing for names
        words = question.split()
        candidates = []
        for w in words:
            clean = re.sub(r'[^a-zA-Z]', '', w).lower()
            if clean and clean not in skip and clean not in team_names and len(clean) > 2:
                if w[0].isupper():  # Likely a name
                    candidates.append(clean)
        return candidates

    def _find_rep_in_question(self, question: str) -> Optional[str]:
        """Check if question mentions a team member. Returns member_id or None."""
        q = question.lower()
        reverse = self._reverse_team_map()
        for name, mid in reverse.items():
            if name in q:
                return mid
        return None

    def detect_intent(self, question: str) -> List[str]:
        """Classify the question into data query intents."""
        q = question.lower()
        intents = []

        # Contact/person lookup
        names = self._extract_names(question)
        if names:
            intents.append("contact_lookup")

        # Call history
        if any(kw in q for kw in ["call history", "past calls", "calls this", "calls last",
                                   "eoc", "end of close", "how many calls", "call log"]):
            intents.append("call_history")
        elif names and any(kw in q for kw in ["call", "calls"]):
            intents.append("call_history")

        # Contact notes / conversations
        if any(kw in q for kw in ["notes", "convo", "conversation", "what happened",
                                   "call with", "tell me about", "read me", "pull up"]):
            intents.append("contact_notes")

        # Payments
        if any(kw in q for kw in ["payment", "paid", "collected", "deposit", "revenue",
                                   "money", "cash", "billing", "payment plan"]):
            intents.append("payment_query")

        # Pipeline / stages
        if any(kw in q for kw in ["pipeline", "opted", "opt-in", "opt in", "booked",
                                   "no show", "no-show", "closed deals", "how many closed",
                                   "who closed", "funnel"]):
            intents.append("pipeline_stage")

        # Rep performance
        rep_id = self._find_rep_in_question(question)
        if rep_id and any(kw in q for kw in ["performance", "stats", "numbers", "how is",
                                              "how's", "doing", "scorecard", "rate"]):
            intents.append("rep_performance")

        # Objection analysis
        if any(kw in q for kw in ["objection", "objections", "pushback", "common objection",
                                   "what objections", "handle"]):
            intents.append("objection_analysis")

        # Lead activity
        if any(kw in q for kw in ["new leads", "leads today", "who came in", "new contacts",
                                   "recent leads", "lead flow", "inbound"]):
            intents.append("lead_activity")

        # Offer breakdown
        if any(kw in q for kw in ["inner circle", "semi circle", "semi-circle",
                                   "by offer", "offer breakdown", "which offer"]):
            intents.append("offer_breakdown")

        return intents

    def fetch_data(self, intents: List[str], question: str) -> str:
        """Fetch data for all detected intents IN PARALLEL."""
        names = self._extract_names(question)
        date_start, date_end = self._parse_date_range(question)
        rep_id = self._find_rep_in_question(question)

        # Pre-warm GHL cache for all names (single batch, avoids duplicate lookups)
        for name in names[:3]:
            self._ghl_search_cached(name)

        # Deduplicate: if contact_lookup + contact_notes both present, merge into contact_lookup
        if "contact_lookup" in intents and "contact_notes" in intents:
            intents = [i for i in intents if i != "contact_notes"]

        # Build task list
        def _run(intent: str) -> str:
            try:
                if intent == "contact_lookup" and names:
                    return self._fetch_contact_lookup(names)
                elif intent == "call_history":
                    return self._fetch_call_history(date_start, date_end, rep_id, names)
                elif intent == "contact_notes" and names:
                    return self._fetch_contact_notes(names)
                elif intent == "payment_query":
                    return self._fetch_payments(date_start, date_end, names)
                elif intent == "pipeline_stage":
                    return self._fetch_pipeline(question)
                elif intent == "rep_performance" and rep_id:
                    return self._fetch_rep_performance(rep_id, date_start, date_end)
                elif intent == "objection_analysis":
                    return self._fetch_objections(date_start, date_end)
                elif intent == "lead_activity":
                    return self._fetch_leads(question)
                elif intent == "offer_breakdown":
                    return self._fetch_offer_breakdown(date_start, date_end)
            except Exception as e:
                return f"[Error fetching {intent}: {e}]"
            return ""

        # Run all fetches in parallel (max 4 threads)
        parts = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_run, intent): intent for intent in intents}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    parts.append(result)

        return "\n\n".join(parts)

    # ── Data Fetchers ─────────────────────────────────────────────────

    def _fetch_contact_lookup(self, names: List[str]) -> str:
        """Look up contacts by name in GHL + Supabase."""
        lines = ["### Contact Lookup"]
        for name in names[:3]:  # Max 3 lookups per query
            # Search GHL
            ghl_contacts = self._ghl_search_cached(name)

            # Search Supabase
            supa_contacts = self.dc._supabase_query("contacts", {
                "full_name": f"ilike.*{name}*",
                "select": "id,full_name,email,phone,source,status,ghl_contact_id,created_at",
                "limit": "3",
            }) or []

            if not ghl_contacts and not supa_contacts:
                lines.append(f"\n**{name.title()}:** No contact found")
                continue

            # GHL data (richer — has pipeline stage, tags, etc.)
            for c in ghl_contacts:
                cname = c.get("contactName") or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                lines.append(f"\n**{cname}** (GHL)")
                if c.get("email"): lines.append(f"- Email: {c['email']}")
                if c.get("phone"): lines.append(f"- Phone: {c['phone']}")
                if c.get("source"): lines.append(f"- Source: {c['source']}")
                if c.get("city"): lines.append(f"- Location: {c.get('city', '')}, {c.get('state', '')}")
                if c.get("tags"): lines.append(f"- Tags: {', '.join(c['tags'])}")
                if c.get("dateAdded"): lines.append(f"- Added: {c['dateAdded'][:10]}")

                # Get their EOC history from Supabase
                ghl_id = c.get("id", "")
                # Find matching Supabase contact
                supa_match = self.dc._supabase_query("contacts", {
                    "ghl_contact_id": f"eq.{ghl_id}",
                    "select": "id",
                }) or []
                if not supa_match:
                    # Try name match
                    supa_match = self.dc._supabase_query("contacts", {
                        "full_name": f"ilike.*{name}*",
                        "select": "id",
                        "limit": "1",
                    }) or []

                if supa_match:
                    cid = supa_match[0]["id"]
                    # Get EOC reports
                    eocs = self.dc._supabase_query("eoc_reports", {
                        "contact_id": f"eq.{cid}",
                        "select": "report_date,outcome,offer,objections,revenue_collected,notes,coaching_notes",
                        "order": "report_date.desc",
                        "limit": "5",
                    }) or []
                    if eocs:
                        lines.append("- **Call History:**")
                        for e in eocs:
                            obj_str = ""
                            if e.get("objections") and e["objections"] != []:
                                objs = e["objections"] if isinstance(e["objections"], list) else []
                                obj_str = f" | Objections: {', '.join(str(o) for o in objs)}"
                            lines.append(f"  - {e['report_date']} | {e.get('outcome', '')} | "
                                         f"{e.get('offer', '')}{obj_str} | ${float(e.get('revenue_collected', 0) or 0):,.0f}")

                    # Get payments
                    payments = self.dc._supabase_query("payment_records", {
                        "contact_id": f"eq.{cid}",
                        "select": "amount,payment_date,payment_method,status",
                        "order": "payment_date.desc",
                        "limit": "5",
                    }) or []
                    if payments:
                        lines.append("- **Payments:**")
                        for p in payments:
                            lines.append(f"  - {p.get('payment_date', '')} | ${float(p.get('amount', 0)):,.0f} | "
                                         f"{p.get('payment_method', '')} | {p.get('status', '')}")

            # Supabase-only contacts (not in GHL)
            for c in supa_contacts:
                if not any(g.get("email") == c.get("email") for g in ghl_contacts if g.get("email")):
                    lines.append(f"\n**{c.get('full_name', name.title())}** (Database)")
                    if c.get("email"): lines.append(f"- Email: {c['email']}")
                    if c.get("phone"): lines.append(f"- Phone: {c['phone']}")
                    if c.get("source"): lines.append(f"- Source: {c['source']}")
                    if c.get("status"): lines.append(f"- Status: {c['status']}")

        return "\n".join(lines)

    def _fetch_call_history(self, start: str, end: str, rep_id: Optional[str], names: List[str]) -> str:
        """Fetch EOC reports with optional rep/contact filter."""
        params = {
            "report_date": f"gte.{start}",
            "select": "report_date,team_member_id,contact_id,outcome,offer,objections,objection_notes,"
                      "revenue_collected,revenue_contracted,notes,coaching_notes,did_pitch",
            "order": "report_date.desc",
            "limit": "30",
        }
        if rep_id:
            params["team_member_id"] = f"eq.{rep_id}"

        eocs = self.dc._supabase_query("eoc_reports", params) or []
        if not eocs:
            return "### Call History\nNo EOC reports found for this period."

        team = self._get_team_map()
        # Resolve contact names
        cids = list({e["contact_id"] for e in eocs if e.get("contact_id")})
        contact_names = {}
        if cids:
            contacts = self.dc._supabase_query("contacts", {
                "id": f"in.({','.join(cids)})",
                "select": "id,full_name",
                "organization_id": None,
            }) or []
            contact_names = {c["id"]: c.get("full_name", "Unknown") for c in contacts}

        lines = [f"### Call History ({start} to {end}) — {len(eocs)} reports"]
        for e in eocs:
            rep = team.get(e.get("team_member_id", ""), "Unknown")
            prospect = contact_names.get(e.get("contact_id", ""), "Unknown")
            obj_str = ""
            if e.get("objections") and e["objections"] not in ([], None, "[]"):
                objs = e["objections"] if isinstance(e["objections"], list) else []
                if objs:
                    obj_str = f" | Objections: {', '.join(str(o) for o in objs)}"
            notes = ""
            if e.get("objection_notes"):
                notes = f" | Notes: {e['objection_notes'][:100]}"
            coaching = ""
            if e.get("coaching_notes"):
                coaching = f" | Coaching: {e['coaching_notes'][:100]}"
            lines.append(
                f"- **{e['report_date']}** | {rep} → {prospect} | {e.get('outcome', '')} | "
                f"{e.get('offer', '')} | ${float(e.get('revenue_collected', 0) or 0):,.0f}"
                f"{obj_str}{notes}{coaching}"
            )

        return "\n".join(lines)

    def _fetch_contact_notes(self, names: List[str]) -> str:
        """Fetch GHL contact notes (AI call summaries, manual notes)."""
        lines = ["### Contact Notes"]
        for name in names[:2]:
            contacts = self._ghl_search_cached(name)
            if not contacts:
                lines.append(f"\n**{name.title()}:** No GHL contact found")
                continue

            c = contacts[0]
            cid = c.get("id", "")
            cname = c.get("contactName") or name.title()

            notes_data = self.dc._ghl_get(f"/contacts/{cid}/notes")
            notes = notes_data.get("notes", []) if notes_data else []

            if not notes:
                lines.append(f"\n**{cname}:** No notes on file")
                continue

            lines.append(f"\n**{cname}** — {len(notes)} notes:")
            for n in notes[:10]:  # Last 10 notes
                body = n.get("body", "").strip()
                created = n.get("createdAt", "")[:16].replace("T", " ")
                # Truncate long notes
                if len(body) > 500:
                    body = body[:500] + "..."
                lines.append(f"\n> **{created}**\n> {body}")

        return "\n".join(lines)

    def _fetch_payments(self, start: str, end: str, names: List[str]) -> str:
        """Fetch payment records."""
        params = {
            "payment_date": f"gte.{start}",
            "select": "amount,payment_date,payment_method,status,contact_id",
            "order": "payment_date.desc",
            "limit": "30",
        }
        payments = self.dc._supabase_query("payment_records", params) or []

        if not payments:
            return "### Payments\nNo payment records found for this period."

        # Resolve contact names
        cids = list({p["contact_id"] for p in payments if p.get("contact_id")})
        contact_names = {}
        if cids:
            contacts = self.dc._supabase_query("contacts", {
                "id": f"in.({','.join(cids)})",
                "select": "id,full_name",
                "organization_id": None,
            }) or []
            contact_names = {c["id"]: c.get("full_name", "Unknown") for c in contacts}

        total = sum(float(p.get("amount", 0) or 0) for p in payments)
        lines = [f"### Payments ({start} to {end}) — {len(payments)} records, ${total:,.0f} total"]
        for p in payments:
            name = contact_names.get(p.get("contact_id", ""), "Unknown")
            lines.append(
                f"- {p.get('payment_date', '')} | {name} | ${float(p.get('amount', 0)):,.0f} | "
                f"{p.get('payment_method', '')} | {p.get('status', '')}"
            )

        return "\n".join(lines)

    def _fetch_pipeline(self, question: str) -> str:
        """Fetch pipeline stage data."""
        q = question.lower()

        # Determine which stage(s) to query
        stages_to_query = []
        stage_keywords = {
            "opt": ["opt_in", "free_training"],
            "application": ["application", "typeform"],
            "booked": ["booked"],
            "no show": ["no_show"],
            "no-show": ["no_show"],
            "cancelled": ["cancelled"],
            "no close": ["no_close"],
            "closed": ["closed"],
            "follow": ["follow_up"],
            "not interested": ["not_interested"],
        }
        for keyword, stage_keys in stage_keywords.items():
            if keyword in q:
                stages_to_query.extend(stage_keys)

        # If no specific stage, show overview of active stages
        if not stages_to_query:
            stages_to_query = ["booked", "no_show", "no_close", "closed", "follow_up", "opt_in", "application"]

        lines = ["### Pipeline Status"]
        for stage_key in stages_to_query:
            stage_id = STAGE_MAP.get(stage_key)
            if not stage_id:
                continue
            data = self.dc._ghl_get(f"/pipelines/{PIPELINE_ID}/opportunities",
                                    {"stageId": stage_id, "limit": 20})
            opps = data.get("opportunities", []) if data and isinstance(data, dict) else []
            stage_name = stage_key.replace("_", " ").title()
            lines.append(f"\n**{stage_name}** ({len(opps)} contacts):")
            for o in opps[:15]:
                name = o.get("name", "Unknown")
                updated = o.get("updatedAt", "")[:10]
                value = o.get("monetaryValue", 0) or 0
                line = f"- {name} (updated: {updated})"
                if value:
                    line += f" — ${float(value):,.0f}"
                lines.append(line)

        return "\n".join(lines)

    def _fetch_rep_performance(self, rep_id: str, start: str, end: str) -> str:
        """Fetch detailed performance for a specific rep."""
        team = self._get_team_map()
        rep_name = team.get(rep_id, "Unknown")

        eocs = self.dc._supabase_query("eoc_reports", {
            "team_member_id": f"eq.{rep_id}",
            "report_date": f"gte.{start}",
            "select": "report_date,outcome,offer,objections,revenue_collected,revenue_contracted,did_pitch",
            "order": "report_date.desc",
        }) or []

        if not eocs:
            return f"### {rep_name} Performance\nNo EOC reports found for this period."

        total = len(eocs)
        showed = sum(1 for e in eocs if e.get("outcome") in ("showed_closed", "showed_not_closed"))
        closed = sum(1 for e in eocs if e.get("outcome") == "showed_closed")
        no_shows = sum(1 for e in eocs if e.get("outcome") == "no_show")
        revenue = sum(float(e.get("revenue_collected", 0) or 0) for e in eocs)
        show_rate = (showed / total * 100) if total else 0
        close_rate = (closed / showed * 100) if showed else 0

        lines = [f"### {rep_name} Performance ({start} to {end})"]
        lines.append(f"- Total calls: {total}")
        lines.append(f"- Showed: {showed} ({show_rate:.0f}%)")
        lines.append(f"- Closed: {closed} ({close_rate:.0f}%)")
        lines.append(f"- No-shows: {no_shows}")
        lines.append(f"- Revenue collected: ${revenue:,.0f}")
        lines.append(f"- Avg revenue per close: ${revenue / closed:,.0f}" if closed else "")

        # Objection breakdown
        all_objs = {}
        for e in eocs:
            if e.get("objections") and isinstance(e["objections"], list):
                for o in e["objections"]:
                    o_str = str(o).strip().lower()
                    if o_str and o_str != "[]":
                        all_objs[o_str] = all_objs.get(o_str, 0) + 1
        if all_objs:
            lines.append("\n**Objections faced:**")
            for obj, cnt in sorted(all_objs.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- \"{obj}\" — {cnt}x")

        # Per-call detail
        lines.append("\n**Call-by-call:**")
        for e in eocs[:15]:
            lines.append(f"- {e['report_date']} | {e.get('outcome', '')} | {e.get('offer', '')} | "
                         f"${float(e.get('revenue_collected', 0) or 0):,.0f}")

        return "\n".join(lines)

    def _fetch_objections(self, start: str, end: str) -> str:
        """Fetch objection analysis from EOC reports."""
        eocs = self.dc._supabase_query("eoc_reports", {
            "report_date": f"gte.{start}",
            "select": "objections,outcome,revenue_collected,offer",
        }) or []

        obj_data = {}
        for e in eocs:
            if not e.get("objections") or not isinstance(e["objections"], list):
                continue
            for o in e["objections"]:
                o_str = str(o).strip().lower()
                if not o_str or o_str == "[]":
                    continue
                if o_str not in obj_data:
                    obj_data[o_str] = {"total": 0, "closed": 0, "revenue": 0}
                obj_data[o_str]["total"] += 1
                if e.get("outcome") == "showed_closed":
                    obj_data[o_str]["closed"] += 1
                    obj_data[o_str]["revenue"] += float(e.get("revenue_collected", 0) or 0)

        if not obj_data:
            return "### Objection Analysis\nNo objections recorded in this period."

        lines = [f"### Objection Analysis ({start} to {end})"]
        for obj, stats in sorted(obj_data.items(), key=lambda x: x[1]["total"], reverse=True):
            cr = (stats["closed"] / stats["total"] * 100) if stats["total"] else 0
            lines.append(f"- **\"{obj}\"** — {stats['total']}x | Close rate: {cr:.0f}% | "
                         f"Revenue when overcome: ${stats['revenue']:,.0f}")

        return "\n".join(lines)

    def _fetch_leads(self, question: str) -> str:
        """Fetch recent leads from GHL."""
        q = question.lower()
        limit = 20
        if "today" in q:
            limit = 50  # Get more for today filter

        ghl_data = self.dc._ghl_get("/contacts/", {"limit": limit, "sortBy": "date_added", "order": "desc"})
        contacts = ghl_data.get("contacts", []) if ghl_data else []

        if not contacts:
            return "### Recent Leads\nNo contacts found."

        today = datetime.now().strftime("%Y-%m-%d")
        if "today" in q:
            contacts = [c for c in contacts if (c.get("dateAdded") or "")[:10] == today]

        lines = [f"### Recent Leads ({len(contacts)} contacts)"]
        for c in contacts[:20]:
            name = c.get("contactName") or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or "Unknown"
            email = c.get("email") or ""
            phone = c.get("phone") or ""
            source = c.get("source") or ""
            added = (c.get("dateAdded") or "")[:10]
            tags = ", ".join(c.get("tags", []))
            lines.append(f"- **{name}** | {phone} | {email}" +
                         (f" | Source: {source}" if source else "") +
                         (f" | Tags: {tags}" if tags else "") +
                         f" | Added: {added}")

        return "\n".join(lines)

    def _fetch_offer_breakdown(self, start: str, end: str) -> str:
        """Fetch per-offer stats from EOC reports."""
        eocs = self.dc._supabase_query("eoc_reports", {
            "report_date": f"gte.{start}",
            "select": "offer,outcome,revenue_collected",
        }) or []

        by_offer = {}
        for e in eocs:
            offer = e.get("offer", "Unknown")
            if offer not in by_offer:
                by_offer[offer] = {"total": 0, "showed": 0, "closed": 0, "revenue": 0, "no_show": 0}
            by_offer[offer]["total"] += 1
            if e.get("outcome") in ("showed_closed", "showed_not_closed"):
                by_offer[offer]["showed"] += 1
            if e.get("outcome") == "showed_closed":
                by_offer[offer]["closed"] += 1
                by_offer[offer]["revenue"] += float(e.get("revenue_collected", 0) or 0)
            if e.get("outcome") == "no_show":
                by_offer[offer]["no_show"] += 1

        if not by_offer:
            return "### Offer Breakdown\nNo data for this period."

        lines = [f"### Offer Breakdown ({start} to {end})"]
        for offer, stats in by_offer.items():
            show_rate = (stats["showed"] / stats["total"] * 100) if stats["total"] else 0
            close_rate = (stats["closed"] / stats["showed"] * 100) if stats["showed"] else 0
            lines.append(f"\n**{offer}:**")
            lines.append(f"- Calls: {stats['total']} | Showed: {stats['showed']} ({show_rate:.0f}%) | "
                         f"Closed: {stats['closed']} ({close_rate:.0f}%)")
            lines.append(f"- No-shows: {stats['no_show']} | Revenue: ${stats['revenue']:,.0f}")

        return "\n".join(lines)
