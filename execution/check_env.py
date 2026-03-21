#!/usr/bin/env python3
"""
Script: check_env.py
Purpose: Validate all required environment variables exist before running the
         sourcing pipeline. Prevents silent failures from missing API keys.

Usage:
  python execution/check_env.py           # Check all keys
  python execution/check_env.py --fix     # Add missing placeholders to .env
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

ENV_FILE = Path(__file__).parent.parent / ".env"

# Required keys grouped by feature
REQUIRED_KEYS = {
    "Core (Keepa + Anthropic)": {
        "KEEPA_API_KEY": "Keepa API key (Pro tier recommended) — keepa.com",
        "ANTHROPIC_API_KEY": "Anthropic API key for Claude — console.anthropic.com",
    },
    "Retail Search (Walmart via SerpAPI)": {
        "SERPAPI_KEY": "SerpAPI key for Walmart/Google Shopping search — serpapi.com",
    },
    "Alerts (Telegram)": {
        "TELEGRAM_BOT_TOKEN": "Telegram bot token — talk to @BotFather on Telegram",
        "TELEGRAM_CHAT_ID": "Telegram chat ID — send /start to your bot, then check getUpdates",
    },
    "Export (Google Sheets)": {
        "GOOGLE_SHARE_EMAIL": "Email to share Google Sheets with (optional)",
    },
}

# Optional but useful
OPTIONAL_KEYS = {
    "Proxy (Anti-CAPTCHA)": {
        "PROXY_PROVIDER": "Proxy provider: smartproxy, brightdata, or free (default: free)",
        "PROXY_API_KEY": "API key for paid proxy provider",
    },
}


def check_env(verbose=True):
    """Check all required environment variables. Returns (ok_count, missing_list)."""
    ok = 0
    missing = []

    for group, keys in REQUIRED_KEYS.items():
        if verbose:
            print(f"\n  {group}")
        for key, desc in keys.items():
            val = os.getenv(key, "")
            if val:
                if verbose:
                    masked = val[:4] + "..." + val[-4:] if len(val) > 12 else "***"
                    print(f"    [OK]  {key} = {masked}")
                ok += 1
            else:
                if verbose:
                    print(f"    [!!]  {key} — MISSING ({desc})")
                missing.append((key, desc, group))

    return ok, missing


def add_missing_to_env(missing):
    """Append missing keys as placeholders to .env file."""
    if not missing:
        print("\n  All keys present — nothing to add.")
        return

    lines_to_add = []
    for key, desc, group in missing:
        lines_to_add.append(f"# {desc}")
        lines_to_add.append(f"{key}=")

    existing = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    if not existing.endswith("\n"):
        existing += "\n"

    with open(ENV_FILE, "a") as f:
        f.write("\n# ── Added by check_env.py ──\n")
        for line in lines_to_add:
            f.write(line + "\n")

    print(f"\n  Added {len(missing)} placeholder(s) to {ENV_FILE}")
    print("  Fill in the actual values, then re-run this script to verify.")


def main():
    parser = argparse.ArgumentParser(description="Validate sourcing pipeline environment variables")
    parser.add_argument("--fix", action="store_true",
                        help="Add missing keys as placeholders to .env")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Only print errors")
    args = parser.parse_args()

    print("\n  Sourcing Pipeline — Environment Check")
    print("  " + "=" * 40)

    ok, missing = check_env(verbose=not args.quiet)

    # Optional keys
    if not args.quiet:
        print(f"\n  Optional keys:")
        for group, keys in OPTIONAL_KEYS.items():
            print(f"\n  {group}")
            for key, desc in keys.items():
                val = os.getenv(key, "")
                status = "[OK]" if val else "[--]"
                print(f"    {status}  {key}")

    # Summary
    total = sum(len(v) for v in REQUIRED_KEYS.values())
    print(f"\n  {'=' * 40}")
    print(f"  Result: {ok}/{total} required keys present")

    if missing:
        print(f"  MISSING: {', '.join(k for k, _, _ in missing)}")
        if args.fix:
            add_missing_to_env(missing)
        else:
            print(f"\n  Run with --fix to add placeholders to .env")
        sys.exit(1)
    else:
        print(f"  All required keys present.")
        sys.exit(0)


if __name__ == "__main__":
    main()
