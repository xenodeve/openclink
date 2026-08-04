"""Run one clink delegation outside the MCP transport, so the caller never blocks.

Why this exists. Calling `mcp__pal__clink` from Claude Code blocks the session for
up to 120s before the host backgrounds the call. That is host behaviour, not PAL's
— PAL has exactly one blocking point and nothing to return earlier (pal-mcp-server
issue #15). This entry point sidesteps the transport entirely: the orchestrator
spawns it with its OWN background mechanism and is re-invoked when the process
exits, so the wait is zero rather than 120s.

It deliberately reuses `create_agent` and the registry, so the ConPTY runner, the
parsers, the model/effort mapping, the pre-spawn refusals and the token accounting
are the same code the MCP tool runs. Only the transport differs.

Simplification, stated rather than hidden: the MCP tool assembles its prompt with
`_prepare_prompt_for_role`, which also embeds conversation history and file
contents. This runner has no conversation and takes the prompt as given, prefixing
the role's system prompt exactly when the client does not receive one externally.
A delegation that needs files should name their absolute paths in the prompt and
let the CLI read them — which `clink-subagents` already recommends.

**Give it the same PATH the MCP server has, or it will use a different binary.**
The registry discovers each CLI from the process PATH at load time, so a shell with
a different PATH silently resolves a different install. Measured 2026-08-04: this
runner picked `~/bin/codex.EXE` 0.142.4 while the MCP server had
`AppData/Roaming/npm/codex.CMD` 0.144.4, and the older one answered a valid model
with HTTP 400 *"requires a newer version of Codex"* — a message that blames the
model, not the binary. Falsified by re-running the identical call with only the
PATH changed: 400 became a clean success. `resolved_executable` is reported on
every run so the divergence is visible instead of silent.

    python clink_bg.py --cli codex --model gpt-5.6-luna --effort high \
        --out result.json --prompt-file p.txt
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from clink import get_registry
from clink.agents import CLIAgentError, create_agent


def _payload(**kw) -> dict:
    return {k: v for k, v in kw.items() if v is not None}


async def _run(args) -> dict:
    registry = get_registry()
    client = registry.get_client(args.cli)
    role = client.roles[args.role]

    system_prompt = role.prompt_path.read_text(encoding="utf-8")
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    # The external-system-prompt clients take it as an argument; the rest need it
    # inlined. `output_to_file` is the marker the tool uses for that distinction.
    if system_prompt.strip() and not client.output_to_file:
        prompt = f"{system_prompt}\n\n{prompt}"

    agent = create_agent(client)
    # Always reported, because the one thing that differs between this path and the
    # MCP one is the PATH the process inherits, and therefore which binary the
    # registry discovered. Measured 2026-08-04: the MCP server resolved
    # `AppData/Roaming/npm/codex.CMD` (0.144.4) while this runner in a Bash shell
    # resolved `~/bin/codex.EXE` (0.142.4) — and the older one refuses a model the
    # newer serves, with a 400 that reads as "model unavailable" rather than
    # "wrong binary". Silent divergence is the failure this field forecloses.
    resolved_exe = shutil.which(client.executable[0]) or client.executable[0]
    started = time.time()
    try:
        result = await agent.run(
            role=role,
            prompt=prompt,
            system_prompt=system_prompt if system_prompt.strip() else None,
            files=[],
            images=[],
            model=args.model,
            reasoning_effort=args.effort,
        )
    except CLIAgentError as exc:
        # The diagnostics are the whole point of a failed background run: nobody is
        # watching the process, so anything not written here is lost. A first version
        # omitted stdout/stderr and produced "exited with status 1" and nothing else,
        # which is a readable artifact that says nothing.
        return _payload(
            ok=False,
            error=str(exc),
            returncode=exc.returncode,
            stdout=(exc.stdout or "")[-4000:] or None,
            stderr=(exc.stderr or "")[-4000:] or None,
            salvaged_content=(exc.parsed.content if exc.parsed else None),
            requested_model=getattr(exc, "requested_model", None),
            resolved_model=getattr(exc, "resolved_model", None),
            observed_model=getattr(exc, "observed_model", None),
            resolved_effort=getattr(exc, "resolved_effort", None),
            resolved_executable=resolved_exe,
            duration_seconds=round(time.time() - started, 2),
        )

    usage = asdict(result.token_usage) if result.token_usage else None
    return _payload(
        ok=True,
        content=result.parsed.content,
        cli_name=client.name,
        resolved_executable=resolved_exe,
        requested_model=result.requested_model,
        resolved_model=result.resolved_model,
        observed_model=result.observed_model,
        resolved_effort=result.resolved_effort,
        duration_seconds=round(result.duration_seconds, 2),
        returncode=result.returncode,
        normalized_usage={k: v for k, v in usage.items() if v is not None} if usage else None,
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cli", required=True)
    p.add_argument("--role", default="default")
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    out = Path(args.out)
    try:
        payload = asyncio.run(_run(args))
    except Exception as exc:  # the process must always leave a readable artifact
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Print the headline so it lands in the background process's captured output too.
    print(f"clink_bg: ok={payload.get('ok')} -> {out}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
