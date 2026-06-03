"""API exposure of provider capabilities and model lists."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.server as server

client = TestClient(server.app)

_ENV_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GITHUB_TOKEN", "GOOGLE_API_KEY"]
ALL_PROVIDERS = {"anthropic", "openai", "groq", "github_models", "gemini"}


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """実 ~/.repocorp や環境変数のキーに依存せず、ネットワークも叩かせない。"""
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    server._model_cache.clear()
    return monkeypatch


def test_settings_includes_provider_capabilities(hermetic):
    response = client.get("/api/settings")
    assert response.status_code == 200
    caps = response.json()["provider_capabilities"]
    assert ALL_PROVIDERS <= set(caps)
    assert caps["anthropic"]["supports_tools"] is True
    assert caps["gemini"]["max_context_tokens"] > 0


def test_provider_models_includes_capabilities(hermetic):
    response = client.get("/api/providers/anthropic/models")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["capabilities"]["provider"] == "anthropic"
    # キー未設定なので fallback 一覧が返る（ネットワーク非依存）
    assert body["source"] in {"fallback", "cache"}
    assert body["models"]


def test_unknown_provider_models_returns_capabilities_shell(hermetic):
    response = client.get("/api/providers/not-a-provider/models")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "unknown"
    assert body["models"] == []
    assert body["capabilities"]["provider"] == "not-a-provider"
