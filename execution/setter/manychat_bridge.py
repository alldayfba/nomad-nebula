"""
ManyChat bridge — webhook handler for keyword triggers from stories/reels.

When someone triggers a keyword in ManyChat (e.g., "AMAZON", "FBA"),
ManyChat fires a webhook to our Flask app. This module creates the prospect
record and queues them for setter qualification.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from .setter_config import MANYCHAT_KEYWORDS
from . import setter_db as db

logger = logging.getLogger("setter.manychat")


def handle_manychat_webhook(payload: Dict) -> Dict:
    """Process a ManyChat webhook payload.

    Expected payload fields (from ManyChat Custom Fields or Flow):
    - ig_handle: str (Instagram username)
    - keyword: str (the trigger keyword, e.g., "AMAZON")
    - name: str (optional, subscriber name)
    - email: str (optional, if collected)

    Returns: {status: str, prospect_id: int, message: str}
    """
    ig_handle = payload.get("ig_handle") or payload.get("username") or ""
    keyword = (payload.get("keyword") or payload.get("trigger") or "").upper().strip()
    name = payload.get("name") or payload.get("full_name") or ""
    email = payload.get("email") or ""

    if not ig_handle:
        return {"status": "error", "prospect_id": 0, "message": "No ig_handle provided"}

    ig_handle = ig_handle.lstrip("@").strip()

    # Look up keyword config
    kw_config = MANYCHAT_KEYWORDS.get(keyword, {})
    offer = kw_config.get("offer", "amazon_os")
    warmth = kw_config.get("warmth", "medium")

    # Create or update prospect
    prospect_id = db.upsert_prospect(
        ig_handle=ig_handle,
        source="manychat_keyword",
        source_detail=f"keyword:{keyword}",
        full_name=name or None,
        email_from_bio=email or None,
        offer_match=offer,
        icp_score=7 if warmth == "high" else 5,  # Pre-score based on intent
        icp_reasoning=f"Triggered ManyChat keyword '{keyword}' (warmth: {warmth})",
    )

    # Check if already in conversation
    existing = db.get_conversation_by_prospect(prospect_id)
    if existing:
        # Update the existing conversation context — they just showed more intent
        logger.info("ManyChat trigger for existing prospect @%s (keyword: %s)",
                     ig_handle, keyword)
        return {
            "status": "existing",
            "prospect_id": prospect_id,
            "message": f"Prospect @{ig_handle} already in conversation (stage: {existing['stage']})",
        }

    # Mark as qualified (they self-selected by triggering the keyword)
    db.update_prospect_status(prospect_id, "qualified")
    db.increment_metric("prospects_qualified")

    logger.info("New ManyChat prospect: @%s (keyword: %s, offer: %s)",
                 ig_handle, keyword, offer)

    return {
        "status": "created",
        "prospect_id": prospect_id,
        "message": f"Prospect @{ig_handle} created and qualified (keyword: {keyword})",
    }


def get_flask_route():
    """Return Flask route handler for ManyChat webhooks.

    Add to app.py:
        from execution.setter.manychat_bridge import get_flask_route
        app.add_url_rule('/webhooks/manychat', 'manychat_webhook',
                         get_flask_route(), methods=['POST'])
    """
    from flask import request, jsonify

    def manychat_webhook():
        payload = request.get_json(force=True, silent=True) or {}
        result = handle_manychat_webhook(payload)
        return jsonify(result), 200 if result["status"] != "error" else 400

    return manychat_webhook
