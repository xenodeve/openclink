"""Antigravity (agy) CLI agent — driven through a Windows pseudo-console (ConPTY).

Google retired the Gemini CLI (June 2026) in favour of the Antigravity CLI, a Go binary
invoked as `agy`. It only emits output to a real terminal: under a plain piped subprocess
(how every MCP server, including PAL, normally spawns a CLI) it exits 0 with EMPTY stdout.
So this agent drives agy through a Windows ConPTY via `pywinpty` — agy sees a TTY, prints
its plain-text reply, and we capture it; the `antigravity_text` parser strips the ANSI
escape codes the terminal introduces. The prompt is passed as a positional argument
(`agy --print "<prompt>"`); stdin is unused. Verified working 2026-06-28.

base.py is intentionally untouched (its asyncio-pipe path serves claude/codex/gemini); the
PTY mechanism lives entirely here so there is no regression risk to the other CLIs.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Sequence

from clink.agents.process_tree import ProcessGroup
from clink.models import ResolvedCLIRole

from .base import AgentOutput, BaseCLIAgent, CLIAgentError


class AntigravityAgent(BaseCLIAgent):
    """Run `agy` inside a ConPTY and capture its plain-text output."""

    async def run(
        self,
        *,
        role: ResolvedCLIRole,
        prompt: str,
        system_prompt: str | None = None,
        files: Sequence[str],
        images: Sequence[str],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AgentOutput:
        _ = (files, images, system_prompt)  # already embedded into the prompt by the tool
        command = self._build_command(
            role=role,
            system_prompt=system_prompt,
            model=model,
            reasoning_effort=reasoning_effort,
        )

        resolved = shutil.which(command[0])
        if resolved is None:
            raise CLIAgentError(
                f"Executable '{command[0]}' not found in PATH for CLI '{self.client.name}'. "
                f"Ensure the Antigravity CLI (agy) is installed and accessible."
            )
        command[0] = resolved

        full_command = [*command, prompt]  # agy reads the prompt as a positional argument
        env = self._build_environment()
        cwd = str(self.client.working_dir) if self.client.working_dir else None

        start_time = time.monotonic()
        # pywinpty is blocking; run it off the event loop.
        returncode, raw_output = await asyncio.to_thread(
            self._run_in_pty, full_command, env, cwd, self.client.timeout_seconds
        )
        duration = time.monotonic() - start_time

        try:
            parsed = self._parser.parse(raw_output, "")
        except Exception as exc:
            raise CLIAgentError(
                f"Failed to parse output from CLI '{self.client.name}': {exc}",
                returncode=returncode,
                stdout=raw_output,
            ) from exc

        return AgentOutput(
            parsed=parsed,
            sanitized_command=list(command),  # logged without the prompt payload
            returncode=returncode,
            stdout=raw_output,
            stderr="",
            duration_seconds=duration,
            parser_name=self._parser.name,
        )

    def _run_in_pty(self, command: list[str], env: dict[str, str], cwd: str | None, timeout: int) -> tuple[int, str]:
        """Spawn the CLI in a ConPTY and read until it exits. Blocking — call via to_thread."""
        try:
            import winpty  # lazy import: PAL still starts (and other CLIs work) if pywinpty is absent
        except ImportError as exc:  # pragma: no cover
            raise CLIAgentError(
                f"CLI '{self.client.name}' requires the 'pywinpty' package — add it to PAL's dependencies."
            ) from exc

        proc = winpty.PtyProcess.spawn(command, cwd=cwd, env=env, dimensions=(50, 200))
        # Join the same ownership model as the pipe runner (base.py) -- a
        # descendant `agy` spawns must not survive a timeout either (#144).
        group = ProcessGroup(proc.pid)
        try:
            chunks: list[str] = []
            start = time.monotonic()
            timed_out = False
            while True:
                if time.monotonic() - start > timeout:
                    timed_out = True
                    break
                try:
                    data = proc.read()
                except EOFError:
                    break
                if data:
                    chunks.append(data)
                elif not proc.isalive():
                    break
                else:
                    time.sleep(0.05)

            exit_status = getattr(proc, "exitstatus", None)

            if timed_out:
                # Confirmed by the OS before we proceed -- do not return early.
                group.terminate_blocking()
                try:
                    proc.close(force=True)
                except Exception:  # pragma: no cover - best effort cleanup
                    pass
                raise CLIAgentError(f"CLI '{self.client.name}' timed out after {timeout} seconds", returncode=None)

            try:
                proc.close(force=True)
            except Exception:  # pragma: no cover - best effort cleanup
                pass

            return (exit_status or 0), "".join(chunks)
        finally:
            # Cleanup runs on every exit path -- success, failure, cancellation
            # and server shutdown (#20 story 32).
            group.close()
