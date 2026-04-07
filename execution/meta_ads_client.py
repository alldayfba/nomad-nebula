#!/usr/bin/env python3
"""
Meta Ads Client — MediaBuyer execution layer
Wraps the Meta Marketing API for use by the MediaBuyer agent.

Usage:
    python execution/meta_ads_client.py accounts
    python execution/meta_ads_client.py campaigns [--account act_XXX] [--days 30]
    python execution/meta_ads_client.py adsets --campaign CAMPAIGN_ID
    python execution/meta_ads_client.py ads --campaign CAMPAIGN_ID [--days 30]
    python execution/meta_ads_client.py insights --level campaign|adset|ad [--days 30]
    python execution/meta_ads_client.py audit [--days 30]
    python execution/meta_ads_client.py pause --id OBJECT_ID
    python execution/meta_ads_client.py budget --id ADSET_ID --amount 5000  (in cents)
    python execution/meta_ads_client.py rules --list
    python execution/meta_ads_client.py rules --create-kill-rules
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("META_ACCESS_TOKEN")
DEFAULT_ACCOUNT = os.getenv("META_AD_ACCOUNT_ID", "")
BASE_URL = "https://graph.facebook.com/v19.0"

# ── Benchmarks (from MediaBuyer agent directive) ──────────────────────────────
BENCHMARKS = {
    "ctr_warning": 1.0,          # CTR % below this = warning
    "frequency_cold_warning": 2.5,
    "frequency_retargeting_warning": 3.5,
    "cpm_warning": 17.0,         # Education/coaching CPM ceiling
    "roas_urgent": 3.0,          # Below this = urgent diagnosis
    "roas_scale": 4.0,           # Above this = scale
    "roas_3x": 10.0,             # Above this = scale 3x
}


def _get(path: str, params: dict | None = None) -> dict:
    """GET helper with token injection."""
    p = params or {}
    p["access_token"] = TOKEN
    r = requests.get(f"{BASE_URL}/{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, data: dict) -> dict:
    """POST helper with token injection."""
    data["access_token"] = TOKEN
    r = requests.post(f"{BASE_URL}/{path}", data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def get_accounts() -> list[dict]:
    """List all ad accounts accessible by this token."""
    data = _get("me/adaccounts", {
        "fields": "id,name,account_status,currency,amount_spent,spend_cap"
    })
    return data.get("data", [])


def _insights_params(days: int) -> dict:
    """Build time params. days=0 means all-time (2020-01-01 → today).
    Uses separators=(',',':') to avoid spaces that break URL encoding."""
    today = datetime.now().strftime("%Y-%m-%d")
    since = (datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d") if days == 0 else (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {"time_range": json.dumps({"since": since, "until": today}, separators=(",", ":"))}


INSIGHT_FIELDS = (
    "spend,impressions,clicks,ctr,cpm,cpc,frequency,reach,"
    "actions,cost_per_action_type,purchase_roas"
)


def get_campaigns(account_id: str, days: int = 30) -> list[dict]:
    """Get all campaigns with insights. days=0 = max history (~3 years)."""
    data = _get(f"{account_id}/campaigns", {
        "fields": "id,name,status,objective,budget_remaining,daily_budget,lifetime_budget,created_time,start_time",
        "limit": 100,
    })
    campaigns = data.get("data", [])
    params = _insights_params(days)
    for c in campaigns:
        try:
            ins = _get(f"{c['id']}/insights", {"fields": INSIGHT_FIELDS, **params})
            c["insights"] = {"data": ins.get("data", [])}
        except Exception as e:
            print(f"  [warn] insights failed for {c.get('name','?')}: {e}")
            c["insights"] = {"data": []}
    return campaigns


def get_adsets(campaign_id: str, days: int = 30) -> list[dict]:
    """Get all ad sets with targeting + insights. days=0 = lifetime."""
    data = _get(f"{campaign_id}/adsets", {
        "fields": "id,name,status,targeting,daily_budget,lifetime_budget,bid_strategy,created_time,optimization_goal,billing_event",
        "limit": 100,
    })
    adsets = data.get("data", [])
    params = _insights_params(days)
    for a in adsets:
        try:
            ins = _get(f"{a['id']}/insights", {"fields": INSIGHT_FIELDS, **params})
            a["insights"] = {"data": ins.get("data", [])}
        except Exception:
            a["insights"] = {"data": []}
    return adsets


def get_ads(campaign_id: str, days: int = 30) -> list[dict]:
    """Get all ads with creative details + insights. days=0 = lifetime."""
    data = _get(f"{campaign_id}/ads", {
        "fields": "id,name,status,created_time,creative{id,name,title,body,thumbnail_url,object_story_spec}",
        "limit": 200,
    })
    ads = data.get("data", [])
    params = _insights_params(days)
    for ad in ads:
        try:
            ins = _get(f"{ad['id']}/insights", {"fields": INSIGHT_FIELDS, **params})
            ad["insights"] = {"data": ins.get("data", [])}
        except Exception:
            ad["insights"] = {"data": []}
    return ads


def get_insights(account_id: str, level: str = "campaign", days: int = 30) -> list[dict]:
    """Pull full insights at campaign/adset/ad level for the account. days=0 = lifetime."""
    params = _insights_params(days)
    data = _get(f"{account_id}/insights", {
        "level": level,
        "fields": (
            "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
            "spend,impressions,clicks,ctr,cpm,cpc,frequency,reach,"
            "actions,cost_per_action_type,purchase_roas"
        ),
        "limit": 500,
        **params,
    })
    return data.get("data", [])


def pause_object(object_id: str) -> dict:
    """Pause a campaign, ad set, or ad."""
    return _post(object_id, {"status": "PAUSED"})


def activate_object(object_id: str) -> dict:
    """Activate (unpause) a campaign, ad set, or ad."""
    return _post(object_id, {"status": "ACTIVE"})


def update_budget(adset_id: str, daily_budget_cents: int) -> dict:
    """Update daily budget on an ad set (amount in cents, e.g. 5000 = $50)."""
    return _post(adset_id, {"daily_budget": str(daily_budget_cents)})


def create_campaign(account_id: str, name: str, objective: str = "OUTCOME_TRAFFIC",
                    buying_type: str = "AUCTION", special_ad_categories: list | None = None,
                    status: str = "PAUSED") -> dict:
    """Create a new campaign. Returns {'id': '...'}.
    Objective should be OUTCOME_TRAFFIC for profile funnel."""
    data = {
        "name": name,
        "objective": objective,
        "buying_type": buying_type,
        "special_ad_categories": json.dumps(special_ad_categories or []),
        "status": status,
    }
    return _post(f"{account_id}/campaigns", data)


def create_adset(account_id: str, campaign_id: str, name: str,
                 daily_budget_cents: int, optimization_goal: str = "LINK_CLICKS",
                 billing_event: str = "IMPRESSIONS",
                 targeting: dict | None = None,
                 promoted_object: dict | None = None,
                 status: str = "PAUSED") -> dict:
    """Create a new ad set under a campaign. Returns {'id': '...'}.

    For profile funnel:
    - optimization_goal: LINK_CLICKS (drives profile visits)
    - targeting: age 23-40, male, IG placements only
    - promoted_object: {"page_id": "195292677006314"}
    """
    default_targeting = {
        "age_min": 23,
        "age_max": 40,
        "genders": [1],  # Male
        "geo_locations": {"countries": ["US"]},
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "story", "reels", "profile_reels"],
    }
    data = {
        "campaign_id": campaign_id,
        "name": name,
        "daily_budget": str(daily_budget_cents),
        "optimization_goal": optimization_goal,
        "billing_event": billing_event,
        "targeting": json.dumps(targeting or default_targeting),
        "status": status,
    }
    if promoted_object:
        data["promoted_object"] = json.dumps(promoted_object)
    return _post(f"{account_id}/adsets", data)


def create_ad(account_id: str, adset_id: str, name: str,
              creative_id: str = "", post_id: str = "",
              status: str = "PAUSED") -> dict:
    """Create a new ad in an ad set.

    Use EITHER creative_id (existing creative) or post_id (organic post → ad).
    For profile funnel: use post_id from organic IG reel/post.
    """
    creative = {}
    if post_id:
        # Use an existing IG post as the ad creative
        creative = {"object_story_id": post_id}
    elif creative_id:
        creative = {"creative_id": creative_id}

    data = {
        "adset_id": adset_id,
        "name": name,
        "creative": json.dumps(creative),
        "status": status,
    }
    return _post(f"{account_id}/ads", data)


def create_nik_abo_campaign(account_id: str, creative_name: str,
                            post_id: str = "", creative_id: str = "",
                            daily_budget_cents: int = 2500,
                            interests: list | None = None) -> dict:
    """Create a full Nik Setting ABO test campaign with 3 ad sets.

    Structure:
    - Campaign: [ABO TEST] {creative_name} — Traffic objective
    - Ad Set 1: Broad (no interests) — $25/day
    - Ad Set 2: Interest-based — $25/day
    - Ad Set 3: Retargeting (IG engagers 180d) — $25/day
    - 1 ad per ad set using the same creative

    Returns dict with campaign_id, adset_ids, ad_ids.
    """
    page_id = "195292677006314"

    # 1. Create campaign
    campaign = create_campaign(
        account_id,
        name=f"[ABO TEST] {creative_name}",
        objective="OUTCOME_TRAFFIC",
        status="PAUSED"
    )
    campaign_id = campaign["id"]

    # Base targeting
    base = {
        "age_min": 23, "age_max": 40, "genders": [1],
        "geo_locations": {"countries": ["US"]},
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "story", "reels", "profile_reels"],
    }

    # Ad Set 1: Broad
    broad_targeting = {**base}
    adset_broad = create_adset(
        account_id, campaign_id,
        name=f"Broad — {creative_name}",
        daily_budget_cents=daily_budget_cents,
        targeting=broad_targeting,
        promoted_object={"page_id": page_id},
        status="PAUSED"
    )

    # Ad Set 2: Interest-based
    default_interests = interests or [
        {"id": "6003012455243", "name": "Entrepreneurship"},
        {"id": "6003384274667", "name": "E-commerce"},
        {"id": "6003107902433", "name": "Investment"},
        {"id": "6003029684094", "name": "Business"},
    ]
    interest_targeting = {
        **base,
        "flexible_spec": [{"interests": default_interests}],
    }
    adset_interest = create_adset(
        account_id, campaign_id,
        name=f"Interest — {creative_name}",
        daily_budget_cents=daily_budget_cents,
        targeting=interest_targeting,
        promoted_object={"page_id": page_id},
        status="PAUSED"
    )

    # Ad Set 3: Retargeting (IG engagers 180 days)
    # Note: Custom audiences need to be created separately in Business Manager
    # For now, use broad + exclude existing followers approach
    retarget_targeting = {
        **base,
        "age_min": 23, "age_max": 45,  # Slightly wider for retargeting
    }
    adset_retarget = create_adset(
        account_id, campaign_id,
        name=f"Retarget — {creative_name}",
        daily_budget_cents=daily_budget_cents,
        targeting=retarget_targeting,
        promoted_object={"page_id": page_id},
        status="PAUSED"
    )

    # Create 1 ad per ad set
    results = {"campaign_id": campaign_id, "adsets": [], "ads": []}
    for adset in [adset_broad, adset_interest, adset_retarget]:
        adset_id = adset["id"]
        results["adsets"].append(adset_id)
        ad = create_ad(
            account_id, adset_id,
            name=creative_name,
            post_id=post_id,
            creative_id=creative_id,
            status="PAUSED"
        )
        results["ads"].append(ad["id"])

    return results


def create_nik_cbo_campaign(account_id: str, creative_name: str,
                            post_id: str = "", creative_id: str = "",
                            daily_budget_cents: int = 10000) -> dict:
    """Create a Nik Setting CBO scale campaign.

    Structure:
    - Campaign: [CBO SCALE] {creative_name} — Traffic, CBO at $100+/day
    - 1 Ad Set: Broad targeting
    - 1 Ad: Winner creative via post ID
    """
    page_id = "195292677006314"

    # CBO campaign — budget at campaign level
    data = {
        "name": f"[CBO SCALE] {creative_name}",
        "objective": "OUTCOME_TRAFFIC",
        "buying_type": "AUCTION",
        "special_ad_categories": json.dumps([]),
        "status": "PAUSED",
        "daily_budget": str(daily_budget_cents),  # CBO: budget on campaign
    }
    campaign = _post(f"{account_id}/campaigns", data)
    campaign_id = campaign["id"]

    # Single broad ad set (no daily budget — inherits from campaign CBO)
    targeting = {
        "age_min": 23, "age_max": 40, "genders": [1],
        "geo_locations": {"countries": ["US"]},
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "story", "reels", "profile_reels"],
    }
    adset = _post(f"{account_id}/adsets", {
        "campaign_id": campaign_id,
        "name": f"Broad — {creative_name}",
        "optimization_goal": "LINK_CLICKS",
        "billing_event": "IMPRESSIONS",
        "targeting": json.dumps(targeting),
        "promoted_object": json.dumps({"page_id": page_id}),
        "status": "PAUSED",
        "access_token": TOKEN,
    })
    adset_id = adset["id"]

    # Single ad
    ad = create_ad(account_id, adset_id, creative_name,
                   post_id=post_id, creative_id=creative_id, status="PAUSED")

    return {"campaign_id": campaign_id, "adset_id": adset_id, "ad_id": ad["id"]}


def create_nik_story_campaign(account_id: str, creative_name: str,
                              image_hash: str = "",
                              daily_budget_cents: int = 1500) -> dict:
    """Create a Nik Setting Story Ads campaign.

    Story ads = image/text ONLY (no video).
    Destination: Instagram profile.
    """
    page_id = "195292677006314"
    ig_user_id = "17841453828932155"

    campaign = create_campaign(
        account_id,
        name=f"[STORY ADS] {creative_name}",
        objective="OUTCOME_TRAFFIC",
        status="PAUSED"
    )
    campaign_id = campaign["id"]

    targeting = {
        "age_min": 23, "age_max": 40, "genders": [1],
        "geo_locations": {"countries": ["US"]},
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["story"],
    }
    adset = create_adset(
        account_id, campaign_id,
        name=f"Story — {creative_name}",
        daily_budget_cents=daily_budget_cents,
        targeting=targeting,
        promoted_object={"page_id": page_id},
        status="PAUSED"
    )

    # For story ads, we create an ad creative with image + "View Profile" CTA
    creative_spec = {
        "object_story_spec": {
            "page_id": page_id,
            "instagram_user_id": ig_user_id,
            "link_data": {
                "link": "http://instagram.com/allday.fba",
                "message": "Follow @allday.fba to learn more",
                "call_to_action": {
                    "type": "VIEW_INSTAGRAM_PROFILE",
                    "value": {
                        "app_link": "instagram://user?username=allday.fba&userid=53937242297",
                        "link": "http://instagram.com/allday.fba"
                    }
                }
            }
        }
    }
    if image_hash:
        creative_spec["object_story_spec"]["link_data"]["image_hash"] = image_hash

    ad = _post(f"{account_id}/ads", {
        "adset_id": adset["id"],
        "name": creative_name,
        "creative": json.dumps(creative_spec),
        "status": "PAUSED",
        "access_token": TOKEN,
    })

    return {"campaign_id": campaign_id, "adset_id": adset["id"], "ad_id": ad["id"]}


def list_rules(account_id: str) -> list[dict]:
    """List all automated rules on the account."""
    data = _get(f"{account_id}/adrules_library", {
        "fields": "id,name,status,evaluation_spec,execution_spec"
    })
    return data.get("data", [])


def create_kill_rules(account_id: str) -> list[dict]:
    """
    Create standard kill rules based on MediaBuyer agent benchmarks.
    Rules: CTR < 1%, frequency > 2.5 cold, CPA runaway guard.
    """
    rules = [
        {
            "name": "[AUTO] Pause low CTR (<1%) after 3000 impressions",
            "evaluation_spec": json.dumps({
                "evaluation_type": "SCHEDULE",
                "schedule_spec": {"schedule": "SEMI_HOURLY"},
                "filters": [
                    {"field": "impressions", "value": ["3000"], "operator": "GREATER_THAN"},
                    {"field": "ctr", "value": ["1"], "operator": "LESS_THAN"},
                ]
            }),
            "execution_spec": json.dumps({
                "execution_type": "PAUSE"
            }),
            "status": "ENABLED",
        },
        {
            "name": "[AUTO] Pause high frequency cold (>2.5)",
            "evaluation_spec": json.dumps({
                "evaluation_type": "SCHEDULE",
                "schedule_spec": {"schedule": "SEMI_HOURLY"},
                "filters": [
                    {"field": "frequency", "value": ["2.5"], "operator": "GREATER_THAN"},
                ]
            }),
            "execution_spec": json.dumps({
                "execution_type": "PAUSE"
            }),
            "status": "ENABLED",
        },
        {
            "name": "[AUTO] Increase budget 20% when ROAS > 4.0 (3-day window)",
            "evaluation_spec": json.dumps({
                "evaluation_type": "SCHEDULE",
                "schedule_spec": {"schedule": "DAILY"},
                "filters": [
                    {"field": "purchase_roas", "value": ["4.0"], "operator": "GREATER_THAN"},
                ]
            }),
            "execution_spec": json.dumps({
                "execution_type": "CHANGE_BUDGET",
                "execution_options": [
                    {"field": "budget", "value": "20", "operator": "PERCENTAGE_INCREASE"}
                ]
            }),
            "status": "ENABLED",
        },
    ]
    results = []
    for rule in rules:
        rule["account_id"] = account_id
        try:
            res = _post(f"{account_id}/adrules_library", rule)
            results.append({"rule": rule["name"], "result": res})
        except Exception as e:
            results.append({"rule": rule["name"], "error": str(e)})
    return results


def _parse_insights(ins_data: list) -> dict:
    """Extract insight metrics from API response data list."""
    i = ins_data[0] if ins_data else {}
    roas_raw = i.get("purchase_roas", [])
    roas = 0.0
    if isinstance(roas_raw, list) and roas_raw:
        first = roas_raw[0]
        roas = float(first.get("value", 0)) if isinstance(first, dict) else 0.0

    # Extract action counts
    actions = i.get("actions", [])
    action_map: dict[str, int] = {}
    if isinstance(actions, list):
        for a in actions:
            if isinstance(a, dict):
                action_map[a.get("action_type", "")] = int(float(a.get("value", 0)))

    leads = action_map.get("lead", 0) + action_map.get("offsite_conversion.lead", 0)
    link_clicks = action_map.get("link_click", 0)
    post_engagement = action_map.get("post_engagement", 0)
    video_views = action_map.get("video_view", 0)

    return {
        "spend": float(i.get("spend", 0)),
        "impressions": int(i.get("impressions", 0)),
        "reach": int(i.get("reach", 0)),
        "clicks": int(i.get("clicks", 0)),
        "ctr": float(i.get("ctr", 0)),
        "cpm": float(i.get("cpm", 0)),
        "cpc": float(i.get("cpc", 0)),
        "frequency": float(i.get("frequency", 0)),
        "roas": roas,
        "leads": leads,
        "link_clicks": link_clicks,
        "post_engagement": post_engagement,
        "video_views": video_views,
        "unique_ctr": float(i.get("unique_ctr", 0)),
    }


def run_account_audit(account_id: str, days: int = 0) -> dict:
    """
    Full account audit per MediaBuyer protocol — campaign + adset + ad level.
    days=0 = lifetime (all time). Includes targeting, creative, Haynes stat chain.
    """
    label = "ALL TIME (Lifetime)" if days == 0 else f"Last {days} days"
    print(f"\n{'='*70}")
    print(f"  META ADS FULL AUDIT — {label}")
    print(f"  Account: {account_id}")
    print(f"{'='*70}\n")

    campaigns = get_campaigns(account_id, days)
    if not campaigns:
        return {"error": "No campaigns found"}

    kill_list = []
    scale_list = []
    watch_list = []
    total_spend = 0.0
    total_impressions = 0
    total_reach = 0
    total_leads = 0
    all_campaign_rows = []

    print(f"{'Campaign':<52} {'Status':<10} {'Spend':>9} {'CTR':>6} {'CPM':>7} {'Freq':>6} {'Leads':>6} {'ROAS':>7}")
    print("-" * 110)

    for c in campaigns:
        name = c.get("name", "Unknown")
        status = c.get("status", "UNKNOWN")
        created = c.get("created_time", "")[:10]
        ins_data = c.get("insights", {}).get("data", []) if c.get("insights") else []
        m = _parse_insights(ins_data)

        total_spend += m["spend"]
        total_impressions += m["impressions"]
        total_reach += m["reach"]
        total_leads += m["leads"]

        flags = []
        if m["ctr"] < BENCHMARKS["ctr_warning"] and m["impressions"] > 3000:
            flags.append(f"LOW CTR ({m['ctr']:.2f}%)")
        if m["frequency"] > BENCHMARKS["frequency_cold_warning"]:
            flags.append(f"HIGH FREQ ({m['frequency']:.1f})")
        if m["cpm"] > BENCHMARKS["cpm_warning"]:
            flags.append(f"HIGH CPM (${m['cpm']:.2f})")

        icon = "🟢" if not flags else "🔴"
        flag_str = "  ⚠ " + " | ".join(flags) if flags else ""
        print(f"  {icon} {name[:50]:<50} {status:<10} ${m['spend']:>8.2f} {m['ctr']:>5.2f}% ${m['cpm']:>5.2f} {m['frequency']:>5.2f}x {m['leads']:>6} {m['roas']:>6.2f}x{flag_str}")

        row = {"id": c["id"], "name": name, "status": status, "created": created, "metrics": m, "flags": flags}
        all_campaign_rows.append(row)

        if m["roas"] >= BENCHMARKS["roas_scale"] and m["spend"] > 0:
            scale_list.append(row)
        elif flags and m["spend"] > 0:
            kill_list.append(row)
        else:
            watch_list.append(row)

    print(f"\n  TOTALS: Spend ${total_spend:,.2f} | Impressions {total_impressions:,} | Reach {total_reach:,} | Leads {total_leads:,}")

    # ── Ad-level creative breakdown ──────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  CREATIVE PERFORMANCE — All Ads (ranked by spend)")
    print(f"{'='*70}\n")

    all_ads = []
    for c in campaigns:
        try:
            ads = get_ads(c["id"], days)
            for ad in ads:
                ad["_campaign_name"] = c.get("name", "")
                ad["_campaign_status"] = c.get("status", "")
            all_ads.extend(ads)
        except Exception:
            pass

    # Sort by spend descending
    def ad_spend(ad: dict) -> float:
        ins = ad.get("insights", {}).get("data", [])
        return _parse_insights(ins)["spend"]

    all_ads.sort(key=ad_spend, reverse=True)

    print(f"{'Ad Name':<45} {'Campaign':<30} {'Status':<10} {'Spend':>9} {'CTR':>6} {'CPM':>7} {'Freq':>6} {'Leads':>6}")
    print("-" * 125)

    top_creatives = []
    for ad in all_ads:
        ins_data = ad.get("insights", {}).get("data", [])
        m = _parse_insights(ins_data)
        if m["spend"] == 0 and m["impressions"] == 0:
            continue  # skip zero-activity ads

        ad_name = ad.get("name", "Unknown")[:44]
        camp_name = ad.get("_campaign_name", "")[:29]
        status = ad.get("status", "")

        creative = ad.get("creative", {})
        creative_body = creative.get("body", "") if isinstance(creative, dict) else ""

        flags = []
        if m["ctr"] < BENCHMARKS["ctr_warning"] and m["impressions"] > 3000:
            flags.append("LOW CTR")
        if m["frequency"] > BENCHMARKS["frequency_cold_warning"]:
            flags.append("HIGH FREQ")
        if m["cpm"] > BENCHMARKS["cpm_warning"]:
            flags.append("HIGH CPM")

        icon = "🟢" if not flags else "🔴"
        flag_str = "  ⚠ " + "|".join(flags) if flags else ""
        print(f"  {icon} {ad_name:<44} {camp_name:<30} {status:<10} ${m['spend']:>8.2f} {m['ctr']:>5.2f}% ${m['cpm']:>5.2f} {m['frequency']:>5.2f}x {m['leads']:>6}{flag_str}")

        top_creatives.append({
            "id": ad.get("id"),
            "name": ad.get("name"),
            "campaign": ad.get("_campaign_name"),
            "status": status,
            "metrics": m,
            "flags": flags,
            "body_preview": creative_body[:100] if creative_body else "",
        })

    # ── Audience targeting summary ───────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  AUDIENCE TARGETING — Ad Set Summary")
    print(f"{'='*70}\n")

    all_adsets = []
    for c in campaigns:
        try:
            adsets = get_adsets(c["id"], days)
            for ads in adsets:
                ads["_campaign_name"] = c.get("name", "")
            all_adsets.extend(adsets)
        except Exception:
            pass

    for adset in all_adsets:
        ins_data = adset.get("insights", {}).get("data", [])
        m = _parse_insights(ins_data)
        if m["spend"] == 0:
            continue

        targeting = adset.get("targeting", {})
        age_min = targeting.get("age_min", "?") if isinstance(targeting, dict) else "?"
        age_max = targeting.get("age_max", "?") if isinstance(targeting, dict) else "?"
        genders = targeting.get("genders", []) if isinstance(targeting, dict) else []
        gender_str = {1: "M", 2: "F"}.get(genders[0], "All") if genders else "All"

        interests = []
        flex = targeting.get("flexible_spec", []) if isinstance(targeting, dict) else []
        if isinstance(flex, list):
            for spec in flex:
                if isinstance(spec, dict):
                    for item in spec.get("interests", []):
                        if isinstance(item, dict):
                            interests.append(item.get("name", ""))

        geo = targeting.get("geo_locations", {}) if isinstance(targeting, dict) else {}
        countries = geo.get("countries", []) if isinstance(geo, dict) else []
        geo_str = ", ".join(countries[:3]) if countries else "Broad"

        print(f"  📍 {adset.get('name','')[:50]}")
        print(f"     Campaign: {adset.get('_campaign_name','')[:50]}")
        print(f"     Spend: ${m['spend']:.2f} | CTR: {m['ctr']:.2f}% | CPM: ${m['cpm']:.2f} | Freq: {m['frequency']:.2f}x | Leads: {m['leads']}")
        print(f"     Age: {age_min}–{age_max} | Gender: {gender_str} | Geo: {geo_str}")
        if interests:
            print(f"     Interests: {', '.join(interests[:8])}")
        print()

    # ── Summary report ───────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  AUDIT SUMMARY")
    print(f"{'='*70}")
    print(f"\n  Total Spend (all time):  ${total_spend:,.2f}")
    print(f"  Total Impressions:       {total_impressions:,}")
    print(f"  Total Reach:             {total_reach:,}")
    print(f"  Total Leads:             {total_leads:,}")
    if total_leads > 0 and total_spend > 0:
        print(f"  Avg Cost Per Lead:       ${total_spend / total_leads:.2f}")

    print(f"\n  🔴 KILL LIST ({len(kill_list)} campaigns with spend + flags):")
    for item in kill_list:
        raw_flags = item.get("flags")
        fs = ", ".join(str(f) for f in (raw_flags if isinstance(raw_flags, list) else []))
        print(f"     ❌ {item['name']} — {fs}")

    print(f"\n  🚀 SCALE LIST ({len(scale_list)} campaigns ROAS ≥ {BENCHMARKS['roas_scale']}x):")
    for item in scale_list:
        print(f"     ✅ {item['name']} — ROAS {item['metrics']['roas']:.2f}x")

    # Top 5 creatives by spend
    print(f"\n  🎨 TOP 5 CREATIVES BY SPEND:")
    for i, cr in enumerate(top_creatives[:5], 1):
        print(f"     {i}. {cr['name']} — ${cr['metrics']['spend']:.2f} | CTR {cr['metrics']['ctr']:.2f}% | CPM ${cr['metrics']['cpm']:.2f}")

    print()

    return {
        "total_spend": total_spend,
        "total_impressions": total_impressions,
        "total_reach": total_reach,
        "total_leads": total_leads,
        "campaigns": len(campaigns),
        "kill_list": kill_list,
        "scale_list": scale_list,
        "top_creatives": top_creatives[:10],
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Meta Ads Client — MediaBuyer execution layer")
    parser.add_argument("command", choices=[
        "accounts", "campaigns", "adsets", "ads", "insights", "audit",
        "pause", "activate", "budget", "rules",
        "create-campaign", "create-adset", "create-ad",
        "create-abo", "create-cbo", "create-story",
    ])
    parser.add_argument("--account", default=DEFAULT_ACCOUNT, help="Ad account ID (act_XXX)")
    parser.add_argument("--campaign", help="Campaign ID for adsets/ads")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--level", default="campaign", choices=["campaign", "adset", "ad"])
    parser.add_argument("--id", help="Object ID for pause/budget commands")
    parser.add_argument("--amount", type=int, help="Budget amount in cents (e.g. 5000 = $50)")
    parser.add_argument("--list", action="store_true", help="List rules")
    parser.add_argument("--create-kill-rules", action="store_true", help="Create standard kill rules")
    # Campaign/adset/ad creation args
    parser.add_argument("--name", help="Name for campaign/adset/ad")
    parser.add_argument("--objective", default="OUTCOME_TRAFFIC", help="Campaign objective")
    parser.add_argument("--post-id", help="Organic IG post ID to use as ad creative")
    parser.add_argument("--creative-id", help="Existing creative ID")
    parser.add_argument("--image-hash", help="Image hash for story ads")
    parser.add_argument("--adset", help="Ad set ID for ad creation")
    parser.add_argument("--status", default="PAUSED", help="Initial status (PAUSED or ACTIVE)")
    args = parser.parse_args()

    if not TOKEN:
        print("ERROR: META_ACCESS_TOKEN not set in .env")
        sys.exit(1)

    account = args.account or DEFAULT_ACCOUNT
    if not account and args.command not in ("accounts",):
        print("ERROR: META_AD_ACCOUNT_ID not set. Use --account act_XXX or set in .env")
        sys.exit(1)

    if args.command == "accounts":
        accounts = get_accounts()
        status_map = {1: "ACTIVE", 2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW", 9: "IN_GRACE_PERIOD"}
        print(f"\n{'ID':<30} {'Name':<35} {'Status':<12} {'Total Spent':>12}")
        print("-" * 95)
        for a in accounts:
            spent = float(a.get("amount_spent", 0)) / 100
            s = status_map.get(a.get("account_status", 0), str(a.get("account_status")))
            print(f"{a['id']:<30} {a.get('name',''):<35} {s:<12} ${spent:>11,.2f}")

    elif args.command == "campaigns":
        campaigns = get_campaigns(account, args.days)
        print(json.dumps(campaigns, indent=2))

    elif args.command == "adsets":
        if not args.campaign:
            print("ERROR: --campaign required for adsets command")
            sys.exit(1)
        adsets = get_adsets(args.campaign, args.days)
        print(json.dumps(adsets, indent=2))

    elif args.command == "ads":
        if not args.campaign:
            print("ERROR: --campaign required for ads command")
            sys.exit(1)
        ads = get_ads(args.campaign, args.days)
        print(json.dumps(ads, indent=2))

    elif args.command == "insights":
        insights = get_insights(account, args.level, args.days)
        print(json.dumps(insights, indent=2))

    elif args.command == "audit":
        result = run_account_audit(account, args.days)
        print(f"\nAudit complete. {result['campaigns']} campaigns, ${result['total_spend']:.2f} spend.")

    elif args.command == "pause":
        if not args.id:
            print("ERROR: --id required")
            sys.exit(1)
        result = pause_object(args.id)
        print(f"Paused {args.id}: {result}")

    elif args.command == "activate":
        if not args.id:
            print("ERROR: --id required")
            sys.exit(1)
        result = activate_object(args.id)
        print(f"Activated {args.id}: {result}")

    elif args.command == "budget":
        if not args.id or not args.amount:
            print("ERROR: --id and --amount required")
            sys.exit(1)
        result = update_budget(args.id, args.amount)
        print(f"Updated budget for {args.id}: {result}")

    elif args.command == "create-campaign":
        if not args.name:
            print("ERROR: --name required")
            sys.exit(1)
        result = create_campaign(account, args.name, args.objective, status=args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "create-adset":
        if not args.campaign or not args.name or not args.amount:
            print("ERROR: --campaign, --name, --amount required")
            sys.exit(1)
        result = create_adset(account, args.campaign, args.name,
                              daily_budget_cents=args.amount, status=args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "create-ad":
        if not args.adset or not args.name:
            print("ERROR: --adset, --name required")
            sys.exit(1)
        result = create_ad(account, args.adset, args.name,
                           creative_id=args.creative_id or "",
                           post_id=args.post_id or "",
                           status=args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "create-abo":
        if not args.name:
            print("ERROR: --name required (creative name)")
            sys.exit(1)
        result = create_nik_abo_campaign(
            account, args.name,
            post_id=args.post_id or "",
            creative_id=args.creative_id or "",
            daily_budget_cents=args.amount or 2500,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "create-cbo":
        if not args.name:
            print("ERROR: --name required (creative name)")
            sys.exit(1)
        result = create_nik_cbo_campaign(
            account, args.name,
            post_id=args.post_id or "",
            creative_id=args.creative_id or "",
            daily_budget_cents=args.amount or 10000,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "create-story":
        if not args.name:
            print("ERROR: --name required (creative name)")
            sys.exit(1)
        result = create_nik_story_campaign(
            account, args.name,
            image_hash=args.image_hash or "",
            daily_budget_cents=args.amount or 1500,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "rules":
        if args.create_kill_rules:
            results = create_kill_rules(account)
            print(json.dumps(results, indent=2))
        else:
            rules = list_rules(account)
            print(json.dumps(rules, indent=2))


if __name__ == "__main__":
    main()
