"""Chat Context Tracker — reads sales team Discord messages and builds rolling context.

Nova Sales passively reads channel messages to understand what the team is
discussing. When someone uses /ask, recent chat context is available so Nova
can reference ongoing conversations.
"""

from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Dict, List


class ChatContextTracker:
    """Stores recent channel messages for context injection."""

    def __init__(self, max_messages: int = 50, max_age_seconds: int = 3600):
        self.max_messages = max_messages
        self.max_age = max_age_seconds
        # channel_id -> deque of (timestamp, author_name, content)
        self._channels: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def record_message(self, channel_id: str, channel_name: str,
                       author_name: str, content: str):
        """Record a message from a channel."""
        if not content or not content.strip():
            return
        with self._lock:
            key = channel_id
            if key not in self._channels:
                self._channels[key] = deque(maxlen=self.max_messages)
            self._channels[key].append((
                _time.time(),
                channel_name,
                author_name,
                content[:500],  # Truncate long messages
            ))

    def get_recent_context(self, limit: int = 20) -> str:
        """Get recent messages across all channels as a formatted context block."""
        with self._lock:
            self._prune_unlocked()
            all_msgs = []
            for msgs in self._channels.values():
                all_msgs.extend(msgs)

            # Sort by timestamp, take most recent
            all_msgs.sort(key=lambda m: m[0], reverse=True)
            recent = all_msgs[:limit]

            if not recent:
                return ""

            lines = [f"## Recent Team Chat ({len(recent)} messages)\n"]
            for ts, channel, author, content in reversed(recent):  # chronological
                ago = int(_time.time() - ts)
                if ago < 60:
                    time_str = f"{ago}s ago"
                elif ago < 3600:
                    time_str = f"{ago // 60}m ago"
                else:
                    time_str = f"{ago // 3600}h ago"
                lines.append(f"[#{channel}] **{author}** ({time_str}): {content}")

            return "\n".join(lines)

    def get_channel_context(self, channel_id: str, limit: int = 10) -> str:
        """Get recent messages from a specific channel."""
        with self._lock:
            self._prune_unlocked()
            msgs = list(self._channels.get(channel_id, []))
            if not msgs:
                return ""

            recent = msgs[-limit:]
            lines = []
            for ts, channel, author, content in recent:
                lines.append(f"**{author}**: {content}")
            return "\n".join(lines)

    def _prune(self):
        """Remove messages older than max_age (thread-safe)."""
        with self._lock:
            self._prune_unlocked()

    def _prune_unlocked(self):
        """Remove messages older than max_age (caller must hold lock)."""
        cutoff = _time.time() - self.max_age
        for key in list(self._channels.keys()):
            q = self._channels[key]
            while q and q[0][0] < cutoff:
                q.popleft()
            if not q:
                del self._channels[key]
