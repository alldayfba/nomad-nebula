"""
Shared utilities for MCP servers (auth, error handling, response formatting).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        # Manual .env loading
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def get_api_key(env_var: str) -> str:
    """Get API key from environment, exit with helpful error if missing."""
    key = os.environ.get(env_var)
    if not key:
        print(
            f"ERROR: {env_var} not set. Add it to {ENV_FILE}\n"
            f"  echo '{env_var}=your_key_here' >> {ENV_FILE}",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def format_response(text: str, model: str, usage: dict | None = None) -> dict:
    """Standardize response format across providers."""
    result = {
        "text": text,
        "model": model,
    }
    if usage:
        result["usage"] = usage
    return result


def truncate_text(text: str, max_chars: int = 50000) -> str:
    """Truncate text to stay within reasonable limits."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"
