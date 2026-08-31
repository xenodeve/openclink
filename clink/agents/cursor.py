"""Cursor-specific CLI agent hooks."""

from __future__ import annotations

from .base import BaseCLIAgent


class CursorAgent(BaseCLIAgent):
    """Cursor CLI agent.

    Behaviourally identical to the base today. It exists as the declaration site
    for cursor's per-client vocabulary, which every other client already has a
    class for — without it, cursor could not say anything about itself that the
    fallback would not also say about a client OpenClink has never seen.
    """

    # `cursor-agent` reports no token usage in any output mode OpenClink runs.
    USAGE_UNAVAILABLE = True
