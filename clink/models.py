"""Pydantic models for clink configuration and runtime structures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, field_validator


class OutputCaptureConfig(BaseModel):
    """Optional configuration for CLIs that write output to disk."""

    flag_template: str = Field(..., description="Template used to inject the output path, e.g. '--output {path}'.")
    cleanup: bool = Field(
        default=True,
        description="Whether the temporary file should be removed after reading.",
    )


class CLIRoleConfig(BaseModel):
    """Role-specific configuration loaded from JSON manifests."""

    prompt_path: str | None = Field(
        default=None,
        description="Path to the prompt file that seeds this role.",
    )
    role_args: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None)

    @field_validator("role_args", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("role_args must be a list of strings or a single string")


class ModelRate(BaseModel):
    """Price per token class for one model, in the card's own unit.

    Every class is optional. A class the card does not price is not free — it is
    unpriced, and the caller is told which ones those were rather than being
    handed a total that quietly omits them.
    """

    input: float | None = None
    cached_input: float | None = None
    output: float | None = None
    reasoning_output: float | None = None


class RateCard(BaseModel):
    """What one client's models cost, declared in that client's configuration.

    `unit` travels with every figure computed from this card. A subscription
    backend prices in credits and a token-billed one in currency; the two are
    never summed, so a bare number would be unusable to a caller that routes
    across both.
    """

    unit: str = Field(..., description="e.g. 'USD' or 'credits'. Carried onto every cost computed from this card.")
    per_tokens: PositiveInt = Field(
        default=1_000_000,
        description="The token count the rates are quoted per. Vendors quote per 1M; a card may say otherwise.",
    )
    models: dict[str, ModelRate] = Field(default_factory=dict)


class CLIClientConfig(BaseModel):
    """Raw CLI client configuration before internal defaults are applied."""

    name: str
    command: str | None = None
    working_dir: str | None = None
    additional_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: PositiveInt | None = Field(default=None)
    roles: dict[str, CLIRoleConfig] = Field(default_factory=dict)
    output_to_file: OutputCaptureConfig | None = None
    model_catalog: dict[str, list[str]] | None = None
    rate_card: RateCard | None = None

    @field_validator("additional_args", mode="before")
    @classmethod
    def _ensure_args_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("additional_args must be a list of strings or a single string")


class ResolvedCLIRole(BaseModel):
    """Runtime representation of a CLI role with resolved prompt path."""

    name: str
    prompt_path: Path
    role_args: list[str] = Field(default_factory=list)
    description: str | None = None


class ResolvedCLIClient(BaseModel):
    """Runtime configuration after merging defaults and validating paths."""

    name: str
    executable: list[str]
    working_dir: Path | None
    internal_args: list[str] = Field(default_factory=list)
    config_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    parser: str
    runner: str | None = None
    roles: dict[str, ResolvedCLIRole]
    output_to_file: OutputCaptureConfig | None = None
    model_catalog: dict[str, list[str]] | None = None
    rate_card: RateCard | None = None

    def list_roles(self) -> list[str]:
        return list(self.roles.keys())

    def get_role(self, role_name: str | None) -> ResolvedCLIRole:
        key = role_name or "default"
        if key not in self.roles:
            available = ", ".join(sorted(self.roles.keys()))
            raise KeyError(f"Role '{role_name}' not configured for CLI '{self.name}'. Available roles: {available}")
        return self.roles[key]
