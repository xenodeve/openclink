"""Keep model-catalog enforcement opt-in so clients can adopt it independently.

Pure by design — no subprocess, no network, no filesystem. Validation has to be
decidable without spawning anything, because its entire purpose is to refuse
*before* a process exists.
"""

from __future__ import annotations


def validate_model_request(
    *,
    client_name: str,
    model: str | None,
    effort: str | None,
    catalog: dict[str, list[str]] | None,
) -> str | None:
    """Refusal message for a tuple this client cannot serve, or None to allow it.

    The unit validated is the **tuple**, not the model name: the same model may be
    servable on one client and absent on another, and an effort tier exists on
    some models and not others.

    Three ways to be allowed through, and the third is the one that looks wrong:

    - No catalog, or an empty one — the client has not declared what it serves, so
      there is nothing to check it against. This is what lets the feature land one
      client at a time instead of requiring every catalog to be complete first.
    - An **omitted model**, even when a catalog exists. This is deliberate and is
      not an oversight to tidy up: refusing an omission is a separate change to a
      public contract, tracked on its own. Removing this branch here would make
      that change land silently, as a side effect of adding a catalog.
    - A tuple the catalog covers.

    An empty tier list means the model exists but takes no effort tiers at all,
    which is different from a model that is absent — so requesting any tier for it
    is refused, and the refusal says which of the two situations it is.
    """
    if not catalog or model is None:
        return None

    if model not in catalog:
        available_models = ", ".join(catalog)
        return f"{client_name} cannot serve model {model!r}; available models: {available_models}"

    if effort is None:
        return None

    tiers = catalog[model]
    if effort not in tiers:
        if not tiers:
            return f"{client_name} cannot serve effort {effort!r} for model {model!r}; serves no effort tiers"
        available_tiers = ", ".join(tiers)
        return (
            f"{client_name} cannot serve effort {effort!r} for model {model!r}; "
            f"serves effort tiers: {available_tiers}"
        )

    return None
