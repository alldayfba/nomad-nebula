"""Discord bot security — thin wrapper around nova_core.security.

All security logic lives in nova_core/security.py. This module re-exports
for backwards compatibility with existing discord_bot imports.
"""

from nova_core.security import (
    # Input security
    check_input,
    sanitize_input,
    wrap_user_input,
    # Output security
    filter_output,
    SAFE_FALLBACK,
    # Rate limiting
    RateLimiter,
    # Permission checks (Discord-specific)
    is_admin,
    is_support,
)

__all__ = [
    "check_input",
    "sanitize_input",
    "wrap_user_input",
    "filter_output",
    "SAFE_FALLBACK",
    "RateLimiter",
    "is_admin",
    "is_support",
]
