"""Cross-platform ownership of a subagent's entire process tree.

`asyncio.create_subprocess_exec` on its own only ever gives the caller a
handle to the direct child. Anything that child spawns -- shells, language
servers, helper processes a coding CLI starts -- belongs to nothing the
server tracks, and `process.kill()` only ever signals that one PID.

This module spawns each subagent into its own process group (POSIX, via
`start_new_session=True`) or Job Object (Windows) so that termination can
target the whole tree, and so that termination can be *confirmed* by the OS
rather than merely requested (issue #144 / PRD #20 story 8: cancellation
must be acknowledged only once the OS confirms the tree is gone).

Windows note: a Job Object's automatic "descendants join the same job"
behaviour is not reliable once the caller is itself already nested inside an
ambient job that silently breaks children away from it (common under
sandboxed dev tools, CI runners, container hosts and terminal wrappers) --
verified empirically while building this fix. So the Job Object is created
as a best-effort safety net (and to satisfy `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
cleanup on abnormal exit), but the *confirmed* kill walks the live process
tree by PID/PPID via `CreateToolhelp32Snapshot`, the same mechanism
`taskkill /T` relies on, which is independent of job-nesting quirks.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import signal
import subprocess
import sys
import time

logger = logging.getLogger("clink.process_tree")

IS_WINDOWS = sys.platform == "win32"

_DEFAULT_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.05

# Imported eagerly (not lazily inside the helpers below) so that assigning a
# freshly spawned child to a Job Object is not slowed down by first-time
# module/DLL loading -- pywin32 ships as a transitive dependency of `mcp` on
# Windows, but is treated as optional here in case that ever changes.
if IS_WINDOWS:  # pragma: sys-platform
    try:
        import pywintypes
        import win32api
        import win32con
        import win32job
    except ImportError:  # pragma: no cover - defensive
        pywintypes = win32api = win32con = win32job = None
else:
    pywintypes = win32api = win32con = win32job = None  # pragma: sys-platform


def spawn_kwargs() -> dict:
    """Extra kwargs for subprocess creation so the child owns its own tree.

    POSIX: `start_new_session=True` makes the child a new session/process
    group leader, so its pgid equals its pid.

    Windows: `CREATE_NEW_PROCESS_GROUP` isolates the child from the parent's
    console process group (e.g. so Ctrl+Break can target it independently).
    """
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def pid_alive(pid: int) -> bool:
    """True if `pid` refers to a currently-running process."""
    if IS_WINDOWS:
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        still_active = 259
        return exit_code.value == still_active

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_process_snapshot() -> list[tuple[int, int]]:
    """Return (pid, ppid) for every currently running Windows process."""
    from ctypes import wintypes

    th32cs_snapprocess = 0x00000002
    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    invalid_handle_value = ctypes.c_void_p(-1).value
    if snapshot in (0, invalid_handle_value, None):
        return []

    entries: list[tuple[int, int]] = []
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return []
        while True:
            entries.append((entry.th32ProcessID, entry.th32ParentProcessID))
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    return entries


def _expand_with_descendants(known_pids: set[int]) -> None:
    """Grow `known_pids` in place with every live descendant of any pid
    already in it, using one fresh snapshot.

    Growing a running set (rather than re-walking from the root each time)
    matters once termination is underway: an intermediate process (e.g. a
    launcher stub that re-execs into the real interpreter) can die before a
    deeper descendant does, at which point a fresh walk *from the root*
    would no longer find that branch at all even though it is still alive.
    """
    children_by_ppid: dict[int, list[int]] = {}
    for pid, ppid in _windows_process_snapshot():
        children_by_ppid.setdefault(ppid, []).append(pid)

    frontier = list(known_pids)
    while frontier:
        current = frontier.pop()
        for child_pid in children_by_ppid.get(current, []):
            if child_pid not in known_pids:
                known_pids.add(child_pid)
                frontier.append(child_pid)


def _windows_terminate_pid(pid: int) -> None:
    process_terminate = 0x0001
    handle = ctypes.windll.kernel32.OpenProcess(process_terminate, False, pid)
    if not handle:
        return
    try:
        ctypes.windll.kernel32.TerminateProcess(handle, 1)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class ProcessGroup:
    """Owns the process group / Job Object a spawned process and its
    descendants belong to, and can confirm the whole tree is gone."""

    def __init__(self, pid: int):
        self.pid = pid
        self._job_handle = None
        if IS_WINDOWS:
            self._job_handle = self._create_and_assign_job(pid)

    @staticmethod
    def _create_and_assign_job(pid: int):
        if win32job is None:
            return None

        job = win32job.CreateJobObject(None, "")
        extended_info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        extended_info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, extended_info)

        try:
            process_handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, pid)
        except pywintypes.error as exc:
            logger.warning("clink: could not open subagent pid %s to assign it to a Job Object: %s", pid, exc)
            return None

        try:
            win32job.AssignProcessToJobObject(job, process_handle)
        except pywintypes.error as exc:
            # Expected when `pid` is already nested in an ambient job that
            # disallows further nesting; the toolhelp-based tree walk below
            # is the mechanism this class actually relies on for confirmed
            # termination, so this is not fatal.
            logger.debug("clink: could not assign subagent pid %s to a Job Object: %s", pid, exc)
            win32api.CloseHandle(process_handle)
            return None

        win32api.CloseHandle(process_handle)
        return job

    def terminate_blocking(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> bool:
        """Kill the whole tree and block until the OS confirms it is gone.

        Returns True once confirmed, False if the tree could not be
        confirmed dead within `timeout` (still attempted; logged either way).
        """
        if IS_WINDOWS:
            return self._terminate_windows(timeout)
        return self._terminate_posix(timeout)

    async def terminate(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> bool:
        return await asyncio.to_thread(self.terminate_blocking, timeout)

    def _terminate_posix(self, timeout: float) -> bool:
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            return True

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.killpg(self.pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(_POLL_INTERVAL_SECONDS)

        logger.warning("clink: process group %s did not confirm exit within %.1fs", self.pid, timeout)
        return False

    def _terminate_windows(self, timeout: float) -> bool:
        known_pids: set[int] = {self.pid}
        deadline = time.monotonic() + timeout

        while True:
            # Discover descendants *before* killing anything this round, so a
            # branch whose intermediate parent is about to die is not lost.
            _expand_with_descendants(known_pids)
            alive = [pid for pid in known_pids if pid_alive(pid)]
            if not alive:
                break
            for pid in alive:
                _windows_terminate_pid(pid)
            if time.monotonic() >= deadline:
                break
            time.sleep(_POLL_INTERVAL_SECONDS)

        # Best-effort defense in depth: closes out anything still assigned to
        # the Job Object (e.g. if auto-inheritance did catch a branch our
        # explicit walk raced with).
        if self._job_handle is not None and win32job is not None:
            try:
                win32job.TerminateJobObject(self._job_handle, 1)
            except Exception as exc:  # pragma: no cover - defensive, job may already be gone
                logger.debug("clink: TerminateJobObject failed for pid %s: %s", self.pid, exc)

        still_alive = [pid for pid in known_pids if pid_alive(pid)]
        if still_alive:
            logger.warning(
                "clink: process tree rooted at pid %s did not confirm exit within %.1fs (still alive: %s)",
                self.pid,
                timeout,
                still_alive,
            )
            return False
        return True

    def close(self) -> None:
        """Release OS resources. On Windows, closing the last handle to a Job
        Object created with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE also kills any
        processes still assigned to it -- a safety net against stragglers on
        every exit path, including a clean success."""
        if IS_WINDOWS and self._job_handle is not None and win32api is not None:
            try:
                win32api.CloseHandle(self._job_handle)
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            self._job_handle = None
