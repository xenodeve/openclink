from __future__ import annotations

import pytest

from clink.validation import validate_model_request


@pytest.mark.parametrize(
    ("client_name", "model", "effort", "catalog", "expected_substrings"),
    [
        pytest.param(
            "codex",
            "unlisted-model",
            "high",
            None,
            None,
            id="no-catalog-accepts-request",
        ),
        pytest.param(
            "gemini",
            "unlisted-model",
            "high",
            {},
            None,
            id="empty-catalog-accepts-request",
        ),
        pytest.param(
            "antigravity",
            None,
            "high",
            {"gpt-5.6-sol": ["low", "medium", "high"]},
            None,
            id="omitted-model-with-catalog-is-accepted",
        ),
        pytest.param(
            "codex",
            "unknown-model",
            None,
            {"gpt-5.6-sol": ["low", "medium", "high"], "composer-2.5": []},
            ("codex", "unknown-model", "gpt-5.6-sol", "composer-2.5"),
            id="unknown-model-refuses-with-available-models",
        ),
        pytest.param(
            "gemini",
            "gpt-5.6-sol",
            None,
            {"gpt-5.6-sol": ["low", "medium", "high"]},
            None,
            id="servable-model-without-effort-is-accepted",
        ),
        pytest.param(
            "antigravity",
            "composer-2.5",
            "high",
            {"composer-2.5": []},
            # Deliberately does NOT assert how "no tiers" is rendered. Pinning the
            # literal "[]" would forbid a clearer message like "serves no effort
            # tiers" — the refusal has to name the tuple, not phrase it one way.
            ("antigravity", "composer-2.5", "high"),
            id="model-with-no-tiers-refuses-effort",
        ),
        pytest.param(
            "codex",
            "gpt-5.6-sol",
            "max",
            {"gpt-5.6-sol": ["low", "medium", "high"]},
            ("codex", "gpt-5.6-sol", "max", "low", "medium", "high"),
            id="unsupported-effort-refuses-with-served-tiers",
        ),
        pytest.param(
            "gemini",
            "gpt-5.6-sol",
            "high",
            {"gpt-5.6-sol": ["low", "medium", "high"]},
            None,
            id="supported-effort-is-accepted",
        ),
    ],
)
def test_validate_model_request_rules(
    client_name: str,
    model: str | None,
    effort: str | None,
    catalog: dict[str, list[str]] | None,
    expected_substrings: tuple[str, ...] | None,
) -> None:
    refusal = validate_model_request(
        client_name=client_name,
        model=model,
        effort=effort,
        catalog=catalog,
    )

    if expected_substrings is None:
        assert refusal is None
    else:
        assert refusal is not None
        for substring in expected_substrings:
            assert substring in refusal
