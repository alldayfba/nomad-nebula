#!/usr/bin/env python3
from __future__ import annotations
"""
Script: velocity_analyzer.py
Purpose: Compute real sell-through velocity from Keepa data.

         Two paths:
         - Cheap (1 token): BSR trend + FBA seller count trend → proxy velocity
         - Expensive (21 tokens): Parse stockCSV per-seller → actual units sold

         Key insight from StartUpFBA: Keepa's graphs are drawn from raw data.
         The API returns those inventory snapshots. Stock drops = confirmed sales.
         Most useful for ASINs selling 0-49 units/month (no "100+ bought" badge).

Usage:
    from velocity_analyzer import analyze_velocity, score_velocity
    velocity = analyze_velocity(keepa_product, mode="cheap")
    confidence = score_velocity(velocity)
"""

import time

# Keepa epoch: 2011-01-01 00:00 UTC
KEEPA_EPOCH = 1293840000


def keepa_ts_to_unix(keepa_ts: int) -> float:
    """Convert Keepa minute-based timestamp to Unix seconds."""
    return KEEPA_EPOCH + (keepa_ts * 60)


# ── Cheap Velocity (1 token — from stats/csv data) ──────────────────────────


def compute_velocity_from_bsr(bsr_csv: list, days: int = 90) -> dict:
    """Estimate velocity from BSR (Best Sellers Rank) time-series.

    BSR going DOWN = more sales (better rank = higher velocity).
    BSR going UP = fewer sales.

    Args:
        bsr_csv: Keepa CSV array for index 3 (sales rank). Format: [ts, rank, ts, rank, ...]
        days: How many days back to analyze.

    Returns:
        dict with bsr_trend, avg_bsr, bsr_improvement_pct, velocity_signal
    """
    if not bsr_csv or len(bsr_csv) < 4:
        return {"bsr_trend": "unknown", "velocity_signal": 0}

    cutoff = time.time() - (days * 86400)

    # Parse pairs
    pairs = []
    for i in range(0, len(bsr_csv) - 1, 2):
        ts_keepa = bsr_csv[i]
        rank = bsr_csv[i + 1]
        if ts_keepa < 0 or rank < 0:
            continue
        unix_ts = keepa_ts_to_unix(ts_keepa)
        if unix_ts >= cutoff:
            pairs.append((unix_ts, rank))

    if len(pairs) < 2:
        return {"bsr_trend": "unknown", "velocity_signal": 0}

    ranks = [r for _, r in pairs]
    avg_bsr = sum(ranks) / len(ranks)

    # Compare first third vs last third
    third = max(1, len(ranks) // 3)
    early_avg = sum(ranks[:third]) / third
    late_avg = sum(ranks[-third:]) / third

    if early_avg > 0:
        improvement_pct = ((early_avg - late_avg) / early_avg) * 100
    else:
        improvement_pct = 0

    # Trend
    if improvement_pct > 15:
        trend = "improving"  # BSR going down = more sales
    elif improvement_pct < -15:
        trend = "declining"  # BSR going up = fewer sales
    else:
        trend = "stable"

    # Velocity signal: 0-100 based on BSR level and trend
    signal = 0
    if avg_bsr < 10000:
        signal = 90
    elif avg_bsr < 50000:
        signal = 70
    elif avg_bsr < 100000:
        signal = 50
    elif avg_bsr < 200000:
        signal = 30
    elif avg_bsr < 500000:
        signal = 15
    else:
        signal = 5

    # Boost/penalize based on trend
    if trend == "improving":
        signal = min(100, signal + 15)
    elif trend == "declining":
        signal = max(0, signal - 15)

    return {
        "bsr_trend": trend,
        "avg_bsr": round(avg_bsr),
        "current_bsr": ranks[-1] if ranks else None,
        "bsr_improvement_pct": round(improvement_pct, 1),
        "data_points": len(pairs),
        "velocity_signal": signal,
    }


def compute_velocity_from_fba_count(fba_csv: list, days: int = 90) -> dict:
    """Estimate velocity stability from FBA seller count trend.

    Stable FBA count = healthy marketplace. Declining = sellers leaving (could be
    negative signal OR opportunity). Rising = more competition.

    Args:
        fba_csv: Keepa CSV array for index 34 (FBA seller count).

    Returns:
        dict with fba_trend, avg_fba_count, competition_signal
    """
    if not fba_csv or len(fba_csv) < 4:
        return {"fba_trend": "unknown", "competition_signal": 50}

    cutoff = time.time() - (days * 86400)

    pairs = []
    for i in range(0, len(fba_csv) - 1, 2):
        ts_keepa = fba_csv[i]
        count = fba_csv[i + 1]
        if ts_keepa < 0:
            continue
        count = max(0, count)  # Keepa uses -1 for no data
        unix_ts = keepa_ts_to_unix(ts_keepa)
        if unix_ts >= cutoff:
            pairs.append((unix_ts, count))

    if not pairs:
        return {"fba_trend": "unknown", "competition_signal": 50}

    counts = [c for _, c in pairs]
    avg_count = sum(counts) / len(counts)
    current_count = counts[-1]

    # Trend
    third = max(1, len(counts) // 3)
    early_avg = sum(counts[:third]) / third
    late_avg = sum(counts[-third:]) / third

    if early_avg > 0:
        change_pct = ((late_avg - early_avg) / early_avg) * 100
    else:
        change_pct = 0

    if change_pct > 20:
        trend = "increasing"  # More sellers entering
    elif change_pct < -20:
        trend = "declining"  # Sellers leaving
    else:
        trend = "stable"

    # Competition signal: sweet spot is 3-8 FBA sellers
    if 3 <= current_count <= 8:
        comp_signal = 100  # Ideal competition level
    elif current_count == 1 or current_count == 2:
        comp_signal = 60  # Low competition but possible PL
    elif 9 <= current_count <= 15:
        comp_signal = 50  # Getting crowded
    elif current_count > 15:
        comp_signal = 20  # Very competitive
    else:
        comp_signal = 30  # 0 sellers = possible issue

    return {
        "fba_trend": trend,
        "avg_fba_count": round(avg_count, 1),
        "current_fba_count": current_count,
        "fba_change_pct": round(change_pct, 1),
        "competition_signal": comp_signal,
    }


# ── Expensive Velocity (21 tokens — from offers/stockCSV) ───────────────────


def compute_velocity_from_stock(stock_csv: list, days: int = 90) -> dict:
    """Compute actual units sold from a single seller's stockCSV.

    stockCSV format: [keepa_ts, quantity, keepa_ts, quantity, ...]
    A drop in quantity between readings = units sold.

    Args:
        stock_csv: stockCSV array from a single offer.
        days: How many days back to analyze.

    Returns:
        dict with units_sold, velocity_per_day, restocks, data_quality
    """
    if not stock_csv or len(stock_csv) < 4:
        return {"units_sold": 0, "velocity_per_day": 0, "data_quality": "insufficient"}

    cutoff = time.time() - (days * 86400)

    # Parse pairs
    pairs = []
    for i in range(0, len(stock_csv) - 1, 2):
        ts_keepa = stock_csv[i]
        qty = stock_csv[i + 1]
        if ts_keepa < 0:
            continue
        unix_ts = keepa_ts_to_unix(ts_keepa)
        if unix_ts >= cutoff and qty >= 0:
            pairs.append((unix_ts, qty))

    if len(pairs) < 2:
        return {"units_sold": 0, "velocity_per_day": 0, "data_quality": "insufficient"}

    # Count stock drops (= sales) and restocks
    total_units_sold = 0
    restocks = 0
    for i in range(1, len(pairs)):
        prev_qty = pairs[i - 1][1]
        curr_qty = pairs[i][1]
        delta = prev_qty - curr_qty

        if delta > 0:
            total_units_sold += delta  # Stock decreased = units sold
        elif delta < -2:
            restocks += 1  # Stock increased significantly = restock

    # Time span
    time_span_days = (pairs[-1][0] - pairs[0][0]) / 86400
    if time_span_days < 1:
        time_span_days = 1

    velocity_per_day = total_units_sold / time_span_days
    velocity_per_month = velocity_per_day * 30

    # Data quality assessment
    if len(pairs) > 20:
        quality = "good"
    elif len(pairs) > 5:
        quality = "moderate"
    else:
        quality = "limited"

    return {
        "units_sold": total_units_sold,
        "velocity_per_day": round(velocity_per_day, 2),
        "velocity_per_month": round(velocity_per_month, 1),
        "restocks": restocks,
        "data_points": len(pairs),
        "time_span_days": round(time_span_days, 1),
        "data_quality": quality,
    }


def compute_velocity_from_offers(offers_data: list[dict], days: int = 90) -> dict:
    """Aggregate velocity across all FBA sellers on a listing.

    Args:
        offers_data: List of seller dicts from keepa_client.parse_offers().
                     Each seller should have raw offer data with stockCSV.

    Returns:
        dict with total_velocity, seller_velocities, confidence
    """
    seller_velocities = []
    total_units = 0

    for offer in offers_data:
        stock_csv = offer.get("stockCSV") or offer.get("stock_csv", [])
        if not stock_csv:
            continue

        vel = compute_velocity_from_stock(stock_csv, days=days)
        if vel["units_sold"] > 0:
            seller_velocities.append({
                "seller_name": offer.get("seller_name", "unknown"),
                "seller_id": offer.get("seller_id", ""),
                "is_fba": offer.get("is_fba", False),
                **vel,
            })
            total_units += vel["units_sold"]

    time_span = max(v["time_span_days"] for v in seller_velocities) if seller_velocities else days
    total_velocity_monthly = (total_units / max(time_span, 1)) * 30

    return {
        "total_units_sold": total_units,
        "total_velocity_monthly": round(total_velocity_monthly, 1),
        "seller_count_with_data": len(seller_velocities),
        "seller_velocities": seller_velocities,
        "confidence": "high" if len(seller_velocities) >= 2 else ("medium" if seller_velocities else "none"),
    }


# ── Combined Analyzer ────────────────────────────────────────────────────────


def analyze_velocity(keepa_product: dict, mode: str = "cheap") -> dict:
    """Analyze velocity for a Keepa product.

    Args:
        keepa_product: Raw Keepa product dict (from get_product() or batch lookup).
        mode: "cheap" (BSR + FBA count, 0 extra tokens) or
              "deep" (stockCSV from offers, requires offers data already fetched).

    Returns:
        dict with velocity_score (0-100), velocity_monthly_est, details
    """
    csv_data = keepa_product.get("csv", [])

    # ── Always compute BSR velocity (cheap) ─────────────────────────────
    bsr_csv = csv_data[3] if csv_data and len(csv_data) > 3 else []
    bsr_velocity = compute_velocity_from_bsr(bsr_csv)

    # ── Always compute FBA count signal ─────────────────────────────────
    fba_csv = csv_data[34] if csv_data and len(csv_data) > 34 else []
    fba_velocity = compute_velocity_from_fba_count(fba_csv)

    # ── Monthly sales estimate from BSR ─────────────────────────────────
    current_bsr = bsr_velocity.get("current_bsr")
    monthly_est = _bsr_to_monthly_sales(current_bsr) if current_bsr else None

    result = {
        "bsr": bsr_velocity,
        "fba_competition": fba_velocity,
        "monthly_sales_estimate": monthly_est,
        "velocity_score": 0,
        "mode": mode,
    }

    # ── Deep mode: add stockCSV analysis ────────────────────────────────
    if mode == "deep":
        offers = keepa_product.get("offers", [])
        if offers:
            offers_velocity = compute_velocity_from_offers(offers)
            result["offers_velocity"] = offers_velocity
            if offers_velocity["total_velocity_monthly"] > 0:
                result["monthly_sales_estimate"] = offers_velocity["total_velocity_monthly"]

    # ── Compute combined velocity score ─────────────────────────────────
    result["velocity_score"] = _compute_combined_score(result)

    return result


def _bsr_to_monthly_sales(bsr: int) -> int:
    """Quick BSR to monthly sales estimate. Matches calculate_fba_profitability.py."""
    tiers = [
        (50, 5000), (100, 3000), (500, 1500), (1000, 800),
        (5000, 300), (10000, 150), (25000, 80), (50000, 40),
        (100000, 20), (200000, 10), (500000, 5), (1000000, 2),
    ]
    for max_rank, sales in tiers:
        if bsr <= max_rank:
            return sales
    return 1


def _compute_combined_score(velocity_data: dict) -> int:
    """Compute combined velocity score (0-100) from all signals."""
    bsr_signal = velocity_data.get("bsr", {}).get("velocity_signal", 0)
    comp_signal = velocity_data.get("fba_competition", {}).get("competition_signal", 50)

    # Base score from BSR (60% weight) + competition (40% weight)
    score = (bsr_signal * 0.6) + (comp_signal * 0.4)

    # Boost from deep analysis if available
    offers_vel = velocity_data.get("offers_velocity", {})
    if offers_vel.get("confidence") == "high":
        monthly = offers_vel.get("total_velocity_monthly", 0)
        if monthly > 100:
            score = min(100, score + 15)
        elif monthly > 30:
            score = min(100, score + 10)
        elif monthly > 10:
            score = min(100, score + 5)

    return min(100, max(0, round(score)))


# ── Confidence Scoring (for catalog pipeline) ────────────────────────────────


def score_confidence(roi_pct: float, velocity_data: dict, bsr: int | None,
                     fba_count: int | None, price_stability: float = 50) -> dict:
    """Compute overall buy confidence score for a catalog candidate.

    StartUpFBA's insight: if 70%+ of historical sales are profitable, it's a buy.
    We adapt this into a weighted multi-signal score.

    Args:
        roi_pct: Return on investment percentage.
        velocity_data: Output from analyze_velocity().
        bsr: Current BSR.
        fba_count: Current FBA seller count.
        price_stability: 0-100 score (100 = very stable price).

    Returns:
        dict with score (0-100), verdict (BUY/MAYBE/RESEARCH/SKIP), breakdown
    """
    # ROI score (25%)
    if roi_pct >= 100:
        roi_score = 100
    elif roi_pct >= 50:
        roi_score = 70
    elif roi_pct >= 30:
        roi_score = 40
    elif roi_pct >= 15:
        roi_score = 20
    else:
        roi_score = 5

    # Velocity score (25%)
    vel_score = velocity_data.get("velocity_score", 0)

    # BSR score (20%)
    if not bsr or bsr <= 0:
        bsr_score = 0
    elif bsr < 50000:
        bsr_score = 100
    elif bsr < 100000:
        bsr_score = 70
    elif bsr < 200000:
        bsr_score = 40
    elif bsr < 500000:
        bsr_score = 20
    else:
        bsr_score = 5

    # Competition score (15%)
    if fba_count is None:
        comp_score = 30
    elif 3 <= fba_count <= 8:
        comp_score = 100
    elif fba_count == 1 or fba_count == 2:
        comp_score = 60
    elif 9 <= fba_count <= 15:
        comp_score = 50
    elif fba_count > 15:
        comp_score = 20
    else:
        comp_score = 30

    # Price stability (15%)
    stab_score = min(100, max(0, price_stability))

    # Weighted sum
    total = (
        roi_score * 0.25
        + vel_score * 0.25
        + bsr_score * 0.20
        + comp_score * 0.15
        + stab_score * 0.15
    )
    total = round(min(100, max(0, total)))

    # Verdict
    if total >= 70:
        verdict = "BUY"
    elif total >= 50:
        verdict = "MAYBE"
    elif total >= 30:
        verdict = "RESEARCH"
    else:
        verdict = "SKIP"

    return {
        "score": total,
        "verdict": verdict,
        "breakdown": {
            "roi": {"score": roi_score, "weight": 0.25, "value": roi_pct},
            "velocity": {"score": vel_score, "weight": 0.25},
            "bsr": {"score": bsr_score, "weight": 0.20, "value": bsr},
            "competition": {"score": comp_score, "weight": 0.15, "value": fba_count},
            "price_stability": {"score": stab_score, "weight": 0.15},
        },
    }
