"""Keepa analysis orchestrator for Nova.

Thin wrapper over KeepaClient + calculate_product_profitability that:
- Caches deep lookups in nova.db (1hr TTL) to save tokens on repeat questions
- Layers MOQ capital / cash-at-risk / payback math when a quantity is given
- Flags "reviews may be cooked" when the recent 1★ ratio is concerning
- Sanitizes its return shape so nothing passed to the LLM is raw credential
  material or PII
- Produces a `<keepa_data>` prompt block that Nova's system prompt scaffold
  can reason over without inventing numbers
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Keepa + profitability live in execution/ — add to path so nova_core can import.
_EXECUTION = Path(__file__).resolve().parent.parent
if str(_EXECUTION) not in sys.path:
    sys.path.insert(0, str(_EXECUTION))

try:
    from keepa_client import KeepaClient  # type: ignore
except Exception:  # pragma: no cover - import-time degradation, logged on use
    KeepaClient = None  # type: ignore

try:
    from calculate_fba_profitability import calculate_product_profitability  # type: ignore
except Exception:  # pragma: no cover
    calculate_product_profitability = None  # type: ignore


# ── Cache (sqlite, 1hr TTL) ──────────────────────────────────────────────────

_CACHE_DB = Path(__file__).resolve().parents[2] / ".tmp" / "nova" / "nova.db"
_CACHE_TTL_SECONDS = 3600
_CACHE_MAX_AGE_DAYS = 90  # Rows older than this are purged opportunistically.


def _cache_conn() -> sqlite3.Connection:
    """Open the nova.db cache connection, creating the table if needed."""
    _CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB), timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keepa_cache (
            asin TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_keepa_cache_created ON keepa_cache(created_at)")
    return conn


def _cache_get(asin: str) -> dict | None:
    """Return cached Keepa payload for `asin` if fresh, else None."""
    try:
        conn = _cache_conn()
        try:
            row = conn.execute(
                "SELECT payload_json, created_at FROM keepa_cache WHERE asin = ?",
                (asin,),
            ).fetchone()
            if not row:
                return None
            payload_raw, created_at = row
            created_ts = datetime.fromisoformat(created_at.replace("Z", "").split(".")[0])
            if (datetime.utcnow() - created_ts).total_seconds() > _CACHE_TTL_SECONDS:
                return None
            return json.loads(payload_raw)
        finally:
            conn.close()
    except Exception:
        return None


def _cache_put(asin: str, payload: dict) -> None:
    try:
        conn = _cache_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO keepa_cache (asin, payload_json, created_at) "
                "VALUES (?, ?, ?)",
                (asin, json.dumps(payload, default=str), datetime.utcnow().isoformat()),
            )
            # Opportunistic purge — cheap because of the created_at index.
            cutoff = (datetime.utcnow() - timedelta(days=_CACHE_MAX_AGE_DAYS)).isoformat()
            conn.execute("DELETE FROM keepa_cache WHERE created_at < ?", (cutoff,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _purge_stale_cache() -> int:
    """Delete rows older than the TTL window. Call from maintenance jobs."""
    try:
        conn = _cache_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=_CACHE_MAX_AGE_DAYS)).isoformat()
            cur = conn.execute("DELETE FROM keepa_cache WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()
    except Exception:
        return 0


# ── Analysis ─────────────────────────────────────────────────────────────────


def _coerce_fba_fees(raw) -> float | None:
    """Normalize Keepa's fba_fees value to a dollar scalar.

    Keepa sometimes returns a scalar (already in dollars) and sometimes an
    object like {"lastUpdate": ..., "pickAndPackFee": 582}, where the fee
    is in CENTS. Either form needs to land as a dollar float downstream.
    Returns None if we can't make sense of it so the profitability engine
    can fall back to its own estimator.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # Heuristic: values above $50 are almost certainly cents (Keepa raw).
        return float(raw) / 100.0 if raw > 50 else float(raw)
    if isinstance(raw, dict):
        pp = raw.get("pickAndPackFee")
        if isinstance(pp, (int, float)):
            return float(pp) / 100.0
    return None


def _review_health_flag(product: dict) -> dict:
    """Flag products with suspicious recent review distribution.

    Students in the chat log have explicitly asked about this ("reviews are
    cooked because people giving 1"). If Keepa surfaces a recent 1★ ratio
    above ~20% we raise a flag; if we don't have the data we return a
    neutral dict so the caller can just skip the section.
    """
    dist = product.get("review_distribution") or {}
    total = 0
    one_star = 0
    for key, count in dist.items() if isinstance(dist, dict) else []:
        try:
            count = int(count)
            total += count
            if str(key).startswith("1"):
                one_star = count
        except (TypeError, ValueError):
            continue
    if total < 10:
        return {"available": False}
    ratio = one_star / total if total else 0
    return {
        "available": True,
        "one_star_ratio": round(ratio, 3),
        "flagged": ratio > 0.20,
        "note": "reviews may be cooked" if ratio > 0.20 else None,
    }


def _moq_layer(buy_cost: float, moq: int, profit_per_unit: float) -> dict:
    """Layer bulk-buy math on top of per-unit profitability.

    The chat log is full of MOQ-style drops ("purchasing at 9.04$ MOQ 320").
    Nova's answer should spell out capital, total profit, and payback.
    """
    capital_required = round(buy_cost * moq, 2)
    total_profit = round(profit_per_unit * moq, 2)
    # Payback period = how many units need to sell to recoup buy cost. This
    # is the conservative floor — ignores Amazon payment delay, which Sabbo
    # wants students to think about separately.
    payback_units = None
    if profit_per_unit > 0:
        payback_units = int(round(buy_cost / profit_per_unit))
    return {
        "moq": moq,
        "capital_required": capital_required,
        "total_profit_at_moq": total_profit,
        "payback_units_per_unit": payback_units,
    }


_SAFE_FIELDS = (
    "asin", "title", "brand", "amazon_price", "buy_box_price", "fba_price",
    "sell_price", "bsr", "review_count", "rating", "fba_seller_count",
    "fbm_seller_count", "total_offer_count", "amazon_on_listing",
    "monthly_sold", "fba_fees", "referral_fee_percentage", "is_sns",
    "is_adult_product", "availability_amazon", "is_heat_sensitive",
    "price_trends", "bsr_drops_30d", "est_sales_from_drops", "amazon_oos_pct",
)


def _sanitize_product(product: dict) -> dict:
    """Strip the Keepa parse down to fields that are safe to show Nova.

    Leaves out raw history arrays, seller names (PII concern — seller names
    can be personal), and debug/internal fields. Keeps the structured numbers
    the LLM needs to reason with.
    """
    clean: dict[str, Any] = {}
    for key in _SAFE_FIELDS:
        if key in product:
            clean[key] = product[key]
    return clean


def analyze_asin(
    asin: str,
    buy_cost: float | None = None,
    moq: int | None = None,
    *,
    skip_cache: bool = False,
) -> dict:
    """Analyze a single ASIN end-to-end.

    Returns a dict with:
        ok: bool
        asin: str
        product: dict  (sanitized Keepa fields)
        profitability: dict | None  (present when buy_cost given)
        moq_math: dict | None       (present when moq given with buy_cost)
        review_health: dict
        cached: bool
        keepa_tokens_used: int | None
        error: str | None
    """
    result: dict[str, Any] = {
        "ok": False,
        "asin": asin,
        "product": None,
        "profitability": None,
        "moq_math": None,
        "review_health": {"available": False},
        "cached": False,
        "keepa_tokens_used": None,
        "error": None,
    }

    if KeepaClient is None:
        result["error"] = "keepa_client unavailable"
        return result

    # Cache check — saves 13 tokens on the hot path.
    product = None
    if not skip_cache:
        product = _cache_get(asin)
        if product:
            result["cached"] = True

    if product is None:
        try:
            client = KeepaClient()
            # Deep by default (offers=20) — chosen during plan: students ask
            # buy-box / seller questions constantly, so the extra 12 tokens
            # are worth it vs. guessing.
            product = client.get_product(asin, offers=20, stats=180)
            if not product:
                result["error"] = "ASIN not found or Keepa returned empty"
                return result
            result["keepa_tokens_used"] = 13
            _cache_put(asin, product)
        except Exception as e:
            result["error"] = f"keepa lookup failed: {e}"
            return result

    result["product"] = _sanitize_product(product)
    result["review_health"] = _review_health_flag(product)

    # Profitability only runs when we have a buy cost to work with.
    if buy_cost is not None and calculate_product_profitability is not None:
        try:
            wrapped = {
                "name": product.get("title", ""),
                "brand": product.get("brand", ""),
                "sale_price": buy_cost,
                "amazon": product,
            }
            # calculate_product_profitability expects:
            #   keepa_fba_fees: the raw Keepa dict ({pickAndPackFee, storageFee}
            #                   in cents — it handles the /100 internally)
            #   keepa_referral_fee_pct: a RATE (0.15), not a percent (15.0).
            # Keepa's parsed field is a percent-number — divide by 100 to
            # convert, but only if it's clearly >1 (some older Keepa parses
            # already normalize to a rate).
            raw_ref_pct = product.get("referral_fee_percentage")
            if isinstance(raw_ref_pct, (int, float)) and raw_ref_pct > 1:
                ref_rate = float(raw_ref_pct) / 100.0
            else:
                ref_rate = raw_ref_pct
            prof = calculate_product_profitability(
                wrapped,
                shipping_to_fba=1.00,
                keepa_referral_fee_pct=ref_rate,
                keepa_fba_fees=product.get("fba_fees"),
                keepa_monthly_sold=product.get("monthly_sold"),
                keepa_sales_rank_drops_30=product.get("bsr_drops_30d"),
                availability_amazon=product.get("availability_amazon"),
            )
            result["profitability"] = prof
            if moq is not None and prof.get("profit_per_unit") is not None:
                result["moq_math"] = _moq_layer(
                    buy_cost, moq, prof["profit_per_unit"]
                )
        except Exception as e:
            result["profitability"] = {"error": f"profit calc failed: {e}"}

    result["ok"] = True
    return result


# ── Prompt formatter ─────────────────────────────────────────────────────────


def _format_number(n: Any, prefix: str = "") -> str:
    if n is None:
        return "—"
    try:
        if isinstance(n, bool):
            return "yes" if n else "no"
        if isinstance(n, float):
            return f"{prefix}{n:,.2f}"
        return f"{prefix}{n:,}"
    except Exception:
        return str(n)


def format_for_prompt(analysis: dict) -> str:
    """Render an analysis dict as a `<keepa_data>` block for the LLM.

    The system-prompt scaffold tells Nova to reason with these numbers and
    never invent any not present here. Keeping the format stable across
    messages also helps Nova's responses stay uniform.
    """
    if not analysis or not analysis.get("ok"):
        err = (analysis or {}).get("error") or "unknown error"
        return f"<keepa_data>\nLookup failed: {err}\n</keepa_data>"

    p = analysis["product"] or {}
    rh = analysis.get("review_health") or {}
    prof = analysis.get("profitability") or {}
    moq_math = analysis.get("moq_math") or {}

    lines = ["<keepa_data>"]
    lines.append(f"ASIN: {analysis['asin']}")
    if analysis.get("cached"):
        lines.append("(cached result — 0 Keepa tokens)")
    if p.get("title"):
        lines.append(f"Title: {p['title'][:140]}")
    if p.get("brand"):
        lines.append(f"Brand: {p['brand']}")

    lines.append("")
    lines.append("PRICE + DEMAND")
    lines.append(f"  Amazon price: {_format_number(p.get('amazon_price'), '$')}")
    bb = p.get("buy_box_price")
    if bb in (None, 0, 0.0):
        lines.append("  Buy Box:      no active buy box")
    else:
        lines.append(f"  Buy Box:      {_format_number(bb, '$')}")
    lines.append(f"  BSR:          {_format_number(p.get('bsr'))}")
    lines.append(f"  Monthly sold: {_format_number(p.get('monthly_sold'))}")
    lines.append(f"  BSR drops 30d: {_format_number(p.get('bsr_drops_30d'))}")

    lines.append("")
    lines.append("COMPETITION")
    lines.append(f"  FBA sellers: {_format_number(p.get('fba_seller_count'))}")
    lines.append(f"  FBM sellers: {_format_number(p.get('fbm_seller_count'))}")
    lines.append(f"  Amazon on listing: {_format_number(p.get('amazon_on_listing'))}")
    lines.append(f"  Amazon OOS %: {_format_number(p.get('amazon_oos_pct'))}")

    lines.append("")
    lines.append("FEES (Keepa-exact)")
    lines.append(f"  Referral %: {_format_number(p.get('referral_fee_percentage'))}")
    # Keepa's fba_fees can be a dict — normalize before rendering.
    fba_fee_scalar = _coerce_fba_fees(p.get("fba_fees"))
    lines.append(f"  FBA fee:    {_format_number(fba_fee_scalar, '$')}")

    if rh.get("available"):
        lines.append("")
        lines.append("REVIEW HEALTH")
        lines.append(f"  1★ ratio: {rh.get('one_star_ratio')}")
        if rh.get("flagged"):
            lines.append(f"  ⚠ {rh.get('note')}")

    risks = []
    if p.get("is_sns"): risks.append("SnS")
    if p.get("is_adult_product"): risks.append("adult product")
    if p.get("is_heat_sensitive"): risks.append("heat sensitive")
    if risks:
        lines.append("")
        lines.append("RISK FLAGS: " + ", ".join(risks))

    if prof:
        lines.append("")
        lines.append("PROFITABILITY (at provided buy cost)")
        lines.append(f"  Buy cost:    {_format_number(prof.get('buy_cost'), '$')}")
        lines.append(f"  Total fees:  {_format_number(prof.get('total_fees'), '$')}")
        lines.append(f"  Profit/unit: {_format_number(prof.get('profit_per_unit'), '$')}")
        lines.append(f"  ROI:         {_format_number(prof.get('roi_percent'))}%")
        lines.append(f"  Margin:      {_format_number(prof.get('profit_margin_percent'))}%")
        lines.append(f"  Verdict:     {prof.get('verdict', 'N/A')}")

    if moq_math:
        lines.append("")
        lines.append(f"AT MOQ {moq_math.get('moq')}")
        lines.append(f"  Capital required: {_format_number(moq_math.get('capital_required'), '$')}")
        lines.append(f"  Total profit:     {_format_number(moq_math.get('total_profit_at_moq'), '$')}")

    lines.append("</keepa_data>")
    return "\n".join(lines)
