"""
Pytest configuration for PAL MCP Server tests
"""

import asyncio
import functools
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# On macOS, the default pytest temp dir is typically under /var (e.g. /private/var/folders/...).
# If /var is considered a dangerous system path, tests must use a safe temp root (like /tmp).
if sys.platform == "darwin":
    os.environ["TMPDIR"] = "/tmp"
    # tempfile caches the temp dir after first lookup; clear it so pytest fixtures pick up TMPDIR.
    tempfile.tempdir = None

# Ensure the parent directory is in the Python path for imports
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import utils.env as env_config  # noqa: E402

# Ensure tests operate with runtime environment rather than .env overrides during imports
env_config.reload_env({"PAL_MCP_FORCE_ENV_OVERRIDE": "false"})

# Set default model to a specific value for tests to avoid auto mode
# This prevents all tests from failing due to missing model parameter
os.environ["DEFAULT_MODEL"] = "gemini-2.5-flash"

# Force reload of config module to pick up the env var
import config  # noqa: E402

importlib.reload(config)

# Note: This creates a test sandbox environment
# Tests create their own temporary directories as needed

# Configure asyncio for Windows compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _force_utf8_replay_cassettes() -> None:
    """Make the vendored google-genai replay client read cassettes as UTF-8.

    `_replay_api_client.py` calls `open(path, 'r')` with no encoding, so Python
    falls back to the locale default — cp1252 on a stock Windows box. The gemini
    cassettes contain non-ASCII characters ('│', '•', '—') that then decode into
    mojibake, and the replay client compares the request body for exact equality,
    so a single mangled character fails the test. The OpenAI cassettes are pure
    ASCII, which is why only the gemini ones break.

    This is upstream's bug (a missing `encoding='utf-8'`), not a stale cassette:
    read as UTF-8 the recorded body matches the generated one exactly.
    """
    try:
        import google.genai._replay_api_client as replay_client
    except ImportError:  # SDK absent — nothing to patch
        return

    builtin_open = open

    def utf8_open(file, mode="r", *args, **kwargs):
        if "b" not in mode:
            kwargs.setdefault("encoding", "utf-8")
        return builtin_open(file, mode, *args, **kwargs)

    # Patch the module global so both the read and the record-mode write use UTF-8.
    replay_client.open = utf8_open


_force_utf8_replay_cassettes()


_GIT_BASH_CANDIDATES = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)


@functools.lru_cache(maxsize=1)
def find_bash() -> str | None:
    """Absolute path to a bash that actually runs, or None.

    Passing the bare name "bash" to subprocess is unusable on Windows:
    CreateProcess searches C:\\Windows\\system32 before PATH, and the bash.exe
    there is the WSL launcher stub, which fails with a relay error on a machine
    with no WSL distro. `shutil.which("bash")` does NOT agree with that lookup —
    it reports the Git-for-Windows bash — so the resolver has to validate by
    executing rather than trusting `which`.

    Git-for-Windows is preferred over whatever `which` returns because a working
    WSL bash would pass the probe below and still choke on the Windows-style
    paths (`source "D:\\..."`) these tests interpolate.
    """
    candidates = []
    if sys.platform == "win32":
        candidates += [p for p in _GIT_BASH_CANDIDATES if Path(p).is_file()]
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    for exe in candidates:
        try:
            proc = subprocess.run([exe, "-c", "echo ok"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0 and proc.stdout.strip() == "ok":
            return exe
    return None


# Register providers for all tests
from providers.gemini import GeminiModelProvider  # noqa: E402
from providers.openai import OpenAIModelProvider  # noqa: E402
from providers.registry import ModelProviderRegistry  # noqa: E402
from providers.shared import ProviderType  # noqa: E402
from providers.xai import XAIModelProvider  # noqa: E402

# Register providers at test startup
ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)
ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)

# Register CUSTOM provider if CUSTOM_API_URL is available (for integration tests)
# But only if we're actually running integration tests, not unit tests
if os.getenv("CUSTOM_API_URL") and "test_prompt_regression.py" in os.getenv("PYTEST_CURRENT_TEST", ""):
    from providers.custom import CustomProvider  # noqa: E402

    def custom_provider_factory(api_key=None):
        """Factory function that creates CustomProvider with proper parameters."""
        base_url = os.getenv("CUSTOM_API_URL", "")
        return CustomProvider(api_key=api_key or "", base_url=base_url)

    ModelProviderRegistry.register_provider(ProviderType.CUSTOM, custom_provider_factory)


@pytest.fixture
def project_path(tmp_path):
    """
    Provides a temporary directory for tests.
    This ensures all file operations during tests are isolated.
    """
    # Create a subdirectory for this specific test
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir(parents=True, exist_ok=True)

    return test_dir


def _set_dummy_keys_if_missing():
    """Set dummy API keys only when they are completely absent."""
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"):
        if not os.environ.get(var):
            os.environ[var] = "dummy-key-for-tests"


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "asyncio: mark test as async")
    config.addinivalue_line("markers", "no_mock_provider: disable automatic provider mocking")
    # Assume we need dummy keys until we learn otherwise
    config._needs_dummy_keys = True


def pytest_collection_modifyitems(session, config, items):
    """Hook that runs after test collection to check for no_mock_provider markers."""
    # Always set dummy keys if real keys are missing
    # This ensures tests work in CI even with no_mock_provider marker
    _set_dummy_keys_if_missing()


@pytest.fixture(autouse=True)
def mock_provider_availability(request, monkeypatch):
    """
    Automatically mock provider availability for all tests to prevent
    effective auto mode from being triggered when DEFAULT_MODEL is unavailable.

    This fixture ensures that when tests run with dummy API keys,
    the tools don't require model selection unless explicitly testing auto mode.
    """
    # Skip this fixture for tests that need real providers
    if hasattr(request, "node"):
        marker = request.node.get_closest_marker("no_mock_provider")
        if marker:
            return

    # Ensure providers are registered (in case other tests cleared the registry)
    from providers.shared import ProviderType

    registry = ModelProviderRegistry()

    if ProviderType.GOOGLE not in registry._providers:
        ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
    if ProviderType.OPENAI not in registry._providers:
        ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)
    if ProviderType.XAI not in registry._providers:
        ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)

    # Ensure CUSTOM provider is registered if needed for integration tests
    if (
        os.getenv("CUSTOM_API_URL")
        and "test_prompt_regression.py" in os.getenv("PYTEST_CURRENT_TEST", "")
        and ProviderType.CUSTOM not in registry._providers
    ):
        from providers.custom import CustomProvider

        def custom_provider_factory(api_key=None):
            base_url = os.getenv("CUSTOM_API_URL", "")
            return CustomProvider(api_key=api_key or "", base_url=base_url)

        ModelProviderRegistry.register_provider(ProviderType.CUSTOM, custom_provider_factory)

    # Also mock is_effective_auto_mode for all BaseTool instances to return False
    # unless we're specifically testing auto mode behavior
    from tools.shared.base_tool import BaseTool

    def mock_is_effective_auto_mode(self):
        # If this is an auto mode test file or specific auto mode test, use the real logic
        test_file = request.node.fspath.basename if hasattr(request, "node") and hasattr(request.node, "fspath") else ""
        test_name = request.node.name if hasattr(request, "node") else ""

        # Allow auto mode for tests in auto mode files or with auto in the name
        if (
            "auto_mode" in test_file.lower()
            or "auto" in test_name.lower()
            or "intelligent_fallback" in test_file.lower()
            or "per_tool_model_defaults" in test_file.lower()
        ):
            # Call original method logic
            from config import DEFAULT_MODEL

            if DEFAULT_MODEL.lower() == "auto":
                return True
            provider = ModelProviderRegistry.get_provider_for_model(DEFAULT_MODEL)
            return provider is None
        # For all other tests, return False to disable auto mode
        return False

    monkeypatch.setattr(BaseTool, "is_effective_auto_mode", mock_is_effective_auto_mode)


@pytest.fixture(autouse=True)
def clear_model_restriction_env(monkeypatch):
    """Ensure per-test isolation from user-defined model restriction env vars."""

    restriction_vars = [
        "OPENAI_ALLOWED_MODELS",
        "GOOGLE_ALLOWED_MODELS",
        "XAI_ALLOWED_MODELS",
        "OPENROUTER_ALLOWED_MODELS",
        "DIAL_ALLOWED_MODELS",
    ]

    for var in restriction_vars:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def disable_force_env_override(monkeypatch):
    """Default tests to runtime environment visibility unless they explicitly opt in."""

    monkeypatch.setenv("PAL_MCP_FORCE_ENV_OVERRIDE", "false")
    env_config.reload_env({"PAL_MCP_FORCE_ENV_OVERRIDE": "false"})
    monkeypatch.setenv("DEFAULT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("MAX_CONVERSATION_TURNS", "50")

    import importlib
    import sys

    import config
    import utils.conversation_memory as conversation_memory

    importlib.reload(config)
    importlib.reload(conversation_memory)

    test_conversation_module = sys.modules.get("tests.test_conversation_memory")
    if test_conversation_module is not None:
        test_conversation_module.MAX_CONVERSATION_TURNS = conversation_memory.MAX_CONVERSATION_TURNS

    try:
        yield
    finally:
        env_config.reload_env()
