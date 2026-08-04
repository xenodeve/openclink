"""An omitted model is refused, not silently resolved to the CLI's default (#29).

The request field used to advertise `Omit to use the CLI's configured default`,
and that fallback is what made a model nobody chose indistinguishable from a model
someone did — the same class of defect as #27 (a model the client cannot serve) and
#28 (a silent substitution), one step earlier in the chain.

Decision recorded on the issue before any code: refuse immediately, no grace
period. A warning window keeps serving the unchosen model, which is the defect
being removed; the caller is an agent with no habit of reading deprecation
metadata; and every caller is one of this developer's own repos.
"""

from __future__ import annotations

import json

import pytest

from tools.clink import CLinkTool
from tools.shared.exceptions import ToolExecutionError


@pytest.mark.asyncio
async def test_an_omitted_model_is_refused():
    with pytest.raises(ToolExecutionError) as excinfo:
        await CLinkTool().execute(
            {
                "prompt": "hi",
                "cli_name": "gemini",
                "role": "default",
                "absolute_file_paths": [],
                "images": [],
            }
        )
    message = json.loads(excinfo.value.payload)["content"]
    # Actionable, per #27's rule: it has to say what to do, not only that this failed.
    assert "model" in message.lower()


@pytest.mark.asyncio
async def test_an_explicitly_null_model_is_refused_the_same_way():
    # `"model": None` and an absent key are the same request. Refusing one and
    # accepting the other would put the fallback back behind a spelling.
    with pytest.raises(ToolExecutionError) as excinfo:
        await CLinkTool().execute(
            {
                "prompt": "hi",
                "cli_name": "gemini",
                "role": "default",
                "absolute_file_paths": [],
                "images": [],
                "model": None,
            }
        )
    assert "model" in json.loads(excinfo.value.payload)["content"].lower()


def test_the_schema_declares_model_required_rather_than_only_saying_so_in_prose():
    # The description asserted below says "Required", but a description is not a
    # contract — an MCP client validates against `required`, so a schema that only
    # says it in prose lets a caller omit the field, pass validation, and discover
    # the refusal at execution time instead. The declared contract has to be the
    # one actually enforced, or #29 is only half-shipped.
    assert "model" in CLinkTool().get_input_schema()["required"]


def test_the_schema_no_longer_advertises_a_fallback_that_does_not_exist():
    # "no longer advertises" is the AC, not "no longer mentions": the replacement
    # names the fallback in order to say it is gone, which is the useful thing to
    # tell a caller that has been relying on it. So this pins the absence of the
    # instruction, not the absence of the words.
    schema = CLinkTool().get_input_schema()
    description = schema["properties"]["model"]["description"]
    assert "Omit to use" not in description
    assert "Required" in description
