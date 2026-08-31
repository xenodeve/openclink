"""OpenCode-specific CLI agent hooks."""

from __future__ import annotations

from .base import BaseCLIAgent


class OpenCodeAgent(BaseCLIAgent):
    """OpenCode CLI agent.

    `opencode run` takes the model as `-m/--model provider/model`, which the base
    already emits, and its reasoning effort as a SEPARATE `--variant` flag. The
    base drops the effort on purpose — claude and gemini bake the tier into the
    model name — so inheriting that dropped it here too, silently (#125).
    """

    # Declared so `_resolve_model_effort` can read the effort back off the command.
    # Writing the flag without declaring it here reports `resolved_effort: None`
    # while the CLI honours it — the silent hole #27 closed for codex and #43 for
    # antigravity. The two halves are one fix; shipping either alone is worse than
    # shipping neither, because it looks done.
    EFFORT_FLAGS = ("--variant",)

    # opencode's parser publishes the account under `tokens`, not `usage`.
    USAGE_METADATA_KEY = "tokens"

    # Recorded from `part.tokens` on a real `step_finish` (2026-08-11, v1.18.15).
    # `total` is deliberately unmapped: it duplicates the others and is numerically
    # plausible in `input_tokens`, so landing it there makes the account wrong
    # rather than incomplete.
    #
    # `cache.read` is a DOTTED key: the payload nests it under `cache`, and the
    # field map now walks a path (#127). It was the largest class on a real run
    # -- 144,256 against 102,535 input -- and it was being dropped because the
    # map could not reach it, not because it had nowhere to go.
    #
    # `cache.write` stays unmapped, and for the OTHER reason: cache-creation has
    # no field on the normalised account at all (#56). The two were bundled once
    # and that is why this one waited on a schema decision it never needed.
    USAGE_FIELD_MAP = {
        "input": "input_tokens",
        "output": "output_tokens",
        "reasoning": "reasoning_output_tokens",
        "cache.read": "cached_input_tokens",
    }

    def _model_args(self, model: str | None, reasoning_effort: str | None) -> list[str]:
        # `opencode run --help` (2026-08-16, v1.18.15):
        #   -m, --model    model to use in the format of provider/model
        #       --variant  model variant (provider-specific reasoning effort,
        #                  e.g., high, max, minimal)
        #
        # Independent knobs, unlike agy's — `--variant` is described as
        # provider-specific, not as conflicting with the model, so either may be
        # given alone.
        #
        # **Why there is no `refuse_unservable`, on the axis that actually
        # matters.** agy's exists because its two knobs CONFLICT per model and it
        # errors, so the refusal turns a guaranteed failure into a clear message.
        # opencode does the opposite: an unsupported variant is accepted and
        # silently ignored (measured 2026-08-16 — `--variant
        # definitely-not-a-real-variant` exited 0 and answered normally), so
        # there is no error to pre-empt. Refusing would mean validating against
        # the per-model `variants` list, which is only readable via a ~30s
        # `opencode models` call. That is a deliberate trade, not an oversight:
        # a typo here is silently ignored by the CLI, and OpenClink does not
        # catch it. Caching the enumerable list would close it (#125).
        args: list[str] = []
        if model:
            args += ["--model", model]
        if reasoning_effort:
            args += ["--variant", reasoning_effort]
        return args
