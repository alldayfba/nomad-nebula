"""
Setter dashboard — Flask routes for oversight UI at /setter.

Provides live stats, conversation viewer, approval queue, and metrics.
Register with: app.register_blueprint(setter_bp)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import types

from flask import Blueprint, jsonify, render_template_string, request

from functools import wraps

from . import setter_db as db
from .setter_config import DASHBOARD_TOKEN, OFFERS, RATE_LIMITS, SAFETY

setter_bp = Blueprint("setter", __name__, url_prefix="/setter")


def _require_token(f):
    """Require Bearer token for mutating API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_TOKEN:
            return f(*args, **kwargs)  # No token configured = no auth
        auth = request.headers.get("Authorization", "")
        token = request.args.get("token", "")
        if auth == f"Bearer {DASHBOARD_TOKEN}" or token == DASHBOARD_TOKEN:
            return f(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return decorated


# ── Dashboard Template ───────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Setter Dashboard</title>
<style>
:root { --bg: #0a0a0f; --card: #12121a; --border: #1e1e2e; --text: #e0e0e0; --dim: #888; --accent: #6366f1; --green: #22c55e; --red: #ef4444; --yellow: #eab308; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; }
h1 { font-size: 24px; margin-bottom: 24px; }
h2 { font-size: 18px; margin-bottom: 16px; color: var(--accent); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.metric { font-size: 32px; font-weight: 700; }
.label { font-size: 13px; color: var(--dim); margin-top: 4px; }
.status-active { color: var(--green); }
.status-paused { color: var(--red); }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }
th { color: var(--dim); font-weight: 500; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-yellow { background: rgba(234,179,8,0.15); color: var(--yellow); }
.badge-red { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-blue { background: rgba(99,102,241,0.15); color: var(--accent); }
.btn { display: inline-block; padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn-approve { background: var(--green); color: #000; }
.btn-reject { background: var(--red); color: #fff; }
.section { margin-bottom: 40px; }
.refresh { color: var(--dim); font-size: 12px; }
</style>
</head>
<body>
<h1>AI Setter Dashboard <span class="{{ 'status-active' if not paused else 'status-paused' }}">{{ 'ACTIVE' if not paused else 'PAUSED' }}</span></h1>

<div class="grid">
    <div class="card"><div class="metric">{{ metrics.total_dms_sent or 0 }}</div><div class="label">DMs Sent Today</div></div>
    <div class="card"><div class="metric">{{ metrics.replies_received or 0 }}</div><div class="label">Replies Today</div></div>
    <div class="card"><div class="metric">{{ '%.1f'|format(metrics.response_rate or 0) }}%</div><div class="label">Response Rate</div></div>
    <div class="card"><div class="metric">{{ metrics.booked or 0 }}</div><div class="label">Booked Today</div></div>
    <div class="card"><div class="metric">{{ pipeline.qualifying + pipeline.replied + pipeline.booking }}</div><div class="label">Active Convos</div></div>
    <div class="card"><div class="metric">{{ pipeline.booked }}</div><div class="label">Calls Pending</div></div>
    <div class="card"><div class="metric">${{ '%.2f'|format(metrics.api_cost or 0) }}</div><div class="label">API Cost Today</div></div>
    <div class="card"><div class="metric">{{ pipeline.total_prospects }}</div><div class="label">Total Prospects</div></div>
</div>

{% if pending_approvals %}
<div class="section">
<h2>Pending Approvals ({{ pending_approvals|length }})</h2>
<table>
<tr><th>Prospect</th><th>Stage</th><th>AI Response</th><th>Actions</th></tr>
{% for msg in pending_approvals %}
<tr>
    <td>@{{ msg.ig_handle }}</td>
    <td><span class="badge badge-yellow">{{ msg.stage }}</span></td>
    <td>{{ msg.content[:80] }}{% if msg.content|length > 80 %}...{% endif %}</td>
    <td>
        <button class="btn btn-approve" onclick="approve({{ msg.id }})">Approve</button>
        <button class="btn btn-reject" onclick="reject({{ msg.id }})">Reject</button>
    </td>
</tr>
{% endfor %}
</table>
</div>
{% endif %}

<div class="section">
<h2>Active Conversations</h2>
<table>
<tr><th>Prospect</th><th>Stage</th><th>Msgs</th><th>Last Message</th><th>Offer</th><th>ICP</th></tr>
{% for conv in conversations %}
<tr>
    <td><a href="/setter/conversation/{{ conv.id }}" style="color: var(--accent)">@{{ conv.ig_handle }}</a></td>
    <td><span class="badge badge-{{ 'green' if conv.stage in ('booked','show','qualified') else 'blue' if conv.stage in ('qualifying','replied') else 'yellow' }}">{{ conv.stage }}</span></td>
    <td>{{ conv.messages_sent + conv.messages_received }}</td>
    <td style="color: var(--dim)">{{ conv.last_message_at[:16] if conv.last_message_at else 'N/A' }}</td>
    <td>{{ conv.offer }}</td>
    <td>{{ conv.icp_score or '-' }}/10</td>
</tr>
{% endfor %}
</table>
</div>

<div class="section">
<h2>Rate Limits</h2>
<div class="grid">
    {% for channel, count in sends.items() %}
    <div class="card">
        <div class="metric">{{ count }}</div>
        <div class="label">{{ channel }}</div>
    </div>
    {% endfor %}
</div>
</div>

<p class="refresh">Last updated: {{ now }} | <a href="/setter" style="color: var(--accent)">Refresh</a></p>

<script>
async function approve(id) {
    await fetch('/setter/api/approve/' + id, {method: 'POST'});
    location.reload();
}
async function reject(id) {
    await fetch('/setter/api/reject/' + id, {method: 'POST'});
    location.reload();
}
</script>
</body>
</html>
"""


# ── Routes ───────────────────────────────────────────────────────────────────

@setter_bp.route("/")
@setter_bp.route("/dashboard")
def dashboard():
    from pathlib import Path
    paused = Path(SAFETY["pause_file"]).exists()
    metrics = db.get_daily_metrics() or {}
    pipeline = db.get_pipeline_stats()
    conversations = db.get_active_conversations(limit=50)
    sends = db.get_today_send_counts()
    pending = db.get_pending_approval_messages()

    return render_template_string(
        DASHBOARD_HTML,
        paused=paused,
        metrics=metrics,
        pipeline=types.SimpleNamespace(**pipeline),
        conversations=conversations,
        sends=sends,
        pending_approvals=pending,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@setter_bp.route("/conversation/<int:conv_id>")
def conversation_detail(conv_id):
    conv = db.get_conversation(conv_id)
    if not conv:
        return "Conversation not found", 404
    prospect = db.get_prospect(conv["prospect_id"])
    messages = db.get_messages(conv_id, limit=100)
    return jsonify({
        "conversation": conv,
        "prospect": prospect,
        "messages": messages,
    })


@setter_bp.route("/api/stats")
def api_stats():
    return jsonify({
        "pipeline": db.get_pipeline_stats(),
        "metrics": db.get_daily_metrics() or {},
        "sends": db.get_today_send_counts(),
        "pending_approvals": len(db.get_pending_approval_messages()),
    })


@setter_bp.route("/api/approve/<int:msg_id>", methods=["POST"])
@_require_token
def api_approve(msg_id):
    db.approve_message(msg_id, approved_by="sabbo")
    return jsonify({"status": "approved"})


@setter_bp.route("/api/reject/<int:msg_id>", methods=["POST"])
@_require_token
def api_reject(msg_id):
    db.reject_message(msg_id)
    return jsonify({"status": "rejected"})


@setter_bp.route("/api/pause", methods=["POST"])
@_require_token
def api_pause():
    from pathlib import Path
    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
    Path(SAFETY["pause_file"]).touch()
    return jsonify({"status": "paused"})


@setter_bp.route("/api/resume", methods=["POST"])
@_require_token
def api_resume():
    from pathlib import Path
    p = Path(SAFETY["pause_file"])
    if p.exists():
        p.unlink()
    return jsonify({"status": "resumed"})


@setter_bp.route("/api/conversations")
def api_conversations():
    convos = db.get_active_conversations(limit=100)
    return jsonify(convos)


@setter_bp.route("/api/prospects")
def api_prospects():
    status = request.args.get("status", "qualified")
    limit = int(request.args.get("limit", 50))
    prospects = db.get_prospects_by_status(status, limit=limit)
    return jsonify(prospects)


@setter_bp.route("/api/metrics")
def api_metrics():
    days = int(request.args.get("days", 7))
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    metrics = db.get_metrics_range(start, end)
    return jsonify(metrics)
