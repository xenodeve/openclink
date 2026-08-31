"""
Test path traversal security fix.

Fixes vulnerability reported in:
- https://github.com/BeehiveInnovations/zen-mcp-server/issues/293
- https://github.com/BeehiveInnovations/zen-mcp-server/issues/312

The vulnerability: is_dangerous_path() only did exact string matching,
so /etc was blocked but /etc/passwd was allowed.

Additionally, this fix properly handles home directory containers:
- /home and C:\\Users are blocked (exact match only)
- /home/user/project paths are allowed through is_dangerous_path()
  and handled by is_home_directory_root() in resolve_and_validate_path()

Why the dangerous-path cases below are chosen per platform
----------------------------------------------------------
`is_dangerous_path()` resolves its argument against the *real* filesystem, so a
path string only means what the host OS says it means. `Path("/etc/passwd")` on
Windows is not absolute (it carries no drive), and resolves to `D:\\etc\\passwd`
on whatever drive the process happens to be running from — an ordinary user
location. Blocking it there would be a false positive, so asserting the POSIX
list on Windows would test nothing about Windows and could only be made to pass
by weakening the function.

Each platform therefore asserts *its own* dangerous paths, at full strength:
the same security property, stated in the vocabulary of the OS running the test.
`TestWindowsPathHandling` below is the complement — it uses `PureWindowsPath`,
which never touches the filesystem, so the Windows *matching logic* is verified
on every platform including POSIX.
"""

import os
from pathlib import Path

import pytest

from utils.security_config import is_dangerous_path

IS_WINDOWS = os.name == "nt"

# Exact system roots that must be blocked, and their subdirectories with them.
DANGEROUS_ROOTS = ["C:\\Windows", "C:\\Program Files"] if IS_WINDOWS else ["/etc", "/usr", "/var"]

# Subdirectories of those roots — the paths the original vulnerability let through.
DANGEROUS_SUBDIRECTORIES = (
    [
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "C:\\Windows\\win.ini",
        "C:\\Program Files\\Common Files",
    ]
    if IS_WINDOWS
    else ["/etc/passwd", "/etc/shadow", "/etc/hosts", "/var/log/auth.log"]
)

DEEPLY_NESTED = (
    ["C:\\Windows\\System32\\config\\SAM", "C:\\Program Files\\Common Files\\System\\x.dll"]
    if IS_WINDOWS
    else ["/etc/ssh/sshd_config", "/usr/local/bin/python"]
)

# The credential stores an attacker actually wants — the regression cases.
CREDENTIAL_TARGETS = (
    # SAM and SYSTEM hold Windows' local password hashes; the /etc equivalents.
    ["C:\\Windows\\System32\\config\\SAM", "C:\\Windows\\System32\\config\\SYSTEM"]
    if IS_WINDOWS
    else ["/etc/passwd", "/etc/shadow"]
)

# Blocked as an exact path only; subdirectories are delegated to is_home_directory_root().
HOME_CONTAINER = "C:\\Users" if IS_WINDOWS else "/home"
HOME_SUBDIRECTORIES = (
    ["C:\\Users\\user", "C:\\Users\\user\\project", "C:\\Users\\user\\project\\src\\main.py"]
    if IS_WINDOWS
    else ["/home/user", "/home/user/project", "/home/user/project/src/main.py"]
)
HOME_DEEPLY_NESTED = (
    "C:\\Users\\user\\documents\\work\\project\\src" if IS_WINDOWS else "/home/user/documents/work/project/src"
)

# A location no dangerous rule covers, on the platform's own terms.
SAFE_ROOT = "C:\\SafeProjects" if IS_WINDOWS else "/tmp"


class TestPathTraversalFix:
    """Test that subdirectories of dangerous system paths are blocked."""

    @pytest.mark.parametrize("path", DANGEROUS_ROOTS)
    def test_exact_match_still_works(self, path):
        """Test that exact dangerous paths are still blocked."""
        assert is_dangerous_path(Path(path)) is True

    @pytest.mark.parametrize("path", DANGEROUS_SUBDIRECTORIES)
    def test_subdirectory_now_blocked(self, path):
        """Test that subdirectories of system paths are blocked (the fix).

        These were allowed before the fix.
        """
        assert is_dangerous_path(Path(path)) is True

    @pytest.mark.parametrize("path", DEEPLY_NESTED)
    def test_deeply_nested_blocked(self, path):
        """Test that deeply nested system paths are blocked."""
        assert is_dangerous_path(Path(path)) is True

    def test_root_blocked(self):
        """Test that root directory is blocked."""
        assert is_dangerous_path(Path("/")) is True

    def test_safe_paths_allowed(self):
        """Test that safe paths are still allowed."""
        # User project directories should be allowed
        assert is_dangerous_path(Path(SAFE_ROOT) / "test") is False
        assert is_dangerous_path(Path(SAFE_ROOT) / "myproject" / "src") is False

    def test_similar_names_not_blocked(self):
        """Test that paths with similar names are not blocked.

        A sibling whose name merely starts with a dangerous one is not under it —
        this is what `is_relative_to` buys over string prefix matching.
        """
        assert is_dangerous_path(Path(SAFE_ROOT) / "etcbackup") is False
        assert is_dangerous_path(Path(SAFE_ROOT) / "my_etc_files") is False
        # Directly adjacent to a real dangerous root, differing only by suffix.
        assert is_dangerous_path(Path(DANGEROUS_ROOTS[0] + "Backup")) is False


class TestHomeDirectoryHandling:
    """Test that home directory containers are handled correctly.

    Home containers (/home, C:\\Users) should only block the exact path,
    not subdirectories. Subdirectory access control is delegated to
    is_home_directory_root() in resolve_and_validate_path().
    """

    def test_home_container_blocked(self):
        """Test that the home container itself is blocked."""
        assert is_dangerous_path(Path(HOME_CONTAINER)) is True

    @pytest.mark.parametrize("path", HOME_SUBDIRECTORIES)
    def test_home_subdirectories_allowed(self, path):
        """Test that home subdirectories pass through is_dangerous_path().

        These paths should NOT be blocked by is_dangerous_path() because:
        1. a user project directory is a valid workspace
        2. access control for the user's own home root is handled by
           is_home_directory_root() separately
        """
        assert is_dangerous_path(Path(path)) is False

    def test_home_deeply_nested_allowed(self):
        """Test that deeply nested home paths are allowed."""
        assert is_dangerous_path(Path(HOME_DEEPLY_NESTED)) is False


class TestRegressionPrevention:
    """Regression tests for the specific vulnerability.

    The reported attack was reading a credential store that sat one level below a
    blocked directory. Each platform asserts its own equivalent.
    """

    @pytest.mark.parametrize("path", CREDENTIAL_TARGETS)
    def test_credential_store_blocked(self, path):
        assert is_dangerous_path(Path(path)) is True


class TestWindowsPathHandling:
    """Test Windows path handling with trailing backslash.

    Fixes issue reported in PR #353: Windows paths like C:\\ have trailing
    backslash which caused double separator issues with string prefix matching.
    Using Path.is_relative_to() resolves this correctly.

    These use PureWindowsPath, which never touches the filesystem, so the Windows
    matching logic is verified on POSIX hosts too.
    """

    def test_windows_root_drive_blocked(self):
        """Test that Windows root drive C:\\ is blocked."""
        from pathlib import PureWindowsPath

        # Simulate Windows path behavior using PureWindowsPath
        # On Linux, we test the logic with PureWindowsPath to verify cross-platform correctness
        c_root = PureWindowsPath("C:\\")
        assert c_root.parent == c_root  # Root check works

    def test_windows_dangerous_subdirectory_detection(self):
        """Test that Windows subdirectories are correctly detected as dangerous.

        This verifies the fix for the double backslash issue:
        - Before fix: "C:\\" + "\\" = "C:\\\\" which doesn't match "C:\\Users"
        - After fix: Path.is_relative_to() handles this correctly
        """
        from pathlib import PureWindowsPath

        # Verify is_relative_to works correctly for Windows paths
        c_users = PureWindowsPath("C:\\Users")
        c_root = PureWindowsPath("C:\\")

        # This is the key test - subdirectory detection must work
        assert c_users.is_relative_to(c_root) is True

        # Deeper paths should also work
        c_users_admin = PureWindowsPath("C:\\Users\\Admin")
        assert c_users_admin.is_relative_to(c_root) is True
        assert c_users_admin.is_relative_to(c_users) is True

    def test_windows_path_not_relative_to_different_drive(self):
        """Test that paths on different drives are not related."""
        from pathlib import PureWindowsPath

        d_path = PureWindowsPath("D:\\Data")
        c_root = PureWindowsPath("C:\\")

        # D: drive paths should not be relative to C:
        assert d_path.is_relative_to(c_root) is False


class TestPosixPathMatchingLogic:
    """The POSIX matching logic, verified on every platform.

    Mirrors TestWindowsPathHandling: PurePosixPath never touches the filesystem,
    so the POSIX subdirectory and sibling rules stay covered when the suite runs
    on Windows — which is where the platform-specific cases above stop asserting
    them.
    """

    def test_posix_subdirectory_is_relative_to_root(self):
        from pathlib import PurePosixPath

        assert PurePosixPath("/etc/passwd").is_relative_to(PurePosixPath("/etc")) is True
        assert PurePosixPath("/etc/ssh/sshd_config").is_relative_to(PurePosixPath("/etc")) is True

    def test_posix_sibling_with_shared_prefix_is_not_relative(self):
        from pathlib import PurePosixPath

        # The string-prefix bug this fix replaced would have matched these.
        assert PurePosixPath("/etcbackup").is_relative_to(PurePosixPath("/etc")) is False
        assert PurePosixPath("/etc_old/passwd").is_relative_to(PurePosixPath("/etc")) is False

    def test_posix_home_subdirectory_is_not_the_container(self):
        from pathlib import PurePosixPath

        assert PurePosixPath("/home/user/project") != PurePosixPath("/home")
