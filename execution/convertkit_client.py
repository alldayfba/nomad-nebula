#!/usr/bin/env python3
"""
ConvertKit API Client — add subscribers and manage tags.

Gracefully skips if CONVERTKIT_API_KEY is not set (logs warning, returns skipped).

Usage:
    from execution.convertkit_client import add_subscriber

    result = add_subscriber(
        email="test@example.com",
        first_name="John",
        tags=["webinar-opt-in"],
    )
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger("convertkit-client")

CK_BASE = "https://api.convertkit.com/v4"
TIMEOUT = 10


def _get_api_key() -> str:
    key = os.environ.get("CONVERTKIT_API_KEY", "")
    if not key:
        logger.warning("CONVERTKIT_API_KEY not set — skipping ConvertKit operations")
    return key


def _get_api_secret() -> str:
    return os.environ.get("CONVERTKIT_API_SECRET", "")


def add_subscriber(
    email: str,
    first_name: str = "",
    fields: dict | None = None,
    tags: list | None = None,
    form_id: str = "",
) -> dict:
    """Add a subscriber to ConvertKit.

    If CONVERTKIT_API_KEY is not set, returns {"skipped": True} without error.

    Args:
        email: Subscriber email (required)
        first_name: Subscriber first name
        fields: Custom field key-value pairs
        tags: List of tag names to apply
        form_id: Optional form ID to subscribe to (uses /forms/{id}/subscribe)
    """
    api_secret = _get_api_secret()
    api_key = _get_api_key()

    if not api_key and not api_secret:
        return {"ok": True, "skipped": True, "reason": "CONVERTKIT_API_KEY not set"}

    # Use v3 API with api_secret for form subscription (more reliable)
    if form_id and api_secret:
        url = f"https://api.convertkit.com/v3/forms/{form_id}/subscribe"
        payload = {
            "api_secret": api_secret,
            "email": email,
        }
        if first_name:
            payload["first_name"] = first_name
        if fields:
            payload["fields"] = fields
        if tags:
            payload["tags"] = tags
    elif api_key:
        # v4 API with Bearer token
        url = f"{CK_BASE}/subscribers"
        payload = {"email_address": email}
        if first_name:
            payload["first_name"] = first_name
        if fields:
            payload["fields"] = fields
    else:
        return {"ok": True, "skipped": True, "reason": "No API credentials"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")

    # Auth header for v4
    if not form_id and api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        result = json.loads(resp.read().decode("utf-8"))
        subscriber_id = result.get("subscriber", {}).get("id", "")
        logger.info(f"[convertkit] Added subscriber {email} (id={subscriber_id})")

        # Tag subscriber if tags provided and using v4
        if tags and api_key and not form_id:
            for tag_name in tags:
                _tag_subscriber(api_key, email, tag_name)

        return {"ok": True, "subscriber_id": subscriber_id, "skipped": False}

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(f"[convertkit] Error adding {email}: {e.code} — {error_body[:200]}")
        return {"ok": False, "error": error_body[:200], "skipped": False}
    except Exception as e:
        logger.error(f"[convertkit] Error adding {email}: {e}")
        return {"ok": False, "error": str(e), "skipped": False}


def _tag_subscriber(api_key: str, email: str, tag_name: str) -> None:
    """Tag a subscriber by email (v4 API)."""
    try:
        # First find tag ID by name
        url = f"{CK_BASE}/tags?api_key={api_key}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {api_key}")
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        tags_data = json.loads(resp.read().decode("utf-8"))

        tag_id = None
        for tag in tags_data.get("tags", []):
            if tag.get("name", "").lower() == tag_name.lower():
                tag_id = tag.get("id")
                break

        if tag_id:
            url = f"{CK_BASE}/tags/{tag_id}/subscribers"
            payload = json.dumps({"email_address": email}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=TIMEOUT)
            logger.info(f"[convertkit] Tagged {email} with '{tag_name}'")
    except Exception as e:
        logger.warning(f"[convertkit] Failed to tag {email} with '{tag_name}': {e}")
