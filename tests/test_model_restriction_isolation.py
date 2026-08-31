"""A test that leaks the model-restriction singleton must not poison the next one.

`ModelRestrictionService` snapshots `*_ALLOWED_MODELS` once, at construction, into
the module-level singleton `utils.model_restrictions._restriction_service`. The
autouse `clear_model_restriction_env` fixture clears those env vars, which does
nothing to a service that has already parsed them — so a test that constructs the
service under a restrictive env leaves every later test restricted.

That is not hypothetical. `test_chat_codegen_integration` sets
`GOOGLE_ALLOWED_MODELS=gemini-2.5-pro` and resets the singleton *after* awaiting
the tool, with no `try`/`finally`; when the await raised, the reset was skipped and
ten later tests died with "Model 'gemini-2.5-flash' is not available". They looked
like portability failures and were not.

The two tests below run in definition order and pin the isolation itself, so the
hazard cannot come back silently the next time some test's cleanup is skipped.
"""

from utils import model_restrictions


def test_a_leaks_a_restriction_service():
    """Stand in for any test whose cleanup is skipped by a raise."""
    model_restrictions._restriction_service = model_restrictions.ModelRestrictionService()
    assert model_restrictions._restriction_service is not None


def test_b_starts_from_a_clean_restriction_service():
    """The next test must not inherit it."""
    assert model_restrictions._restriction_service is None
