#!/usr/bin/env python3
"""
Script: wholesale_supplier_finder.py
Purpose: Find, rank, and manage wholesale suppliers by product category.
         Scrapes supplier directories (ThomasNet, Wholesale Central, Google),
         scores suppliers on Amazon-friendliness, and maintains a SQLite DB
         for ongoing relationship management.
Inputs:  CLI subcommands (search, list, add, contact, followups, export, import, stats)
Outputs: Ranked supplier lists, CSV exports, follow-up reminders (stdout or file)

CLI:
    python execution/wholesale_supplier_finder.py search --category "Health & Household" --sources google,thomasnet
    python execution/wholesale_supplier_finder.py list --min-score 50 --status active
    python execution/wholesale_supplier_finder.py add --name "ABC Wholesale" --website "abc.com"
    python execution/wholesale_supplier_finder.py contact --id 5 --type email --notes "Sent intro"
    python execution/wholesale_supplier_finder.py followups --days 7
    python execution/wholesale_supplier_finder.py export --output suppliers.csv --min-score 60
    python execution/wholesale_supplier_finder.py import --csv suppliers.csv
    python execution/wholesale_supplier_finder.py stats
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    print("Install with: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)


# ── Config ────────────────────────────────────────────────────────────────────

DB_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing"
DB_PATH = DB_DIR / "price_tracker.db"

REQUEST_DELAY = 3  # seconds between web requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CATEGORY_SEARCH_TERMS = {
    "Health & Household": ["health products wholesale", "household supplies distributor"],
    "Beauty & Personal Care": ["beauty wholesale supplier", "cosmetics distributor"],
    "Toys & Games": ["toy wholesale USA", "games distributor"],
    "Home & Kitchen": ["home goods wholesale", "kitchen supplies distributor"],
    "Office Products": ["office supplies wholesale"],
    "Grocery": ["grocery wholesale distributor", "food supplier"],
    "Sports & Outdoors": ["sporting goods wholesale"],
    "Tools & Home Improvement": ["tools wholesale distributor"],
    "Pet Supplies": ["pet supplies wholesale"],
    "Baby": ["baby products wholesale distributor"],
}

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS wholesale_suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    website TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    state TEXT,
    country TEXT DEFAULT 'US',
    categories TEXT DEFAULT '[]',
    min_order TEXT,
    certifications TEXT DEFAULT '[]',
    score INTEGER DEFAULT 0,
    source TEXT,
    notes TEXT,
    status TEXT DEFAULT 'new',
    scraped_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(name, website)
);

CREATE TABLE IF NOT EXISTS supplier_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    contact_type TEXT NOT NULL,
    date TEXT NOT NULL,
    notes TEXT,
    next_followup TEXT,
    FOREIGN KEY (supplier_id) REFERENCES wholesale_suppliers(id)
);

CREATE TABLE IF NOT EXISTS supplier_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER NOT NULL,
    product_name TEXT,
    wholesale_cost REAL,
    case_pack INTEGER,
    upc TEXT,
    asin TEXT,
    estimated_roi REAL,
    added_at TEXT NOT NULL,
    FOREIGN KEY (supplier_id) REFERENCES wholesale_suppliers(id)
);

CREATE INDEX IF NOT EXISTS idx_ws_score ON wholesale_suppliers(score);
CREATE INDEX IF NOT EXISTS idx_ws_status ON wholesale_suppliers(status);
CREATE INDEX IF NOT EXISTS idx_ws_categories ON wholesale_suppliers(categories);
CREATE INDEX IF NOT EXISTS idx_sc_followup ON supplier_contacts(next_followup);
"""


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Open (and initialize if needed) the SQLite database."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_supplier(supplier: dict) -> int:
    """Score a supplier dict on a 0-100 scale based on Amazon-friendliness."""
    s = 0

    # Location
    country = (supplier.get("country") or "").upper().strip()
    state = (supplier.get("state") or "").upper().strip()
    if country in ("US", "USA", "UNITED STATES") or state in US_STATES:
        s += 20
    elif country:
        s += 5

    # Website
    if supplier.get("website"):
        s += 10

    # Minimum order info
    if supplier.get("min_order"):
        s += 10

    # Years in business (from notes or dedicated field)
    years = _extract_years_in_business(supplier)
    if years is not None:
        s += min(int(years / 2), 15)

    # Number of categories
    cats = supplier.get("categories") or []
    if isinstance(cats, str):
        try:
            cats = json.loads(cats)
        except (json.JSONDecodeError, TypeError):
            cats = [cats]
    s += min(len(cats) * 3, 10)

    # Certifications
    certs = supplier.get("certifications") or []
    if isinstance(certs, str):
        try:
            certs = json.loads(certs)
        except (json.JSONDecodeError, TypeError):
            certs = [c.strip() for c in certs.split(",") if c.strip()]
    s += min(len(certs) * 5, 15)

    # Contact info completeness
    if supplier.get("email"):
        s += 5
    if supplier.get("phone"):
        s += 5
    if supplier.get("address"):
        s += 5

    # Amazon-friendly indicators
    desc = " ".join([
        supplier.get("notes") or "",
        supplier.get("name") or "",
        str(supplier.get("categories") or ""),
    ]).lower()
    amazon_bonus = 0
    for keyword in ("dropship", "fba prep", "private label"):
        if keyword in desc:
            amazon_bonus += 10
    s += min(amazon_bonus, 20)

    return min(s, 100)


def _extract_years_in_business(supplier: dict) -> int | None:
    """Try to extract years in business from notes or other fields."""
    notes = (supplier.get("notes") or "") + " " + (supplier.get("name") or "")
    m = re.search(r"(\d+)\s*(?:years?|yrs?)\s*(?:in business)?", notes, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Check for "established YYYY" or "since YYYY"
    m = re.search(r"(?:est(?:ablished)?|since|founded)\s*\.?\s*(\d{4})", notes, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        if 1900 <= year <= datetime.now().year:
            return datetime.now().year - year
    return None


# ── Web Scraping ──────────────────────────────────────────────────────────────

def _safe_request(url: str, params: dict = None) -> requests.Response | None:
    """Make a GET request with rate limiting and error handling."""
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 403:
            print(f"  [WARN] 403 Forbidden: {url}", file=sys.stderr)
            return None
        if resp.status_code == 429:
            print(f"  [WARN] 429 Rate limited: {url} — waiting 10s", file=sys.stderr)
            time.sleep(10)
            return None
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"  [WARN] Request failed: {e}", file=sys.stderr)
        return None


def _scrape_google(query: str, max_results: int = 10) -> list[dict]:
    """Search Google for wholesale suppliers and extract results."""
    suppliers = []
    search_url = "https://www.google.com/search"
    params = {"q": query, "num": max_results}

    print(f"  [Google] Searching: {query}")
    resp = _safe_request(search_url, params=params)
    if not resp:
        return suppliers

    soup = BeautifulSoup(resp.text, "html.parser")

    # Parse organic results
    for g in soup.select("div.g, div[data-hveid]"):
        link_el = g.select_one("a[href^='http']")
        title_el = g.select_one("h3")
        snippet_el = g.select_one("div[data-sncf], span.st, div.VwiC3b")

        if not link_el or not title_el:
            continue

        href = link_el.get("href", "")
        title = title_el.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        # Skip non-supplier results
        if any(skip in href for skip in ["google.com", "youtube.com", "wikipedia.org", "amazon.com"]):
            continue

        supplier = {
            "name": title,
            "website": href,
            "notes": snippet,
            "source": "google",
            "country": "US",
            "categories": [],
            "certifications": [],
        }

        # Extract email/phone from snippet
        email_m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", snippet)
        if email_m:
            supplier["email"] = email_m.group(0)
        phone_m = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", snippet)
        if phone_m:
            supplier["phone"] = phone_m.group(0)

        suppliers.append(supplier)

    time.sleep(REQUEST_DELAY)
    return suppliers


def _scrape_thomasnet(query: str, max_results: int = 10) -> list[dict]:
    """Search ThomasNet for suppliers by category."""
    suppliers = []
    search_url = f"https://www.thomasnet.com/nsearch.html"
    params = {"cov": "NA", "heading": "", "what": query, "which": "prod"}

    print(f"  [ThomasNet] Searching: {query}")
    resp = _safe_request(search_url, params=params)
    if not resp:
        return suppliers

    soup = BeautifulSoup(resp.text, "html.parser")

    # ThomasNet supplier listing cards
    for card in soup.select("div.profile-card, div.supplier-result, div.company-row")[:max_results]:
        name_el = card.select_one("h2 a, .profile-card__title a, a.profile-card__name")
        if not name_el:
            name_el = card.select_one("a[data-content='Supplier Name']")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        link = name_el.get("href", "")
        if link and not link.startswith("http"):
            link = "https://www.thomasnet.com" + link

        location_el = card.select_one(".profile-card__location, .supplier-location, .company-location")
        location = location_el.get_text(strip=True) if location_el else ""

        # Parse state from location
        state = ""
        state_m = re.search(r"\b([A-Z]{2})\b", location)
        if state_m and state_m.group(1) in US_STATES:
            state = state_m.group(1)

        desc_el = card.select_one(".profile-card__desc, .supplier-description")
        desc = desc_el.get_text(strip=True) if desc_el else ""

        # Extract certifications
        certs = []
        cert_els = card.select(".certification-badge, .cert-icon, span[title*='ISO'], span[title*='FDA']")
        for c in cert_els:
            cert_text = c.get("title", "") or c.get_text(strip=True)
            if cert_text:
                certs.append(cert_text)

        # Also scan text for certs
        for cert_kw in ("ISO 9001", "ISO 13485", "ISO 14001", "FDA", "GMP", "UL", "CE"):
            if cert_kw.lower() in (desc + " " + name).lower() and cert_kw not in certs:
                certs.append(cert_kw)

        supplier = {
            "name": name,
            "website": link,
            "address": location,
            "state": state,
            "country": "US",
            "notes": desc,
            "certifications": certs,
            "source": "thomasnet",
            "categories": [],
        }
        suppliers.append(supplier)

    time.sleep(REQUEST_DELAY)
    return suppliers


def _scrape_wholesale_central(query: str, max_results: int = 10) -> list[dict]:
    """Search Wholesale Central for supplier listings."""
    suppliers = []
    search_url = f"https://www.wholesalecentral.com/st/{quote_plus(query)}.html"

    print(f"  [WholesaleCentral] Searching: {query}")
    resp = _safe_request(search_url)
    if not resp:
        return suppliers

    soup = BeautifulSoup(resp.text, "html.parser")

    for listing in soup.select("div.listing, div.product-listing, div.company-listing")[:max_results]:
        name_el = listing.select_one("a.listing-title, h3 a, a.company-name")
        if not name_el:
            name_el = listing.select_one("a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        link = name_el.get("href", "")
        if link and not link.startswith("http"):
            link = "https://www.wholesalecentral.com" + link

        desc_el = listing.select_one(".listing-desc, .description, p")
        desc = desc_el.get_text(strip=True) if desc_el else ""

        # Extract minimum order
        min_order = ""
        mo_m = re.search(r"(?:min(?:imum)?\s*order[:\s]*)([\$\d,]+(?:\s*(?:units?|pcs?|cases?))?)",
                         desc, re.IGNORECASE)
        if mo_m:
            min_order = mo_m.group(1)

        supplier = {
            "name": name,
            "website": link,
            "notes": desc,
            "min_order": min_order,
            "source": "wholesale_central",
            "country": "US",
            "categories": [],
            "certifications": [],
        }
        suppliers.append(supplier)

    time.sleep(REQUEST_DELAY)
    return suppliers


# ── Core Functions ────────────────────────────────────────────────────────────

def search_suppliers(category: str, sources: list[str] = None) -> list[dict]:
    """
    Search for wholesale suppliers by category across specified sources.
    Returns list of scored supplier dicts and saves to DB.
    """
    if sources is None:
        sources = ["google", "thomasnet"]

    # Build search queries from category mapping
    search_terms = CATEGORY_SEARCH_TERMS.get(category, [f"{category} wholesale supplier"])
    raw_suppliers = []

    for term in search_terms:
        for source in sources:
            if source == "google":
                full_query = f'"{term}" USA minimum order'
                raw_suppliers.extend(_scrape_google(full_query))
            elif source == "thomasnet":
                raw_suppliers.extend(_scrape_thomasnet(term))
            elif source == "wholesale_central":
                raw_suppliers.extend(_scrape_wholesale_central(term))
            else:
                print(f"  [WARN] Unknown source: {source}", file=sys.stderr)

    # Deduplicate by name (case-insensitive)
    seen = set()
    unique_suppliers = []
    for sup in raw_suppliers:
        key = sup["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            sup["categories"] = [category]
            sup["score"] = score_supplier(sup)
            unique_suppliers.append(sup)

    # Sort by score descending
    unique_suppliers.sort(key=lambda x: x["score"], reverse=True)

    # Save to database
    saved_count = 0
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat()
        for sup in unique_suppliers:
            try:
                conn.execute(
                    """INSERT INTO wholesale_suppliers
                       (name, website, email, phone, address, state, country,
                        categories, min_order, certifications, score, source,
                        notes, status, scraped_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
                    (
                        sup.get("name"),
                        sup.get("website"),
                        sup.get("email"),
                        sup.get("phone"),
                        sup.get("address"),
                        sup.get("state"),
                        sup.get("country", "US"),
                        json.dumps(sup.get("categories", [])),
                        sup.get("min_order"),
                        json.dumps(sup.get("certifications", [])),
                        sup["score"],
                        sup.get("source"),
                        sup.get("notes"),
                        now,
                        now,
                    ),
                )
                saved_count += 1
            except sqlite3.IntegrityError:
                # Duplicate — update score and timestamp
                conn.execute(
                    """UPDATE wholesale_suppliers
                       SET score = MAX(score, ?), updated_at = ?, notes = COALESCE(notes, ?)
                       WHERE name = ? AND website = ?""",
                    (sup["score"], now, sup.get("notes"), sup["name"], sup.get("website")),
                )
        conn.commit()
    finally:
        conn.close()

    print(f"\nFound {len(unique_suppliers)} suppliers, saved {saved_count} new to DB.")
    return unique_suppliers


def rank_suppliers(category: str = None, min_score: int = 40) -> list[dict]:
    """Return ranked supplier list from DB, optionally filtered by category."""
    conn = get_db()
    try:
        query = "SELECT * FROM wholesale_suppliers WHERE score >= ?"
        params: list = [min_score]
        if category:
            query += " AND categories LIKE ?"
            params.append(f"%{category}%")
        query += " ORDER BY score DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_supplier(
    name: str,
    website: str = None,
    email: str = None,
    phone: str = None,
    address: str = None,
    state: str = None,
    country: str = "US",
    categories: list = None,
    min_order: str = None,
    certifications: list = None,
    notes: str = None,
) -> int:
    """Manually add a supplier to the DB. Returns the new supplier ID."""
    sup = {
        "name": name,
        "website": website,
        "email": email,
        "phone": phone,
        "address": address,
        "state": state,
        "country": country,
        "categories": categories or [],
        "certifications": certifications or [],
        "min_order": min_order,
        "notes": notes,
    }
    sup["score"] = score_supplier(sup)
    now = datetime.utcnow().isoformat()

    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO wholesale_suppliers
               (name, website, email, phone, address, state, country,
                categories, min_order, certifications, score, source,
                notes, status, scraped_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, 'new', ?, ?)""",
            (
                name, website, email, phone, address, state, country,
                json.dumps(categories or []),
                min_order,
                json.dumps(certifications or []),
                sup["score"],
                notes,
                now, now,
            ),
        )
        conn.commit()
        supplier_id = cur.lastrowid
        print(f"Added supplier '{name}' (ID: {supplier_id}, Score: {sup['score']})")
        return supplier_id
    except sqlite3.IntegrityError:
        print(f"Supplier '{name}' with website '{website}' already exists.", file=sys.stderr)
        return -1
    finally:
        conn.close()


def update_status(supplier_id: int, status: str, notes: str = None) -> bool:
    """Update a supplier's relationship status."""
    valid = ("new", "contacted", "approved", "rejected", "active")
    if status not in valid:
        print(f"Invalid status '{status}'. Must be one of: {valid}", file=sys.stderr)
        return False

    conn = get_db()
    try:
        now = datetime.utcnow().isoformat()
        parts = ["status = ?", "updated_at = ?"]
        params: list = [status, now]
        if notes:
            parts.append("notes = COALESCE(notes, '') || char(10) || ?")
            params.append(f"[{now[:10]}] {notes}")
        params.append(supplier_id)

        rows = conn.execute(
            f"UPDATE wholesale_suppliers SET {', '.join(parts)} WHERE id = ?",
            params,
        ).rowcount
        conn.commit()
        if rows:
            print(f"Supplier {supplier_id} → status: {status}")
        else:
            print(f"No supplier found with ID {supplier_id}", file=sys.stderr)
        return rows > 0
    finally:
        conn.close()


def log_contact(
    supplier_id: int,
    contact_type: str,
    notes: str = None,
    next_followup: str = None,
) -> int:
    """Log a contact event for a supplier. Returns contact ID."""
    conn = get_db()
    try:
        # Verify supplier exists
        row = conn.execute(
            "SELECT id, name FROM wholesale_suppliers WHERE id = ?", (supplier_id,)
        ).fetchone()
        if not row:
            print(f"No supplier found with ID {supplier_id}", file=sys.stderr)
            return -1

        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            """INSERT INTO supplier_contacts
               (supplier_id, contact_type, date, notes, next_followup)
               VALUES (?, ?, ?, ?, ?)""",
            (supplier_id, contact_type, now, notes, next_followup),
        )

        # Auto-update status to 'contacted' if currently 'new'
        conn.execute(
            """UPDATE wholesale_suppliers SET status = 'contacted', updated_at = ?
               WHERE id = ? AND status = 'new'""",
            (now, supplier_id),
        )
        conn.commit()

        contact_id = cur.lastrowid
        followup_msg = f", followup: {next_followup}" if next_followup else ""
        print(f"Logged {contact_type} with '{row['name']}' (contact #{contact_id}{followup_msg})")
        return contact_id
    finally:
        conn.close()


def get_followups(days: int = 7) -> list[dict]:
    """Get suppliers due for followup within the next N days."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() + timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT sc.id AS contact_id, sc.supplier_id, ws.name, ws.status,
                      sc.contact_type, sc.date AS last_contact, sc.notes,
                      sc.next_followup
               FROM supplier_contacts sc
               JOIN wholesale_suppliers ws ON ws.id = sc.supplier_id
               WHERE sc.next_followup IS NOT NULL
                 AND sc.next_followup <= ?
                 AND ws.status NOT IN ('rejected')
               ORDER BY sc.next_followup ASC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def import_from_csv(csv_path: str) -> int:
    """Bulk import suppliers from a CSV file. Returns count imported."""
    path = Path(csv_path)
    if not path.exists():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 0

    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize field names (lowercase, strip)
            row = {k.lower().strip(): v.strip() for k, v in row.items() if v}

            cats = row.get("categories", "[]")
            if not cats.startswith("["):
                cats = json.dumps([c.strip() for c in cats.split(",") if c.strip()])

            certs = row.get("certifications", "[]")
            if not certs.startswith("["):
                certs = json.dumps([c.strip() for c in certs.split(",") if c.strip()])

            sup_id = add_supplier(
                name=row.get("name", "Unknown"),
                website=row.get("website"),
                email=row.get("email"),
                phone=row.get("phone"),
                address=row.get("address"),
                state=row.get("state"),
                country=row.get("country", "US"),
                categories=json.loads(cats),
                min_order=row.get("min_order"),
                certifications=json.loads(certs),
                notes=row.get("notes"),
            )
            if sup_id > 0:
                count += 1

    print(f"\nImported {count} suppliers from {csv_path}")
    return count


def export_suppliers(output_path: str, min_score: int = 50, status: str = None) -> int:
    """Export suppliers to CSV. Returns count exported."""
    suppliers = rank_suppliers(min_score=min_score)
    if status:
        suppliers = [s for s in suppliers if s["status"] == status]

    if not suppliers:
        print("No suppliers match the criteria.", file=sys.stderr)
        return 0

    fieldnames = [
        "id", "name", "website", "email", "phone", "address", "state",
        "country", "categories", "min_order", "certifications", "score",
        "source", "status", "notes", "scraped_at", "updated_at",
    ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(suppliers)

    print(f"Exported {len(suppliers)} suppliers to {output_path}")
    return len(suppliers)


def get_stats() -> dict:
    """Return supplier statistics."""
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM wholesale_suppliers").fetchone()[0]

        # By status
        status_rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM wholesale_suppliers GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
        by_status = {r["status"]: r["cnt"] for r in status_rows}

        # By source
        source_rows = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM wholesale_suppliers GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        by_source = {r["source"]: r["cnt"] for r in source_rows}

        # Score distribution
        score_dist = {}
        for label, lo, hi in [("0-19", 0, 19), ("20-39", 20, 39), ("40-59", 40, 59),
                               ("60-79", 60, 79), ("80-100", 80, 100)]:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM wholesale_suppliers WHERE score BETWEEN ? AND ?",
                (lo, hi),
            ).fetchone()[0]
            score_dist[label] = cnt

        # Top categories
        all_cats = conn.execute("SELECT categories FROM wholesale_suppliers").fetchall()
        cat_counts: dict[str, int] = {}
        for row in all_cats:
            try:
                cats = json.loads(row["categories"])
                for c in cats:
                    cat_counts[c] = cat_counts.get(c, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        top_categories = dict(sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10])

        # Avg score
        avg = conn.execute("SELECT AVG(score) FROM wholesale_suppliers").fetchone()[0]

        # Pending followups
        now = datetime.utcnow().isoformat()
        pending = conn.execute(
            "SELECT COUNT(*) FROM supplier_contacts WHERE next_followup IS NOT NULL AND next_followup <= ?",
            (now,),
        ).fetchone()[0]

        return {
            "total_suppliers": total,
            "by_status": by_status,
            "by_source": by_source,
            "score_distribution": score_dist,
            "top_categories": top_categories,
            "average_score": round(avg, 1) if avg else 0,
            "overdue_followups": pending,
        }
    finally:
        conn.close()


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_supplier_table(suppliers: list[dict], limit: int = 50):
    """Pretty-print a list of suppliers."""
    if not suppliers:
        print("No suppliers found.")
        return

    print(f"\n{'ID':>5}  {'Score':>5}  {'Status':<10}  {'Name':<35}  {'Source':<16}  {'Website':<35}")
    print("-" * 115)
    for s in suppliers[:limit]:
        print(
            f"{s.get('id', '-'):>5}  "
            f"{s.get('score', 0):>5}  "
            f"{(s.get('status') or 'new'):<10}  "
            f"{(s.get('name') or '')[:35]:<35}  "
            f"{(s.get('source') or '')[:16]:<16}  "
            f"{(s.get('website') or '')[:35]:<35}"
        )
    if len(suppliers) > limit:
        print(f"\n  ... and {len(suppliers) - limit} more (use --min-score to narrow)")


def _print_followups(followups: list[dict]):
    """Pretty-print followup list."""
    if not followups:
        print("No followups due.")
        return

    print(f"\n{'SupID':>5}  {'Name':<30}  {'Status':<10}  {'Type':<8}  {'Due':<12}  {'Notes':<40}")
    print("-" * 115)
    for f in followups:
        print(
            f"{f['supplier_id']:>5}  "
            f"{f['name'][:30]:<30}  "
            f"{f['status']:<10}  "
            f"{f['contact_type']:<8}  "
            f"{(f['next_followup'] or '')[:12]:<12}  "
            f"{(f['notes'] or '')[:40]:<40}"
        )


def _print_stats(stats: dict):
    """Pretty-print statistics."""
    print(f"\n{'='*50}")
    print(f"  WHOLESALE SUPPLIER DATABASE STATS")
    print(f"{'='*50}")
    print(f"  Total suppliers:    {stats['total_suppliers']}")
    print(f"  Average score:      {stats['average_score']}")
    print(f"  Overdue followups:  {stats['overdue_followups']}")

    print(f"\n  By Status:")
    for status, cnt in stats["by_status"].items():
        print(f"    {status:<12} {cnt:>5}")

    print(f"\n  By Source:")
    for source, cnt in stats["by_source"].items():
        print(f"    {(source or 'unknown'):<16} {cnt:>5}")

    print(f"\n  Score Distribution:")
    for bracket, cnt in stats["score_distribution"].items():
        bar = "#" * min(cnt, 40)
        print(f"    {bracket:<8} {cnt:>5}  {bar}")

    if stats["top_categories"]:
        print(f"\n  Top Categories:")
        for cat, cnt in stats["top_categories"].items():
            print(f"    {cat:<30} {cnt:>5}")

    print(f"{'='*50}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wholesale Supplier Finder — discover, score, and manage suppliers"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = sub.add_parser("search", help="Search for suppliers by category")
    p_search.add_argument("--category", "-c", required=True, help="Product category")
    p_search.add_argument(
        "--sources", "-s", default="google,thomasnet",
        help="Comma-separated sources: google, thomasnet, wholesale_central (default: google,thomasnet)"
    )

    # list
    p_list = sub.add_parser("list", help="List suppliers from database")
    p_list.add_argument("--min-score", type=int, default=0, help="Minimum score filter")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--category", help="Filter by category")

    # add
    p_add = sub.add_parser("add", help="Manually add a supplier")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--website")
    p_add.add_argument("--email")
    p_add.add_argument("--phone")
    p_add.add_argument("--address")
    p_add.add_argument("--state")
    p_add.add_argument("--country", default="US")
    p_add.add_argument("--categories", default="[]", help="JSON array of categories")
    p_add.add_argument("--min-order")
    p_add.add_argument("--certifications", default="[]", help="JSON array of certs")
    p_add.add_argument("--notes")

    # contact
    p_contact = sub.add_parser("contact", help="Log a contact event")
    p_contact.add_argument("--id", type=int, required=True, help="Supplier ID")
    p_contact.add_argument("--type", required=True, choices=["email", "call", "meeting"])
    p_contact.add_argument("--notes")
    p_contact.add_argument("--followup", help="Next followup date (YYYY-MM-DD)")

    # followups
    p_followup = sub.add_parser("followups", help="Show due followups")
    p_followup.add_argument("--days", type=int, default=7, help="Lookahead window in days")

    # export
    p_export = sub.add_parser("export", help="Export suppliers to CSV")
    p_export.add_argument("--output", "-o", required=True, help="Output CSV path")
    p_export.add_argument("--min-score", type=int, default=50)
    p_export.add_argument("--status", help="Filter by status")

    # import
    p_import = sub.add_parser("import", help="Import suppliers from CSV")
    p_import.add_argument("--csv", required=True, help="Path to CSV file")

    # stats
    sub.add_parser("stats", help="Show supplier database statistics")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "search":
        sources = [s.strip() for s in args.sources.split(",")]
        results = search_suppliers(args.category, sources=sources)
        _print_supplier_table(results)

    elif args.command == "list":
        suppliers = rank_suppliers(category=args.category, min_score=args.min_score)
        if args.status:
            suppliers = [s for s in suppliers if s["status"] == args.status]
        _print_supplier_table(suppliers)

    elif args.command == "add":
        try:
            cats = json.loads(args.categories)
        except json.JSONDecodeError:
            cats = [c.strip() for c in args.categories.split(",") if c.strip()]
        try:
            certs = json.loads(args.certifications)
        except json.JSONDecodeError:
            certs = [c.strip() for c in args.certifications.split(",") if c.strip()]

        add_supplier(
            name=args.name,
            website=args.website,
            email=args.email,
            phone=args.phone,
            address=args.address,
            state=args.state,
            country=args.country,
            categories=cats,
            min_order=args.min_order,
            certifications=certs,
            notes=args.notes,
        )

    elif args.command == "contact":
        log_contact(
            supplier_id=args.id,
            contact_type=args.type,
            notes=args.notes,
            next_followup=args.followup,
        )

    elif args.command == "followups":
        followups = get_followups(days=args.days)
        _print_followups(followups)

    elif args.command == "export":
        export_suppliers(args.output, min_score=args.min_score, status=args.status)

    elif args.command == "import":
        import_from_csv(args.csv)

    elif args.command == "stats":
        stats = get_stats()
        _print_stats(stats)


if __name__ == "__main__":
    main()
