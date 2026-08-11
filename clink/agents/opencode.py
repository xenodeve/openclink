"""OpenCode-specific CLI agent hooks."""

from __future__ import annotations

from .base import BaseCLIAgent


class OpenCodeAgent(BaseCLIAgent):
    """OpenCode CLI agent.

    Behaviourally identical to the base today — `opencode run` takes the model as
    `-m provider/model`, which `BaseCLIAgent` already emits, and its reasoning
    effort is a separate `--variant` flag that no PAL call sets yet. The class
    exists as the declaration site for opencode's own usage vocabulary, which the
    fallback cannot express.
    """

    # opencode's parser publishes the account under `tokens`, not `usage`.
    USAGE_METADATA_KEY = "tokens"

    # Recorded from `part.tokens` on a real `step_finish` (2026-08-11, v1.18.15).
    # `total` is deliberately unmapped: it duplicates the others and is numerically
    # plausible in `input_tokens`, so landing it there makes the account wrong
    # rather than incomplete.
    #
    # `cache.write` and `cache.read` are unmapped for two different reasons —
    # cache-creation has no field on the normalised account at all (#56), and
    # cache-read has one but sits a level down, which the flat field map cannot
    # reach. Both are pinned by test_opencode_cache_tokens_reach_no_field_of_the_account.
    USAGE_FIELD_MAP = {
        "input": "input_tokens",
        "output": "output_tokens",
        "reasoning": "reasoning_output_tokens",
    }
