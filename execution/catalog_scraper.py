#!/usr/bin/env python3
from __future__ import annotations
"""
Script: catalog_scraper.py
Purpose: Universal retailer catalog dumper for FBA online arbitrage.
         Point it at any real retailer URL (ShopWSS, Kohl's, CVS, Target, etc.)
         and it scrapes every product with UPC + price.

         Platform detection is automatic — Shopify stores use fast JSON API,
         other retailers use sitemap + JSON-LD/Playwright extraction.

         This is Stage 1 of the catalog sourcing pipeline (0 Keepa tokens).

Inputs:  Retailer base URL (e.g., https://www.shopwss.com)
Outputs: .tmp/sourcing/catalogs/{domain}_{date}.json

Usage:
    python execution/catalog_scraper.py https://www.shopwss.com
    python execution/catalog_scraper.py https://www.shopwss.com --limit 100
    python execution/catalog_scraper.py https://www.shopwss.com --detect-only
    python execution/catalog_scraper.py https://www.shopwss.com --resume
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# ── Constants ────────────────────────────────────────────────────────────────

CATALOG_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "catalogs"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
CHECKPOINT_INTERVAL = 100  # Save progress every N products
CATALOG_TTL_DAYS = 7  # Re-scrape if older than this

# ── Platform Detection ───────────────────────────────────────────────────────


def detect_platform(base_url: str) -> dict:
    """Auto-detect the e-commerce platform behind a retailer URL.

    Returns dict with:
        platform: str — "shopify", "sitemap_jsonld", "sitemap_playwright", "unknown"
        method: str — extraction method to use
        product_count_estimate: int — rough count if detectable
        details: dict — platform-specific info
    """
    headers = {"User-Agent": USER_AGENT}
    base = base_url.rstrip("/")
    result = {
        "platform": "unknown",
        "method": "sitemap_playwright",
        "product_count_estimate": 0,
        "details": {},
    }

    # ── Try Shopify: /products.json returns JSON ────────────────────────
    try:
        r = requests.get(f"{base}/products.json?limit=1", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "products" in data:
                # Count total via pagination
                r2 = requests.get(f"{base}/products/count.json", headers=headers, timeout=10)
                count = 0
                if r2.status_code == 200:
                    count = r2.json().get("count", 0)
                if count == 0:
                    # Estimate from page count
                    count = _estimate_shopify_count(base, headers)

                result["platform"] = "shopify"
                result["method"] = "shopify_api"
                result["product_count_estimate"] = count
                result["details"] = {"api_url": f"{base}/products.json"}
                return result
    except Exception:
        pass

    # ── Try sitemap.xml ─────────────────────────────────────────────────
    try:
        r = requests.get(f"{base}/sitemap.xml", headers=headers, timeout=10)
        if r.status_code == 200 and "<?xml" in r.text[:100]:
            product_urls = _parse_sitemap_for_products(r.text, base)
            if product_urls:
                result["platform"] = "sitemap"
                result["method"] = "sitemap_jsonld"
                result["product_count_estimate"] = len(product_urls)
                result["details"] = {"sitemap_url": f"{base}/sitemap.xml"}
                return result
    except Exception:
        pass

    # ── Try robots.txt for sitemap location ─────────────────────────────
    try:
        r = requests.get(f"{base}/robots.txt", headers=headers, timeout=10)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    r2 = requests.get(sitemap_url, headers=headers, timeout=10)
                    if r2.status_code == 200:
                        product_urls = _parse_sitemap_for_products(r2.text, base)
                        if product_urls:
                            result["platform"] = "sitemap"
                            result["method"] = "sitemap_jsonld"
                            result["product_count_estimate"] = len(product_urls)
                            result["details"] = {"sitemap_url": sitemap_url}
                            return result
    except Exception:
        pass

    return result


def _estimate_shopify_count(base: str, headers: dict) -> int:
    """Estimate Shopify product count by paginating /products.json."""
    count = 0
    page = 1
    while page <= 5:  # Sample first 5 pages
        try:
            r = requests.get(
                f"{base}/products.json?limit=250&page={page}",
                headers=headers, timeout=15,
            )
            if r.status_code != 200:
                break
            products = r.json().get("products", [])
            if not products:
                break
            count += len(products)
            if len(products) < 250:
                break  # Last page
            page += 1
        except Exception:
            break
    if page > 5:
        count = count * 10  # Rough estimate: 5 pages sampled = ~10% of total
    return count


def _parse_sitemap_for_products(xml_text: str, base_url: str) -> list[str]:
    """Parse sitemap XML and extract product URLs."""
    product_urls = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # Check if this is a sitemap index (contains other sitemaps)
    sitemap_locs = root.findall(".//sm:sitemap/sm:loc", ns)
    if sitemap_locs:
        headers = {"User-Agent": USER_AGENT}
        product_kws = ["product", "item", "catalog", "pdp", "sku"]
        skip_kws = ["image", "video", "blog", "article", "news", "facet",
                     "brand-shop", "brand-cat", "thematic", "landing", "categor"]

        # First: try product-specific sub-sitemaps
        for loc in sitemap_locs:
            url = loc.text.strip() if loc.text else ""
            if any(kw in url.lower() for kw in product_kws):
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    if r.status_code == 200:
                        found = _extract_urls_from_sitemap(r.text, ns)
                        product_urls.extend(found)
                        print(f"[catalog] Sub-sitemap {url}: {len(found)} product URLs", file=sys.stderr)
                except Exception:
                    continue

        # If none found, try ALL non-skip sub-sitemaps (e.g., sitemap_1.xml)
        if not product_urls:
            for loc in sitemap_locs:
                url = loc.text.strip() if loc.text else ""
                if any(kw in url.lower() for kw in skip_kws):
                    continue
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    if r.status_code == 200:
                        found = _extract_urls_from_sitemap(r.text, ns)
                        product_urls.extend(found)
                        print(f"[catalog] Sub-sitemap {url}: {len(found)} product URLs", file=sys.stderr)
                except Exception:
                    continue

        return product_urls

    # Direct URL list
    return _extract_urls_from_sitemap(xml_text, ns)


def _extract_urls_from_sitemap(xml_text: str, ns: dict) -> list[str]:
    """Extract URLs from a sitemap XML that look like product pages."""
    urls = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    product_patterns = [
        "/product/", "/products/", "/p/", "/item/", "/dp/",
        "/shop/", "/buy/", "/catalog/",
    ]

    for url_elem in root.findall(".//sm:url/sm:loc", ns):
        url = url_elem.text.strip() if url_elem.text else ""
        if any(p in url.lower() for p in product_patterns):
            urls.append(url)

    return urls


# ── Shopify Scraper ──────────────────────────────────────────────────────────


def scrape_shopify(base_url: str, limit: int = 0, delay: float = 0.5,
                   checkpoint_path: str | None = None,
                   resume_from: int = 0) -> list[dict]:
    """Scrape full Shopify catalog via 2-pass approach.

    Pass 1: /products.json (250/page) to get all product handles quickly.
    Pass 2: /products/{handle}.json per product to get barcodes (UPCs).

    Many Shopify stores (like ShopWSS) don't include barcode in the bulk
    /products.json endpoint but DO include it in per-product .json endpoints.

    Returns list of product dicts with UPC, price, title, url, etc.
    """
    base = base_url.rstrip("/")
    headers = {"User-Agent": USER_AGENT}
    products = []
    total_scraped = 0

    print(f"[catalog] Scraping Shopify catalog: {base}", file=sys.stderr)

    # ── Pass 1: Collect all product handles ─────────────────────────────
    print("[catalog] Pass 1: Collecting product handles...", file=sys.stderr)
    handles = []
    page = 1
    empty_pages = 0

    while True:
        try:
            r = requests.get(
                f"{base}/products.json?limit=250&page={page}",
                headers=headers, timeout=20,
            )
        except requests.RequestException as e:
            print(f"[catalog] Request error on page {page}: {e}", file=sys.stderr)
            time.sleep(5)
            continue

        if r.status_code == 429:
            print(f"[catalog] Rate limited, backing off 30s...", file=sys.stderr)
            time.sleep(30)
            continue

        if r.status_code != 200:
            break

        try:
            page_products = r.json().get("products", [])
        except (json.JSONDecodeError, ValueError):
            break

        if not page_products:
            empty_pages += 1
            if empty_pages >= 2:
                break
            page += 1
            continue

        empty_pages = 0
        for p in page_products:
            handles.append({
                "handle": p.get("handle", ""),
                "title": p.get("title", ""),
                "vendor": p.get("vendor", ""),
                "product_type": p.get("product_type", ""),
            })

        print(f"[catalog] Page {page}: {len(page_products)} products ({len(handles)} total)", file=sys.stderr)
        page += 1
        time.sleep(0.3)  # Light rate limit for listing pages

    print(f"[catalog] Pass 1 complete: {len(handles)} product handles collected", file=sys.stderr)

    if limit > 0:
        handles = handles[:limit]

    # ── Pass 2: Fetch per-product JSON for barcodes ─────────────────────
    print(f"[catalog] Pass 2: Fetching barcodes for {len(handles)} products...", file=sys.stderr)

    # Skip already-processed if resuming
    start_idx = resume_from if resume_from > 0 else 0
    if start_idx > 0:
        print(f"[catalog] Resuming from product {start_idx}", file=sys.stderr)

    for idx in range(start_idx, len(handles)):
        h = handles[idx]
        handle = h["handle"]
        if not handle:
            continue

        try:
            r = requests.get(
                f"{base}/products/{handle}.json",
                headers=headers, timeout=15,
            )
        except requests.RequestException:
            continue

        if r.status_code == 429:
            print(f"[catalog] Rate limited at product {idx}, backing off 30s...", file=sys.stderr)
            time.sleep(30)
            try:
                r = requests.get(f"{base}/products/{handle}.json", headers=headers, timeout=15)
            except requests.RequestException:
                continue

        if r.status_code != 200:
            continue

        try:
            product_data = r.json().get("product", {})
        except (json.JSONDecodeError, ValueError):
            continue

        extracted = _extract_shopify_product(product_data, base)
        products.extend(extracted)
        total_scraped += 1

        if (idx + 1) % 50 == 0:
            with_upc = sum(1 for p in products if p.get("upc"))
            print(
                f"[catalog] Progress: {idx + 1}/{len(handles)} products, "
                f"{len(products)} variants ({with_upc} with UPC)",
                file=sys.stderr,
            )

        # Checkpoint
        if checkpoint_path and (idx + 1) % CHECKPOINT_INTERVAL == 0:
            _save_checkpoint(checkpoint_path, products, idx + 1)

        time.sleep(delay)

    print(
        f"[catalog] Done: {total_scraped} products, {len(products)} variants with data",
        file=sys.stderr,
    )
    return products


def _extract_shopify_product(product: dict, base_url: str) -> list[dict]:
    """Extract product variants from a Shopify product JSON."""
    results = []
    title = product.get("title", "")
    handle = product.get("handle", "")
    product_type = product.get("product_type", "")
    vendor = product.get("vendor", "")
    product_url = f"{base_url}/products/{handle}" if handle else ""
    images = product.get("images", [])
    image_url = images[0].get("src", "") if images else ""

    for variant in product.get("variants", []):
        barcode = (variant.get("barcode") or "").strip()
        sku = (variant.get("sku") or "").strip()
        price_str = variant.get("price", "0")
        compare_price_str = variant.get("compare_at_price") or "0"
        available = variant.get("available", True)

        try:
            price = float(price_str)
        except (ValueError, TypeError):
            price = 0

        try:
            compare_price = float(compare_price_str) if compare_price_str else 0
        except (ValueError, TypeError):
            compare_price = 0

        # Validate UPC: must be 12-13 digits
        upc = _clean_upc(barcode) if barcode else None

        results.append({
            "title": title,
            "variant_title": variant.get("title", ""),
            "upc": upc,
            "sku": sku,
            "price": price,
            "compare_at_price": compare_price,
            "available": available,
            "product_url": product_url,
            "image_url": image_url,
            "brand": vendor,
            "category": product_type,
            "variant_id": variant.get("id"),
            "extraction_method": "shopify_api",
        })

    return results


# ── Sitemap + JSON-LD Scraper ────────────────────────────────────────────────


def scrape_sitemap_jsonld(base_url: str, limit: int = 0, delay: float = 1.0,
                          checkpoint_path: str | None = None,
                          resume_from: int = 0) -> list[dict]:
    """Scrape a retailer catalog via sitemap + JSON-LD extraction from product pages.

    Works on most e-commerce sites that have structured data.
    Falls back to meta tags if JSON-LD not present.
    """
    base = base_url.rstrip("/")
    headers = {"User-Agent": USER_AGENT}
    products = []

    print(f"[catalog] Scraping via sitemap + JSON-LD: {base}", file=sys.stderr)

    # Get product URLs from sitemap (try multiple locations)
    product_urls = []
    sitemap_locations = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
    ]

    # Check robots.txt for sitemap location
    try:
        robots = requests.get(f"{base}/robots.txt", headers=headers, timeout=10)
        if robots.status_code == 200:
            for line in robots.text.split("\n"):
                if line.lower().startswith("sitemap:"):
                    sm_url = line.split(":", 1)[1].strip()
                    if sm_url and sm_url not in sitemap_locations:
                        sitemap_locations.insert(0, sm_url)
    except Exception:
        pass

    for sitemap_url in sitemap_locations:
        try:
            r = requests.get(sitemap_url, headers=headers, timeout=15)
            if r.status_code == 200 and "<" in r.text[:100]:
                product_urls = _parse_sitemap_for_products(r.text, base)
                if product_urls:
                    print(f"[catalog] Found sitemap at {sitemap_url}", file=sys.stderr)
                    break
        except Exception:
            continue

    if not product_urls:
        print(f"[catalog] No sitemap/product URLs found for {base}", file=sys.stderr)
        return []

    if not product_urls:
        print("[catalog] No product URLs found in sitemap", file=sys.stderr)
        return []

    print(f"[catalog] Found {len(product_urls)} product URLs in sitemap", file=sys.stderr)

    # Skip already-processed URLs if resuming
    if resume_from > 0:
        product_urls = product_urls[resume_from:]
        print(f"[catalog] Resuming from index {resume_from}", file=sys.stderr)

    if limit > 0:
        product_urls = product_urls[:limit]

    # Probe first 5 URLs to detect if we need Playwright (403/JS-rendered)
    use_playwright = False
    fail_count = 0
    for probe_url in product_urls[:5]:
        try:
            r = requests.get(probe_url, headers=headers, timeout=10)
            if r.status_code in (403, 429):
                fail_count += 1
            elif r.status_code == 200:
                extracted = _extract_jsonld_product(r.text, probe_url)
                if not extracted:
                    fail_count += 1
        except Exception:
            fail_count += 1

    if fail_count >= 3:
        print(f"[catalog] {fail_count}/5 probe pages failed — switching to Playwright", file=sys.stderr)
        use_playwright = True

    # ── Playwright-based scraping ────────────────────────────────────
    if use_playwright:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[catalog] Playwright not installed — cannot scrape JS-rendered pages", file=sys.stderr)
            return products

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            for idx, url in enumerate(product_urls):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(1)  # Let JS render
                    html = page.content()
                    extracted = _extract_jsonld_product(html, url)
                    if extracted:
                        products.append(extracted)
                except Exception as e:
                    if idx < 3:
                        print(f"[catalog] Playwright error on {url}: {e}", file=sys.stderr)
                    continue

                if (idx + 1) % 50 == 0:
                    print(
                        f"[catalog] Progress: {idx + 1}/{len(product_urls)} pages, "
                        f"{len(products)} products extracted (Playwright)",
                        file=sys.stderr,
                    )
                if checkpoint_path and (idx + 1) % CHECKPOINT_INTERVAL == 0:
                    _save_checkpoint(checkpoint_path, products, resume_from + idx + 1)

            browser.close()

    else:
        # ── Standard requests-based scraping ────────────────────────────
        for idx, url in enumerate(product_urls):
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code != 200:
                    continue

                extracted = _extract_jsonld_product(r.text, url)
                if extracted:
                    products.append(extracted)

            except Exception as e:
                if idx < 3:
                    print(f"[catalog] Error scraping {url}: {e}", file=sys.stderr)
                continue

            if (idx + 1) % 50 == 0:
                print(
                    f"[catalog] Progress: {idx + 1}/{len(product_urls)} pages, "
                    f"{len(products)} products extracted",
                    file=sys.stderr,
                )
            if checkpoint_path and (idx + 1) % CHECKPOINT_INTERVAL == 0:
                _save_checkpoint(checkpoint_path, products, resume_from + idx + 1)

            time.sleep(delay)

    print(
        f"[catalog] Done: {len(product_urls)} pages visited, "
        f"{len(products)} products extracted"
        f"{' (via Playwright)' if use_playwright else ''}",
        file=sys.stderr,
    )
    return products


def _extract_jsonld_product(html: str, url: str) -> dict | None:
    """Extract product data from HTML using JSON-LD and meta tag fallbacks."""
    # ── Try JSON-LD ─────────────────────────────────────────────────────
    jsonld_pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in jsonld_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))

            # Handle @graph arrays (common pattern on many e-commerce sites)
            if isinstance(data, dict) and "@graph" in data:
                graph = data["@graph"]
                if isinstance(graph, list):
                    data = next((d for d in graph if d.get("@type") == "Product"), None)
                    if not data:
                        continue

            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Product"), None)
            if not data or data.get("@type") != "Product":
                continue

            upc = None
            for field in ("gtin12", "gtin13", "gtin", "gtin14", "productID", "sku", "mpn"):
                val = data.get(field, "")
                cleaned = _clean_upc(str(val))
                if cleaned:
                    upc = cleaned
                    break

            # Price from offers (handle multiple nesting patterns)
            price = 0
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            # Handle nested offers.offers pattern
            if isinstance(offers, dict) and "offers" in offers:
                inner = offers["offers"]
                if isinstance(inner, list) and inner:
                    offers = inner[0]
                elif isinstance(inner, dict):
                    offers = inner
            price_str = offers.get("price", "0")
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                # Try lowPrice/highPrice
                try:
                    price = float(offers.get("lowPrice", "0"))
                except (ValueError, TypeError):
                    pass

            return {
                "title": data.get("name", ""),
                "variant_title": "",
                "upc": upc,
                "sku": data.get("sku", ""),
                "price": price,
                "compare_at_price": 0,
                "available": offers.get("availability", "").lower() != "outofstock",
                "product_url": url,
                "image_url": data.get("image", ""),
                "brand": data.get("brand", {}).get("name", "") if isinstance(data.get("brand"), dict) else str(data.get("brand", "")),
                "category": data.get("category", ""),
                "variant_id": None,
                "extraction_method": "jsonld",
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    # ── Fallback: meta tags + data attributes ────────────────────────────
    upc = None
    for pattern in [
        r'<meta[^>]*itemprop=["\']gtin12["\'][^>]*content=["\'](\d{12})["\']',
        r'<meta[^>]*itemprop=["\']gtin13["\'][^>]*content=["\'](\d{13})["\']',
        r'<meta[^>]*itemprop=["\']gtin["\'][^>]*content=["\'](\d{12,13})["\']',
        r'<meta[^>]*name=["\']upc["\'][^>]*content=["\'](\d{12,13})["\']',
        r'<meta[^>]*property=["\']product:upc["\'][^>]*content=["\'](\d{12,13})["\']',
        r'<meta[^>]*property=["\']og:upc["\'][^>]*content=["\'](\d{12,13})["\']',
        r'data-upc=["\'](\d{12,13})["\']',
        r'data-gtin=["\'](\d{12,13})["\']',
        r'data-ean=["\'](\d{12,13})["\']',
        r'"upc"\s*:\s*"(\d{12,13})"',
        r'"gtin12"\s*:\s*"(\d{12})"',
        r'"gtin13"\s*:\s*"(\d{13})"',
    ]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            upc = _clean_upc(m.group(1))
            if upc:
                break

    title = ""
    m = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html)
    if m:
        title = m.group(1)

    price = 0
    m = re.search(r'<meta[^>]*property=["\']product:price:amount["\'][^>]*content=["\']([^"\']+)["\']', html)
    if m:
        try:
            price = float(m.group(1))
        except ValueError:
            pass

    if not title and not upc:
        return None

    return {
        "title": title,
        "variant_title": "",
        "upc": upc,
        "sku": "",
        "price": price,
        "compare_at_price": 0,
        "available": True,
        "product_url": url,
        "image_url": "",
        "brand": "",
        "category": "",
        "variant_id": None,
        "extraction_method": "meta_tags",
    }


# ── Utilities ────────────────────────────────────────────────────────────────


def _clean_upc(raw: str) -> str | None:
    """Validate and clean a UPC/EAN barcode. Returns 12-13 digit string or None."""
    digits = re.sub(r"\D", "", raw.strip())
    if len(digits) == 12 or len(digits) == 13:
        return digits
    # Try zero-padding short codes
    if 8 <= len(digits) < 12:
        padded = digits.zfill(12)
        return padded
    return None


def _save_checkpoint(path: str, products: list[dict], resume_index: int):
    """Save scraping checkpoint for resume capability."""
    checkpoint = {
        "resume_index": resume_index,
        "product_count": len(products),
        "timestamp": datetime.now().isoformat(),
        "products": products,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(checkpoint, f)
    print(f"[catalog] Checkpoint saved: {len(products)} products at index {resume_index}", file=sys.stderr)


def _load_checkpoint(path: str) -> dict | None:
    """Load a previous checkpoint."""
    if not Path(path).exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ── Main Scrape Function ─────────────────────────────────────────────────────


def scrape_catalog(base_url: str, limit: int = 0, delay: float = 0,
                   resume: bool = False, detect_only: bool = False) -> list[dict]:
    """Main entry point: scrape a retailer's full catalog.

    Args:
        base_url: Retailer URL (e.g., https://www.shopwss.com)
        limit: Max products to scrape (0 = unlimited)
        delay: Seconds between requests (0 = auto based on platform)
        resume: Resume from last checkpoint
        detect_only: Just detect platform and return info

    Returns:
        List of product dicts with UPC, price, title, url, etc.
    """
    domain = urlparse(base_url).netloc.replace("www.", "")

    # Detect platform
    print(f"[catalog] Detecting platform for {domain}...", file=sys.stderr)
    platform_info = detect_platform(base_url)
    print(
        f"[catalog] Platform: {platform_info['platform']} "
        f"(method: {platform_info['method']}, "
        f"~{platform_info['product_count_estimate']} products)",
        file=sys.stderr,
    )

    if detect_only:
        return platform_info

    # Set up paths
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = CATALOG_DIR / f"{domain}_{date_str}.json"
    checkpoint_path = str(CATALOG_DIR / f"{domain}_{date_str}_checkpoint.json")

    # Check for fresh existing catalog
    if output_path.exists() and not resume:
        age_days = (time.time() - output_path.stat().st_mtime) / 86400
        if age_days < CATALOG_TTL_DAYS:
            print(f"[catalog] Fresh catalog exists ({age_days:.1f} days old), loading it", file=sys.stderr)
            with open(output_path) as f:
                return json.load(f)

    # Resume from checkpoint?
    resume_from = 0
    existing_products = []
    if resume:
        cp = _load_checkpoint(checkpoint_path)
        if cp:
            resume_from = cp["resume_index"]
            existing_products = cp.get("products", [])
            print(
                f"[catalog] Resuming: {len(existing_products)} products already scraped, "
                f"continuing from index {resume_from}",
                file=sys.stderr,
            )

    # Auto-set delay if not specified
    if delay == 0:
        delay = 0.5 if platform_info["method"] == "shopify_api" else 1.5

    # Dispatch to appropriate scraper
    method = platform_info["method"]
    if method == "shopify_api":
        new_products = scrape_shopify(
            base_url, limit=limit, delay=delay,
            checkpoint_path=checkpoint_path, resume_from=resume_from,
        )
    elif method == "sitemap_jsonld":
        new_products = scrape_sitemap_jsonld(
            base_url, limit=limit, delay=delay,
            checkpoint_path=checkpoint_path, resume_from=resume_from,
        )
    else:
        print(f"[catalog] Unsupported method: {method}. Try sitemap_jsonld as fallback.", file=sys.stderr)
        new_products = scrape_sitemap_jsonld(
            base_url, limit=limit, delay=delay,
            checkpoint_path=checkpoint_path, resume_from=resume_from,
        )

    # Merge with existing (resume)
    all_products = existing_products + new_products

    # Save final catalog
    with open(output_path, "w") as f:
        json.dump(all_products, f, indent=2)
    print(f"[catalog] Catalog saved: {output_path} ({len(all_products)} variants)", file=sys.stderr)

    # Clean up checkpoint
    cp_path = Path(checkpoint_path)
    if cp_path.exists():
        cp_path.unlink()

    return all_products


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape a retailer's full product catalog")
    parser.add_argument("url", help="Retailer base URL (e.g., https://www.shopwss.com)")
    parser.add_argument("--limit", type=int, default=0, help="Max products to scrape (0=unlimited)")
    parser.add_argument("--delay", type=float, default=0, help="Seconds between requests (0=auto)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--detect-only", action="store_true", help="Just detect platform, don't scrape")
    args = parser.parse_args()

    result = scrape_catalog(
        args.url,
        limit=args.limit,
        delay=args.delay,
        resume=args.resume,
        detect_only=args.detect_only,
    )

    if args.detect_only:
        print(json.dumps(result, indent=2))
    else:
        # Summary
        total = len(result)
        with_upc = sum(1 for p in result if p.get("upc"))
        in_stock = sum(1 for p in result if p.get("available", True))
        print(f"\n{'='*60}")
        print(f"Catalog Summary:")
        print(f"  Total variants:  {total}")
        print(f"  With UPC:        {with_upc} ({with_upc*100//max(total,1)}%)")
        print(f"  In stock:        {in_stock}")
        print(f"  Price range:     ${min((p['price'] for p in result if p.get('price',0)>0), default=0):.2f} - ${max((p['price'] for p in result if p.get('price',0)>0), default=0):.2f}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
