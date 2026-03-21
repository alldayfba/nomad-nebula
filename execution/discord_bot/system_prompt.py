"""Build the system prompt — delegates to nova_core.prompts.

Reads business context at startup, caches the result. Never includes
sensitive internal data (pricing, funnels, conversion rates, API keys).
"""

from nova_core.prompts import build_prompt
from nova_core.knowledge import get_relevant_faq

_cached_prompt = None


def build_system_prompt(force_rebuild=False):
    """Build and cache the system prompt from identity files.

    Returns the complete system prompt string.
    """
    global _cached_prompt

    if _cached_prompt and not force_rebuild:
        return _cached_prompt

    _cached_prompt = build_prompt("discord")
    return _cached_prompt
