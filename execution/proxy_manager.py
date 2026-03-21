#!/usr/bin/env python3
"""
Script: proxy_manager.py
Purpose: Proxy rotation for Playwright-based retail scraping. Prevents CAPTCHA
         blocks by rotating IPs across requests.

Supports:
  - SmartProxy residential proxies (PROXY_PROVIDER=smartproxy)
  - BrightData residential proxies (PROXY_PROVIDER=brightdata)
  - Free proxy lists as fallback (PROXY_PROVIDER=free, default)
  - No proxy / direct (PROXY_PROVIDER=none)

Usage:
  from proxy_manager import ProxyManager

  pm = ProxyManager()
  proxy = pm.next()  # Returns Playwright proxy dict or None
  # Use: browser = playwright.chromium.launch(proxy=proxy)

  pm.mark_failed(proxy)  # Mark a proxy as blocked, rotates it out
  pm.mark_success(proxy)  # Record successful request

Config (.env):
  PROXY_PROVIDER=free|smartproxy|brightdata|none
  PROXY_API_KEY=your_key_here (for paid providers)
"""

import os
import random
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Free proxy list — these rotate frequently, expect ~30-50% success rate
# Updated manually or via scraping. Only use as fallback.
FREE_PROXIES = [
    # Format: "host:port" — HTTP proxies
    # These are placeholders — real free proxies need to be scraped fresh
    # from sites like free-proxy-list.net, proxyscrape.com, etc.
]

# CAPTCHA detection patterns
CAPTCHA_INDICATORS = [
    "captcha",
    "robot",
    "are you a human",
    "access denied",
    "blocked",
    "unusual traffic",
    "verify you are human",
    "challenge-platform",
    "cf-challenge",  # Cloudflare
    "px-captcha",    # PerimeterX
    "distil",        # Distil Networks
]


class ProxyManager:
    """Manages proxy rotation for web scraping."""

    def __init__(self, provider=None, api_key=None):
        self.provider = (provider or os.getenv("PROXY_PROVIDER", "none")).lower()
        self.api_key = api_key or os.getenv("PROXY_API_KEY", "")
        self._proxies = []
        self._current_idx = 0
        self._failed = set()
        self._success_count = 0
        self._fail_count = 0
        self._init_proxies()

    def _init_proxies(self):
        """Initialize proxy list based on provider."""
        if self.provider == "none":
            self._proxies = []
        elif self.provider == "smartproxy":
            self._init_smartproxy()
        elif self.provider == "brightdata":
            self._init_brightdata()
        elif self.provider == "free":
            self._init_free_proxies()
        else:
            print(f"[proxy] Unknown provider '{self.provider}', using direct connection",
                  file=sys.stderr)
            self._proxies = []

    def _init_smartproxy(self):
        """SmartProxy residential — rotates automatically per request via gateway."""
        if not self.api_key:
            print("[proxy] PROXY_API_KEY not set for SmartProxy, falling back to direct",
                  file=sys.stderr)
            return
        # SmartProxy uses a gateway that rotates IPs per request
        # Format: user:pass@gate.smartproxy.com:port
        self._proxies = [{
            "server": "http://gate.smartproxy.com:10000",
            "username": self.api_key.split(":")[0] if ":" in self.api_key else self.api_key,
            "password": self.api_key.split(":")[1] if ":" in self.api_key else "",
        }]
        print(f"[proxy] SmartProxy gateway configured", file=sys.stderr)

    def _init_brightdata(self):
        """BrightData residential — rotates via zone gateway."""
        if not self.api_key:
            print("[proxy] PROXY_API_KEY not set for BrightData, falling back to direct",
                  file=sys.stderr)
            return
        self._proxies = [{
            "server": "http://brd.superproxy.io:22225",
            "username": self.api_key.split(":")[0] if ":" in self.api_key else self.api_key,
            "password": self.api_key.split(":")[1] if ":" in self.api_key else "",
        }]
        print(f"[proxy] BrightData gateway configured", file=sys.stderr)

    def _init_free_proxies(self):
        """Free proxy list — scrape fresh or use cached list."""
        cache_file = Path(__file__).parent.parent / ".tmp" / "sourcing" / "free_proxies.txt"
        if cache_file.exists():
            age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
            if age_hours < 6:  # Use cache if < 6 hours old
                lines = cache_file.read_text().strip().split("\n")
                self._proxies = [{"server": f"http://{line.strip()}"} for line in lines if line.strip()]
                print(f"[proxy] Loaded {len(self._proxies)} cached free proxies", file=sys.stderr)
                return

        # Try to scrape fresh proxies
        try:
            self._scrape_free_proxies(cache_file)
        except Exception as e:
            print(f"[proxy] Failed to scrape free proxies: {e}", file=sys.stderr)
            if FREE_PROXIES:
                self._proxies = [{"server": f"http://{p}"} for p in FREE_PROXIES]

    def _scrape_free_proxies(self, cache_file):
        """Scrape free proxies from public lists."""
        import urllib.request
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=us&ssl=all&anonymity=all"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode()
            proxies = [line.strip() for line in text.strip().split("\n") if line.strip()]
            if proxies:
                random.shuffle(proxies)
                proxies = proxies[:50]  # Keep top 50
                self._proxies = [{"server": f"http://{p}"} for p in proxies]
                # Cache
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text("\n".join(proxies))
                print(f"[proxy] Scraped {len(proxies)} free proxies", file=sys.stderr)
        except Exception as e:
            print(f"[proxy] Proxy scrape failed: {e}", file=sys.stderr)

    def next(self):
        """Get next proxy config for Playwright. Returns dict or None (direct)."""
        if not self._proxies:
            return None

        # For gateway proxies (smartproxy/brightdata), always return the same
        # because the gateway rotates IPs per request
        if self.provider in ("smartproxy", "brightdata"):
            return self._proxies[0]

        # For free proxies, rotate through the list, skipping failed ones
        attempts = 0
        while attempts < len(self._proxies):
            proxy = self._proxies[self._current_idx % len(self._proxies)]
            self._current_idx += 1
            server = proxy.get("server", "")
            if server not in self._failed:
                return proxy
            attempts += 1

        # All failed — reset and try again
        self._failed.clear()
        return self._proxies[0] if self._proxies else None

    def mark_failed(self, proxy):
        """Mark a proxy as blocked/failed."""
        if proxy and proxy.get("server"):
            self._failed.add(proxy["server"])
            self._fail_count += 1

    def mark_success(self, proxy):
        """Record successful proxy use."""
        self._success_count += 1

    @property
    def is_configured(self):
        """True if any proxies are available."""
        return len(self._proxies) > 0

    def stats(self):
        """Return proxy usage stats."""
        return {
            "provider": self.provider,
            "total_proxies": len(self._proxies),
            "failed_proxies": len(self._failed),
            "success_count": self._success_count,
            "fail_count": self._fail_count,
        }


def detect_captcha(page_content):
    """Check if page content indicates a CAPTCHA or bot block.

    Args:
        page_content: HTML string or page text content.

    Returns:
        True if CAPTCHA/block detected.
    """
    if not page_content:
        return False
    content_lower = page_content.lower()
    return any(indicator in content_lower for indicator in CAPTCHA_INDICATORS)


def get_proxy_manager():
    """Convenience function — creates a ProxyManager from .env config."""
    return ProxyManager()
