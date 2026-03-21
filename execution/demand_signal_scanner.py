#!/usr/bin/env python3
"""
Script: demand_signal_scanner.py
Purpose: Detects rising demand signals using Google Trends and Reddit to find
         products BEFORE they spike on Amazon — giving a sourcing head start.
         Scores signals 0-100 and stores them in SQLite for tracking/action.

CLI:
    python execution/demand_signal_scanner.py scan [--source google|reddit]
    python execution/demand_signal_scanner.py trends --keyword "stanley cup"
    python execution/demand_signal_scanner.py signals [--days 7] [--min-score 50]
    python execution/demand_signal_scanner.py act --id 123 --action sourced [--notes "..."]
    python execution/demand_signal_scanner.py stats
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
DB_PATH = DB_DIR / "price_tracker.db"

REDDIT_USER_AGENT = "DemandSignalScanner/1.0 (by SabboOpenClawAI; research only)"
REDDIT_RATE_LIMIT = 2.0  # seconds between requests
GOOGLE_TRENDS_RATE_LIMIT = 12.0  # seconds between requests (5 req/min)

DEFAULT_SUBREDDITS = [
    "AmazonDeals",
    "deals",
    "BuyItForLife",
    "shutupandtakemymoney",
    "gadgets",
    "trending",
]

ASIN_PATTERN = re.compile(r"\b(B0[A-Z0-9]{8})\b")
AMAZON_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?amazon\.com[^\s\)\"']*(?:/dp/|/gp/product/)([A-Z0-9]{10})"
)
# Keywords that suggest a post is about a specific product (not just generic discussion)
PRODUCT_KEYWORDS = re.compile(
    r"\b(?:buy|bought|purchased|ordered|recommend|review|deal|sale|discount|coupon|"
    r"price drop|brand|model|version|gen\s?\d|mk\s?\d)\b",
    re.IGNORECASE,
)
SENTIMENT_POSITIVE = re.compile(
    r"\b(?:amazing|love|best|perfect|incredible|game.?changer|must.?have|essential|"
    r"awesome|excellent|fantastic|worth|recommend)\b",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("demand_signal_scanner")

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS demand_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    keyword TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    url TEXT,
    asin TEXT,
    details_json TEXT,
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demand_signal_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    notes TEXT,
    acted_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES demand_signals(id)
);

CREATE INDEX IF NOT EXISTS idx_ds_detected ON demand_signals(detected_at);
CREATE INDEX IF NOT EXISTS idx_ds_score ON demand_signals(score DESC);
CREATE INDEX IF NOT EXISTS idx_ds_source ON demand_signals(source);
CREATE INDEX IF NOT EXISTS idx_dsa_signal ON demand_signal_actions(signal_id);
"""


def init_db():
    """Initialize the SQLite database and tables."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ── Google Trends Integration ────────────────────────────────────────────────

def _get_pytrends():
    """Lazily import and return a pytrends TrendReq instance."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log.error("pytrends not installed. Run: pip install pytrends")
        sys.exit(1)
    return TrendReq(hl="en-US", tz=360)


def scan_trending_queries(category=None):
    """
    Get today's trending searches from Google Trends.
    Filters for product-related terms using heuristics.

    Returns:
        list[dict]: Each with 'keyword', 'approximate_traffic'
    """
    pt = _get_pytrends()
    log.info("Fetching trending searches from Google Trends...")

    try:
        trending_df = pt.trending_searches(pn="united_states")
    except Exception as e:
        log.error("Failed to fetch trending searches: %s", e)
        return []

    results = []
    for _, row in trending_df.iterrows():
        keyword = str(row[0]).strip()
        if not keyword:
            continue
        # Heuristic: keep terms that look product-related
        # Skip pure celebrity/news/sports terms (rough filter)
        lower = keyword.lower()
        skip_signals = ["vs ", "game", "score", "election", "death", "died", "murder"]
        if any(s in lower for s in skip_signals):
            continue
        results.append({"keyword": keyword, "approximate_traffic": None})

    log.info("Found %d potentially product-related trending queries", len(results))
    return results


def check_trend(keyword, timeframe="today 3-m"):
    """
    Get interest-over-time data for a keyword from Google Trends.

    Args:
        keyword: Search term
        timeframe: pytrends timeframe string (default: last 3 months)

    Returns:
        dict with 'keyword', 'timeframe', 'values' (list of ints 0-100),
        'average', 'latest', 'spike_ratio'
    """
    pt = _get_pytrends()
    log.info("Checking trend for '%s' (timeframe: %s)...", keyword, timeframe)

    try:
        pt.build_payload([keyword], timeframe=timeframe)
        df = pt.interest_over_time()
    except Exception as e:
        log.error("Failed to check trend for '%s': %s", keyword, e)
        return None

    if df.empty or keyword not in df.columns:
        log.warning("No trend data for '%s'", keyword)
        return None

    values = df[keyword].tolist()
    avg = sum(values) / len(values) if values else 0
    latest = values[-1] if values else 0
    spike_ratio = latest / avg if avg > 0 else 0

    return {
        "keyword": keyword,
        "timeframe": timeframe,
        "values": values,
        "average": round(avg, 2),
        "latest": latest,
        "spike_ratio": round(spike_ratio, 2),
    }


def detect_spike(keyword, threshold=2.0):
    """
    Returns True if the keyword's recent Google Trends interest is greater
    than threshold * its 90-day average.

    Args:
        keyword: Search term
        threshold: Multiplier (default 2.0 = double the average)

    Returns:
        tuple(bool, dict|None): (is_spiking, trend_data)
    """
    data = check_trend(keyword, timeframe="today 3-m")
    if data is None:
        return False, None
    is_spiking = data["spike_ratio"] >= threshold
    if is_spiking:
        log.info(
            "SPIKE DETECTED: '%s' — %.1fx above average (latest=%d, avg=%.1f)",
            keyword, data["spike_ratio"], data["latest"], data["average"],
        )
    return is_spiking, data


def batch_trend_check(keywords, threshold=2.0):
    """
    Check multiple keywords and return those with detected spikes.
    Respects Google Trends rate limits.

    Args:
        keywords: list of search terms
        threshold: spike detection threshold

    Returns:
        list[dict]: Spiking keywords with their trend data
    """
    spiking = []
    for i, kw in enumerate(keywords):
        if i > 0:
            time.sleep(GOOGLE_TRENDS_RATE_LIMIT)
        is_spike, data = detect_spike(kw, threshold=threshold)
        if is_spike and data:
            spiking.append(data)
    log.info("Batch check: %d/%d keywords spiking", len(spiking), len(keywords))
    return spiking


# ── Reddit Integration ───────────────────────────────────────────────────────

def _reddit_get(url):
    """Make a rate-limited GET request to Reddit's JSON API."""
    import requests

    headers = {"User-Agent": REDDIT_USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Reddit request failed (%s): %s", url, e)
        return None


def scan_reddit(subreddits=None, hours=24):
    """
    Scan subreddits for recent posts that mention products.

    Args:
        subreddits: list of subreddit names (without r/). Defaults to DEFAULT_SUBREDDITS.
        hours: only include posts from the last N hours

    Returns:
        list[dict]: Posts with title, url, score, num_comments, created_utc, subreddit, selftext
    """
    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cutoff_ts = cutoff.timestamp()
    all_posts = []

    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(REDDIT_RATE_LIMIT)

        log.info("Scanning r/%s (last %dh)...", sub, hours)
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit=50"
        data = _reddit_get(url)
        if not data or "data" not in data:
            continue

        for child in data["data"].get("children", []):
            post = child.get("data", {})
            created = post.get("created_utc", 0)
            if created < cutoff_ts:
                continue

            all_posts.append({
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "permalink": f"https://www.reddit.com{post.get('permalink', '')}",
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "created_utc": created,
                "subreddit": sub,
                "selftext": post.get("selftext", "")[:500],
                "upvote_ratio": post.get("upvote_ratio", 0),
            })

    log.info("Scanned %d subreddits, found %d recent posts", len(subreddits), len(all_posts))
    return all_posts


def extract_product_mentions(posts):
    """
    Extract product-related information from Reddit posts.
    Looks for Amazon URLs, ASINs, and product name patterns.

    Args:
        posts: list of post dicts from scan_reddit()

    Returns:
        list[dict]: Posts enriched with 'asins', 'amazon_urls', 'product_keywords_found'
    """
    enriched = []
    for post in posts:
        text = f"{post['title']} {post.get('selftext', '')} {post.get('url', '')}"

        # Extract ASINs
        asins = list(set(ASIN_PATTERN.findall(text)))

        # Extract Amazon URLs and their ASINs
        amazon_matches = AMAZON_URL_PATTERN.findall(text)
        for asin in amazon_matches:
            if asin not in asins:
                asins.append(asin)

        # Check for product-related keywords
        product_kw_matches = PRODUCT_KEYWORDS.findall(text)
        sentiment_matches = SENTIMENT_POSITIVE.findall(text)

        enriched_post = {
            **post,
            "asins": asins,
            "amazon_urls": amazon_matches,
            "product_keywords_found": list(set(kw.lower() for kw in product_kw_matches)),
            "sentiment_positive": list(set(s.lower() for s in sentiment_matches)),
        }
        enriched.append(enriched_post)

    with_products = [p for p in enriched if p["asins"] or p["product_keywords_found"]]
    log.info(
        "Extracted product mentions: %d/%d posts have product signals",
        len(with_products), len(enriched),
    )
    return enriched


def score_reddit_signal(post):
    """
    Score a Reddit post's demand signal strength (0-100).

    Breakdown:
        - Engagement (0-30): upvotes + comments, normalized
        - Velocity (0-20): upvotes per hour since posting
        - Product specificity (0-20): has ASIN, brand name, product keywords
        - Sentiment (0-10): positive sentiment words
        - Subreddit quality (0-20): some subreddits are stronger signals

    Args:
        post: enriched post dict from extract_product_mentions()

    Returns:
        int: score 0-100
    """
    score = 0

    # ── Engagement (0-30) ──
    upvotes = post.get("score", 0)
    comments = post.get("num_comments", 0)
    engagement = upvotes + (comments * 2)  # comments weighted higher
    if engagement >= 500:
        score += 30
    elif engagement >= 200:
        score += 25
    elif engagement >= 100:
        score += 20
    elif engagement >= 50:
        score += 15
    elif engagement >= 20:
        score += 10
    elif engagement >= 5:
        score += 5

    # ── Velocity (0-20) ──
    created = post.get("created_utc", 0)
    if created > 0:
        hours_alive = max((datetime.utcnow().timestamp() - created) / 3600, 0.1)
        velocity = upvotes / hours_alive
        if velocity >= 100:
            score += 20
        elif velocity >= 50:
            score += 16
        elif velocity >= 20:
            score += 12
        elif velocity >= 10:
            score += 8
        elif velocity >= 5:
            score += 4

    # ── Product specificity (0-20) ──
    asins = post.get("asins", [])
    product_kws = post.get("product_keywords_found", [])
    if asins:
        score += 12  # Has actual ASIN — strong signal
    if len(product_kws) >= 3:
        score += 8
    elif len(product_kws) >= 1:
        score += 4

    # ── Sentiment (0-10) ──
    sentiment = post.get("sentiment_positive", [])
    if len(sentiment) >= 3:
        score += 10
    elif len(sentiment) >= 1:
        score += 5

    # ── Subreddit quality (0-20) ──
    sub = post.get("subreddit", "").lower()
    high_signal_subs = {"shutupandtakemymoney": 20, "buyitforlife": 18, "deals": 15, "amazondeals": 15}
    mid_signal_subs = {"gadgets": 12, "trending": 8}
    if sub in high_signal_subs:
        score += high_signal_subs[sub]
    elif sub in mid_signal_subs:
        score += mid_signal_subs[sub]
    else:
        score += 5

    return min(score, 100)


# ── Signal Scoring for Google Trends ─────────────────────────────────────────

def score_trend_signal(trend_data):
    """
    Score a Google Trends signal (0-100).

    Breakdown:
        - Spike magnitude (0-30): how far above the 90-day average
        - Trend momentum (0-30): are recent values climbing?
        - Search volume proxy (0-20): latest absolute value
        - Product specificity (0-20): heuristic on keyword text

    Args:
        trend_data: dict from check_trend()

    Returns:
        int: score 0-100
    """
    score = 0
    ratio = trend_data.get("spike_ratio", 0)
    latest = trend_data.get("latest", 0)
    values = trend_data.get("values", [])

    # ── Spike magnitude (0-30) ──
    if ratio >= 5.0:
        score += 30
    elif ratio >= 3.0:
        score += 24
    elif ratio >= 2.0:
        score += 18
    elif ratio >= 1.5:
        score += 12
    elif ratio >= 1.2:
        score += 6

    # ── Trend momentum (0-30): last 7 data points climbing? ──
    if len(values) >= 7:
        recent = values[-7:]
        climbing = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        momentum_pct = climbing / (len(recent) - 1)
        score += int(momentum_pct * 30)

    # ── Search volume proxy (0-20) ──
    if latest >= 80:
        score += 20
    elif latest >= 60:
        score += 15
    elif latest >= 40:
        score += 10
    elif latest >= 20:
        score += 5

    # ── Product specificity heuristic (0-20) ──
    kw = trend_data.get("keyword", "").lower()
    product_signals = ["buy", "price", "deal", "review", "best", "vs", "pro", "max", "gen", "mk"]
    specificity = sum(1 for s in product_signals if s in kw)
    score += min(specificity * 5, 20)

    return min(score, 100)


# ── Storage ──────────────────────────────────────────────────────────────────

def store_signal(conn, source, keyword, signal_type, score, url=None, asin=None, details=None):
    """Insert a demand signal into the database."""
    now = datetime.utcnow().isoformat()
    details_json = json.dumps(details) if details else None
    conn.execute(
        """INSERT INTO demand_signals (source, keyword, signal_type, score, url, asin, details_json, detected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (source, keyword, signal_type, score, url, asin, details_json, now),
    )
    conn.commit()


def store_action(conn, signal_id, action, notes=None):
    """Record an action taken on a demand signal."""
    valid_actions = ("sourced", "skipped", "watching")
    if action not in valid_actions:
        log.error("Invalid action '%s'. Must be one of: %s", action, valid_actions)
        return False
    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO demand_signal_actions (signal_id, action, notes, acted_at)
           VALUES (?, ?, ?, ?)""",
        (signal_id, action, notes, now),
    )
    conn.commit()
    return True


def get_signals(conn, days=7, min_score=0, source=None, limit=50):
    """Retrieve stored demand signals with optional filters."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    query = "SELECT * FROM demand_signals WHERE detected_at >= ? AND score >= ?"
    params = [cutoff, min_score]
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY score DESC, detected_at DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_stats(conn):
    """Get aggregate statistics on demand signals and actions."""
    stats = {}

    # Signal counts by source
    rows = conn.execute(
        "SELECT source, COUNT(*) as cnt, AVG(score) as avg_score FROM demand_signals GROUP BY source"
    ).fetchall()
    stats["by_source"] = [
        {"source": r["source"], "count": r["cnt"], "avg_score": round(r["avg_score"], 1)}
        for r in rows
    ]

    # Signal counts by type
    rows = conn.execute(
        "SELECT signal_type, COUNT(*) as cnt FROM demand_signals GROUP BY signal_type"
    ).fetchall()
    stats["by_type"] = [{"type": r["signal_type"], "count": r["cnt"]} for r in rows]

    # Action rates
    rows = conn.execute(
        "SELECT action, COUNT(*) as cnt FROM demand_signal_actions GROUP BY action"
    ).fetchall()
    stats["actions"] = [{"action": r["action"], "count": r["cnt"]} for r in rows]

    total_signals = conn.execute("SELECT COUNT(*) FROM demand_signals").fetchone()[0]
    acted_signals = conn.execute(
        "SELECT COUNT(DISTINCT signal_id) FROM demand_signal_actions"
    ).fetchone()[0]
    stats["total_signals"] = total_signals
    stats["acted_on"] = acted_signals
    stats["action_rate"] = (
        round(acted_signals / total_signals * 100, 1) if total_signals > 0 else 0
    )

    # Last 7 days trend
    cutoff_7d = (datetime.utcnow() - timedelta(days=7)).isoformat()
    stats["last_7d_signals"] = conn.execute(
        "SELECT COUNT(*) FROM demand_signals WHERE detected_at >= ?", (cutoff_7d,)
    ).fetchone()[0]

    # Top 5 keywords by score (last 30 days)
    cutoff_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT keyword, MAX(score) as top_score, COUNT(*) as appearances
           FROM demand_signals WHERE detected_at >= ?
           GROUP BY keyword ORDER BY top_score DESC LIMIT 5""",
        (cutoff_30d,),
    ).fetchall()
    stats["top_keywords_30d"] = [
        {"keyword": r["keyword"], "top_score": r["top_score"], "appearances": r["appearances"]}
        for r in rows
    ]

    return stats


# ── Scan Orchestration ───────────────────────────────────────────────────────

def run_google_scan(conn):
    """Run a full Google Trends scan: get trending queries, check for spikes, store signals."""
    log.info("=== Google Trends Scan ===")
    signals_found = []

    # Step 1: Get trending queries
    trending = scan_trending_queries()
    if not trending:
        log.warning("No trending queries found")
        return signals_found

    # Step 2: Batch check top trending keywords for spikes
    keywords = [t["keyword"] for t in trending[:15]]  # cap at 15 to respect rate limits
    log.info("Checking %d trending keywords for spikes...", len(keywords))

    for i, kw in enumerate(keywords):
        if i > 0:
            time.sleep(GOOGLE_TRENDS_RATE_LIMIT)
        is_spike, data = detect_spike(kw, threshold=1.5)
        if data:
            trend_score = score_trend_signal(data)
            signal_type = "spike" if is_spike else "trending"
            if trend_score >= 20:  # only store meaningful signals
                store_signal(
                    conn,
                    source="google_trends",
                    keyword=kw,
                    signal_type=signal_type,
                    score=trend_score,
                    details=data,
                )
                signals_found.append({
                    "keyword": kw,
                    "score": trend_score,
                    "type": signal_type,
                    "spike_ratio": data["spike_ratio"],
                    "latest": data["latest"],
                })
                log.info(
                    "  [%s] '%s' — score=%d, spike=%.1fx",
                    signal_type.upper(), kw, trend_score, data["spike_ratio"],
                )

    log.info("Google scan complete: %d signals stored", len(signals_found))
    return signals_found


def run_reddit_scan(conn, subreddits=None, hours=24):
    """Run a full Reddit scan: fetch posts, extract products, score and store."""
    log.info("=== Reddit Scan ===")
    signals_found = []

    # Step 1: Scan subreddits
    posts = scan_reddit(subreddits=subreddits, hours=hours)
    if not posts:
        log.warning("No Reddit posts found")
        return signals_found

    # Step 2: Extract product mentions
    enriched = extract_product_mentions(posts)

    # Step 3: Score and store
    for post in enriched:
        reddit_score = score_reddit_signal(post)
        if reddit_score < 15:  # skip low-signal noise
            continue

        # Determine signal type
        asins = post.get("asins", [])
        velocity = 0
        if post.get("created_utc", 0) > 0:
            hours_alive = max((datetime.utcnow().timestamp() - post["created_utc"]) / 3600, 0.1)
            velocity = post.get("score", 0) / hours_alive

        if velocity >= 50:
            signal_type = "viral"
        elif asins:
            signal_type = "trending"
        else:
            signal_type = "trending"

        primary_asin = asins[0] if asins else None
        keyword = post["title"][:120]

        details = {
            "subreddit": post["subreddit"],
            "upvotes": post.get("score", 0),
            "comments": post.get("num_comments", 0),
            "velocity": round(velocity, 1),
            "asins": asins,
            "product_keywords": post.get("product_keywords_found", []),
            "sentiment": post.get("sentiment_positive", []),
        }

        store_signal(
            conn,
            source="reddit",
            keyword=keyword,
            signal_type=signal_type,
            score=reddit_score,
            url=post.get("permalink"),
            asin=primary_asin,
            details=details,
        )
        signals_found.append({
            "keyword": keyword,
            "score": reddit_score,
            "type": signal_type,
            "subreddit": post["subreddit"],
            "asin": primary_asin,
            "upvotes": post.get("score", 0),
        })

    log.info("Reddit scan complete: %d signals stored", len(signals_found))
    return signals_found


# ── Display Helpers ──────────────────────────────────────────────────────────

def print_signals(signals, title="Demand Signals"):
    """Pretty-print a list of signal rows from the DB."""
    if not signals:
        print(f"\n{title}: (none found)\n")
        return

    print(f"\n{'=' * 80}")
    print(f"  {title} ({len(signals)} results)")
    print(f"{'=' * 80}")

    for s in signals:
        asin_str = f"  ASIN: {s['asin']}" if s["asin"] else ""
        print(f"\n  [{s['id']:>4}]  Score: {s['score']:>3}/100  |  {s['source']}  |  {s['signal_type']}")
        print(f"         {s['keyword'][:70]}{asin_str}")
        if s["url"]:
            print(f"         {s['url'][:80]}")
        print(f"         Detected: {s['detected_at'][:19]}")

    print(f"\n{'=' * 80}\n")


def print_scan_results(all_signals):
    """Print top 10 signals from a scan run, sorted by score."""
    if not all_signals:
        print("\nNo signals detected in this scan.\n")
        return

    sorted_signals = sorted(all_signals, key=lambda x: x["score"], reverse=True)[:10]

    print(f"\n{'=' * 80}")
    print(f"  TOP {len(sorted_signals)} DEMAND SIGNALS")
    print(f"{'=' * 80}")

    for i, s in enumerate(sorted_signals, 1):
        asin_str = f"  [{s.get('asin', '')}]" if s.get("asin") else ""
        source = s.get("subreddit", s.get("type", ""))
        print(
            f"  {i:>2}. [{s['score']:>3}] {s['keyword'][:55]}"
            f"  ({source}){asin_str}"
        )

    print(f"\n{'=' * 80}\n")


def print_stats(stats):
    """Pretty-print statistics."""
    print(f"\n{'=' * 80}")
    print("  DEMAND SIGNAL STATS")
    print(f"{'=' * 80}")

    print(f"\n  Total signals: {stats['total_signals']}")
    print(f"  Acted on:      {stats['acted_on']} ({stats['action_rate']}%)")
    print(f"  Last 7 days:   {stats['last_7d_signals']}")

    if stats["by_source"]:
        print("\n  By Source:")
        for s in stats["by_source"]:
            print(f"    {s['source']:<20} {s['count']:>5} signals  (avg score: {s['avg_score']})")

    if stats["by_type"]:
        print("\n  By Type:")
        for t in stats["by_type"]:
            print(f"    {t['type']:<20} {t['count']:>5}")

    if stats["actions"]:
        print("\n  Actions Taken:")
        for a in stats["actions"]:
            print(f"    {a['action']:<20} {a['count']:>5}")

    if stats["top_keywords_30d"]:
        print("\n  Top Keywords (30 days):")
        for k in stats["top_keywords_30d"]:
            print(f"    [{k['top_score']:>3}] {k['keyword']:<50} ({k['appearances']}x)")

    print(f"\n{'=' * 80}\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Demand Signal Scanner — detect rising product demand from Google Trends and Reddit"
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # scan
    p_scan = sub.add_parser("scan", help="Full scan (Google Trends + Reddit)")
    p_scan.add_argument("--source", choices=["google", "reddit"], help="Scan one source only")
    p_scan.add_argument("--hours", type=int, default=24, help="Reddit: posts from last N hours (default: 24)")

    # trends
    p_trends = sub.add_parser("trends", help="Check Google Trends for a specific keyword")
    p_trends.add_argument("--keyword", required=True, help="Keyword to check")
    p_trends.add_argument("--timeframe", default="today 3-m", help="Timeframe (default: 'today 3-m')")
    p_trends.add_argument("--threshold", type=float, default=2.0, help="Spike threshold (default: 2.0)")

    # signals
    p_signals = sub.add_parser("signals", help="View stored signals")
    p_signals.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    p_signals.add_argument("--min-score", type=int, default=0, help="Minimum score filter (default: 0)")
    p_signals.add_argument("--source", choices=["google_trends", "reddit"], help="Filter by source")

    # act
    p_act = sub.add_parser("act", help="Mark a signal as acted on")
    p_act.add_argument("--id", type=int, required=True, help="Signal ID")
    p_act.add_argument(
        "--action", required=True, choices=["sourced", "skipped", "watching"],
        help="Action taken",
    )
    p_act.add_argument("--notes", default=None, help="Optional notes")

    # stats
    sub.add_parser("stats", help="View signal statistics")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    conn = init_db()

    try:
        if args.command == "scan":
            all_signals = []
            if args.source in (None, "google"):
                all_signals.extend(run_google_scan(conn))
            if args.source in (None, "reddit"):
                all_signals.extend(run_reddit_scan(conn, hours=args.hours))
            print_scan_results(all_signals)

        elif args.command == "trends":
            is_spike, data = detect_spike(args.keyword, threshold=args.threshold)
            if data:
                print(f"\nKeyword:     {data['keyword']}")
                print(f"Timeframe:   {data['timeframe']}")
                print(f"Average:     {data['average']}")
                print(f"Latest:      {data['latest']}")
                print(f"Spike ratio: {data['spike_ratio']}x")
                print(f"Spiking:     {'YES' if is_spike else 'No'} (threshold: {args.threshold}x)")
                print(f"Trend score: {score_trend_signal(data)}/100")
                # Show mini sparkline of last 12 data points
                if data["values"]:
                    recent = data["values"][-12:]
                    bars = "".join(_sparkline_char(v, max(recent)) for v in recent)
                    print(f"Last 12:     {bars}")
            else:
                print(f"\nNo trend data available for '{args.keyword}'")

        elif args.command == "signals":
            rows = get_signals(conn, days=args.days, min_score=args.min_score, source=args.source)
            title = f"Signals (last {args.days}d, min score {args.min_score})"
            print_signals(rows, title=title)

        elif args.command == "act":
            # Verify signal exists
            row = conn.execute("SELECT id FROM demand_signals WHERE id = ?", (args.id,)).fetchone()
            if not row:
                log.error("Signal ID %d not found", args.id)
                sys.exit(1)
            if store_action(conn, args.id, args.action, args.notes):
                print(f"Signal #{args.id} marked as '{args.action}'")
            else:
                sys.exit(1)

        elif args.command == "stats":
            stats = get_stats(conn)
            print_stats(stats)

    finally:
        conn.close()


def _sparkline_char(value, max_val):
    """Return a Unicode sparkline character for a value relative to max."""
    if max_val == 0:
        return " "
    blocks = " _.-~*^"
    idx = int(value / max_val * (len(blocks) - 1))
    return blocks[min(idx, len(blocks) - 1)]


if __name__ == "__main__":
    main()
