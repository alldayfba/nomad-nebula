"""ASIN / retailer URL / buy cost / MOQ extractor for Nova message pre-processing.

Pure functions, no network, no side effects. Hard caps prevent abuse
(a student pasting 50 ASINs will process only the first 5).
Retailer URL extraction enforces a domain whitelist — closes SSRF surface.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# B[A-Z0-9]{9} — Amazon ASIN format. Books (ISBN-10) can also appear as ASINs but
# always start with digits; we intentionally skip those to avoid false positives
# on prices, quantities, etc.
_ASIN_RE = re.compile(r"\bB[A-Z0-9]{9}\b")

# /dp/ASIN and /gp/product/ASIN capture — matches path segments even with
# trailing slashes, query strings, or ?th=1 variants.
_ASIN_URL_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/(B[A-Z0-9]{9})")

# Retailer buy-cost patterns, in priority order.
# "purchasing at 9.04", "Buy cost: 6.49", "im buying at 16.3", "$4.50", "for 7$",
# "3.99 and B0B4HWPJ56" (leading decimal before an ASIN).
_BUY_COST_PATTERNS = (
    re.compile(
        r"(?:purchasing|buying|purchased|bought|buy\s*(?:cost|price)?|cost)\s*"
        r"(?:at|for|@|=|:)?\s*\$?(\d{1,4}(?:\.\d{1,2})?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\$(\d{1,4}(?:\.\d{1,2})?)\b"),
    re.compile(r"\b(\d{1,4}(?:\.\d{1,2})?)\s*\$"),
    # Leading decimal in the message body, right before an ASIN reference
    # ("3.99 and B0B4HWPJ56") — must have 2-decimal precision to avoid
    # false-positives on random numbers like "I have 3 units."
    re.compile(r"\b(\d{1,4}\.\d{2})\s+(?:and|for|at)?\s*B[A-Z0-9]{9}\b"),
)

# MOQ / quantity patterns.
_MOQ_PATTERNS = (
    re.compile(r"\bMOQ\s*(?:of)?\s*:?\s*(\d{1,5})\b", re.IGNORECASE),
    re.compile(r"\bq(?:t)?y\s*(?:of)?\s*:?\s*(\d{1,5})\b", re.IGNORECASE),
    re.compile(r"\b(\d{2,5})\s*(?:units?|pieces?|pcs?)\b", re.IGNORECASE),
)

# Amazon storefront domain whitelist for URL-based ASIN extraction.
_AMAZON_DOMAINS = (
    "amazon.com", "www.amazon.com",
    "amazon.co.uk", "www.amazon.co.uk",
    "amazon.de", "www.amazon.de",
    "amazon.ca", "www.amazon.ca",
    "a.co",  # Amazon short-link service
)

# Retailer domains we recognize as legitimate arbitrage source URLs.
# Used by extract_retailer_urls(). SSRF protection: any URL whose host is not
# in this list, or which resolves to a private/loopback IP, is rejected.
_RETAILER_DOMAINS = (
    "walmart.com", "www.walmart.com",
    "target.com", "www.target.com",
    "cvs.com", "www.cvs.com",
    "walgreens.com", "www.walgreens.com",
    "bestbuy.com", "www.bestbuy.com",
    "homedepot.com", "www.homedepot.com",
    "lowes.com", "www.lowes.com",
    "costco.com", "www.costco.com",
    "samsclub.com", "www.samsclub.com",
    "kohls.com", "www.kohls.com",
    "macys.com", "www.macys.com",
    "marymaxim.com", "www.marymaxim.com",
)

# Hard limits — prevent token-exhaustion DoS.
MAX_ASINS_PER_MESSAGE = 5
MAX_URL_LENGTH = 500
MAX_INPUT_LENGTH = 10_000


def _is_safe_host(host: str) -> bool:
    """Reject hosts that resolve to loopback, link-local, or private IPs.

    This is a best-effort static check: for IP literals we reject private ranges
    directly; for DNS names we trust the domain whitelist to have screened them.
    No DNS resolution happens here (that would itself be an SSRF vector in tests).
    """
    if not host:
        return False
    host = host.lower().strip()
    # Block obvious internal targets even if someone added them to a whitelist
    # by mistake.
    if host in {"localhost", "localhost.localdomain"}:
        return False
    # If it's an IP literal, screen it.
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass  # not an IP — fine, domain-whitelist will decide
    return True


def _validate_url(raw: str, allowed_domains: tuple[str, ...]) -> str | None:
    """Parse and validate a URL against a domain whitelist.

    Returns the normalized URL if safe, else None.
    """
    if not raw or len(raw) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if host not in allowed_domains:
        return None
    if not _is_safe_host(host):
        return None
    return raw


def extract_asins(text: str) -> list[str]:
    """Extract up to MAX_ASINS_PER_MESSAGE unique ASINs from a message.

    Picks up bare ASINs, /dp/ URLs, /gp/product/ URLs, and /gp/aw/d/ mobile URLs.
    Order-preserving dedupe. Truncates input to MAX_INPUT_LENGTH first so a
    huge paste can't blow regex time.
    """
    if not text:
        return []
    text = text[:MAX_INPUT_LENGTH]

    seen: list[str] = []
    # URL matches first — they're more specific and less likely to false-positive
    # than bare regex matches.
    for match in _ASIN_URL_RE.finditer(text):
        asin = match.group(1)
        if asin not in seen:
            seen.append(asin)
            if len(seen) >= MAX_ASINS_PER_MESSAGE:
                return seen

    for match in _ASIN_RE.finditer(text):
        asin = match.group(0)
        if asin not in seen:
            seen.append(asin)
            if len(seen) >= MAX_ASINS_PER_MESSAGE:
                break

    return seen


def extract_amazon_urls(text: str) -> list[str]:
    """Extract Amazon product URLs (validated against domain whitelist)."""
    if not text:
        return []
    text = text[:MAX_INPUT_LENGTH]
    urls: list[str] = []
    for raw in re.findall(r"https?://\S+", text):
        clean = raw.rstrip(").,;:")
        validated = _validate_url(clean, _AMAZON_DOMAINS)
        if validated and validated not in urls:
            urls.append(validated)
    return urls


def extract_retailer_urls(text: str) -> list[str]:
    """Extract whitelisted retailer URLs (Walmart, Target, etc.).

    Used when a student pastes a retailer source link alongside an ASIN for
    arbitrage analysis. Returns only URLs on whitelisted domains.
    """
    if not text:
        return []
    text = text[:MAX_INPUT_LENGTH]
    urls: list[str] = []
    for raw in re.findall(r"https?://\S+", text):
        clean = raw.rstrip(").,;:")
        validated = _validate_url(clean, _RETAILER_DOMAINS)
        if validated and validated not in urls:
            urls.append(validated)
    return urls


def extract_buy_cost(text: str) -> float | None:
    """Extract a buy cost if the message mentions one.

    Tries verb-phrase patterns ("purchasing at 9.04") before bare dollar amounts
    to avoid picking up "I sold 5 units at $10" as a buy cost. Returns None if
    no plausible cost is found.
    """
    if not text:
        return None
    text = text[:MAX_INPUT_LENGTH]
    for pattern in _BUY_COST_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = float(match.group(1))
                # Reject implausible values — buy costs of Amazon arbitrage products
                # are realistically between $0.50 and $5000.
                if 0.10 <= value <= 5000.0:
                    return value
            except (ValueError, IndexError):
                continue
    return None


def extract_moq(text: str) -> int | None:
    """Extract an MOQ / bulk quantity if present."""
    if not text:
        return None
    text = text[:MAX_INPUT_LENGTH]
    for pattern in _MOQ_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = int(match.group(1))
                if 1 <= value <= 100_000:
                    return value
            except (ValueError, IndexError):
                continue
    return None


def extract_all(text: str) -> dict:
    """One-shot extraction — returns everything a downstream handler needs.

    Shape: {"asins": [...], "amazon_urls": [...], "retailer_urls": [...],
            "buy_cost": float|None, "moq": int|None}
    """
    return {
        "asins": extract_asins(text),
        "amazon_urls": extract_amazon_urls(text),
        "retailer_urls": extract_retailer_urls(text),
        "buy_cost": extract_buy_cost(text),
        "moq": extract_moq(text),
    }
