"""Model catalog configuration survives from JSON into the resolved client."""

from __future__ import annotations

import json
from pathlib import Path

import clink.registry as registry_module
from clink.registry import ClinkRegistry


def _load_client(tmp_path: Path, monkeypatch, model_catalog: dict[str, list[str]] | None = None):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    payload = {"name": "codex", "command": "codex"}
    if model_catalog is not None:
        payload["model_catalog"] = model_catalog
    (config_dir / "codex.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(registry_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(registry_module, "USER_CONFIG_DIR", tmp_path / "missing-user-config")
    monkeypatch.delenv(registry_module.CONFIG_ENV_VAR, raising=False)
    return ClinkRegistry().get_client("codex")


def test_missing_model_catalog_defaults_to_none(tmp_path, monkeypatch):
    client = _load_client(tmp_path, monkeypatch)

    assert client.model_catalog is None


def test_model_catalog_resolves_intact(tmp_path, monkeypatch):
    catalog = {
        "composer-2.5": ["low", "high"],
        "gpt-5.6-sol": ["medium"],
    }

    client = _load_client(tmp_path, monkeypatch, catalog)

    assert client.model_catalog == catalog


def test_empty_model_catalog_tier_list_is_preserved(tmp_path, monkeypatch):
    catalog = {"composer-2.5": []}

    client = _load_client(tmp_path, monkeypatch, catalog)

    assert client.model_catalog == catalog
    assert client.model_catalog["composer-2.5"] == []
