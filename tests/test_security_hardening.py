"""Tests for the P0 security/robustness batch (web/server.py + web/terminal.py)."""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

import web.server as server
from web.terminal import is_allowed_origin

client = TestClient(server.app)


def test_health_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "has_llm" in body
    assert "terminal_sessions" in body


def test_atomic_write_text(tmp_path):
    target = tmp_path / "sub" / "data.json"
    server._atomic_write_text(target, json.dumps({"a": 1}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    # 上書きも原子的に成功し、一時ファイルが残らない
    server._atomic_write_text(target, json.dumps({"a": 2}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}
    assert list(target.parent.glob("*.tmp.*")) == []


def test_redact_secrets():
    samples = [
        ("anthropic key sk-ant-ABCD1234efgh5678 here", "sk-ant-"),
        ("openai sk-proj-ABCDEFGH12345678ZZZZ tail", "sk-"),
        ("token ghp_ABCDEFGHIJKLMNOP1234 x", "ghp_"),
        ("google AIzaABCDEFGH1234567890 y", "AIza"),
        ("groq gsk_ABCDEFGHIJKLMNOP1234 z", "gsk_"),
    ]
    for text, marker in samples:
        redacted = server._redact_secrets(text)
        assert "***REDACTED***" in redacted
        assert marker not in redacted or marker == "sk-"  # sk- prefix replaced wholesale


def test_secret_redacting_filter_mutates_record():
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="f", lineno=1,
        msg="saving key sk-ant-ABCDEFGH12345678 to disk", args=(), exc_info=None,
    )
    server._SecretRedactingFilter().filter(record)
    assert "***REDACTED***" in record.getMessage()
    assert "sk-ant-ABCDEFGH12345678" not in record.getMessage()


def test_is_allowed_origin():
    assert is_allowed_origin(None) is True  # 非ブラウザは client host で別途ガード
    assert is_allowed_origin("http://localhost:7860") is True
    assert is_allowed_origin("http://127.0.0.1:5173") is True
    assert is_allowed_origin("http://evil.example.com") is False
    assert is_allowed_origin("http://10.0.0.5:7860") is False


def test_trusted_host_rejects_foreign_host(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    # localhost(testclient既定) は許可
    assert client.get("/api/health").status_code == 200
    # 見知らぬ Host ヘッダ（DNS リバインディング想定）は拒否
    resp = client.get("/api/health", headers={"host": "evil.example.com"})
    assert resp.status_code == 400


def test_trusted_hosts_allowlist_contents():
    hosts = server._trusted_hosts()
    assert "localhost" in hosts and "127.0.0.1" in hosts and "testclient" in hosts
    assert "evil.example.com" not in hosts


def test_assets_have_immutable_cache_header(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    # ハッシュ付き /assets/* は長期 immutable キャッシュ（E10）。404 でもミドルウェアが付与。
    resp = client.get("/assets/does-not-exist-12345.js")
    assert "immutable" in resp.headers.get("cache-control", "")


def test_cors_methods_tightened():
    # ワイルドカードではなく明示メソッドに絞られている
    cors = next(
        (mw for mw in server.app.user_middleware if "CORSMiddleware" in str(mw.cls)),
        None,
    )
    assert cors is not None
    methods = cors.kwargs.get("allow_methods", [])
    assert "*" not in methods
    assert "GET" in methods and "POST" in methods


# --------------------------------------------------------------------------- #
# A8: リクエストボディサイズ上限
# --------------------------------------------------------------------------- #


def test_body_size_limit_rejects_oversized_request(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("REPOCORP_MAX_BODY_BYTES", "100")
    # Content-Length 超過は本文処理前に 413（ルーティング前に拒否）
    resp = client.post("/api/health", content="x" * 500)
    assert resp.status_code == 413


def test_body_size_limit_allows_small_request(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("REPOCORP_MAX_BODY_BYTES", "100000")
    assert client.get("/api/health").status_code == 200


def test_max_body_bytes_env_override(monkeypatch):
    monkeypatch.setenv("REPOCORP_MAX_BODY_BYTES", "12345")
    assert server._max_body_bytes() == 12345
    monkeypatch.setenv("REPOCORP_MAX_BODY_BYTES", "not-an-int")
    assert server._max_body_bytes() == server._DEFAULT_MAX_BODY_BYTES


# --------------------------------------------------------------------------- #
# A2: 任意のローカル API トークン認証（既定は無効）
# --------------------------------------------------------------------------- #


def test_api_token_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.delenv("REPOCORP_API_TOKEN", raising=False)
    # 未設定なら認証無効（既存挙動不変）→ 401 にはならない
    assert client.get("/api/settings").status_code != 401


def test_api_token_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("REPOCORP_API_TOKEN", "secret-token-123")
    # トークン無し → 401
    assert client.get("/api/settings").status_code == 401
    # X-RepoCorp-Token 一致 → 通過（401 以外）
    assert client.get("/api/settings", headers={"X-RepoCorp-Token": "secret-token-123"}).status_code != 401
    # Authorization: Bearer 形式も可
    assert client.get("/api/settings", headers={"Authorization": "Bearer secret-token-123"}).status_code != 401
    # 誤ったトークン → 401
    assert client.get("/api/settings", headers={"X-RepoCorp-Token": "wrong"}).status_code == 401


def test_api_token_health_endpoint_exempt(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("REPOCORP_API_TOKEN", "secret-token-123")
    # health はトークン無しでも到達可能（監視のため除外）
    assert client.get("/api/health").status_code == 200


def test_api_token_non_api_paths_exempt(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("REPOCORP_API_TOKEN", "secret-token-123")
    # SPA / 静的アセットは認証対象外（/api/ 以外）
    assert client.get("/assets/missing-123.js").status_code != 401


def test_resolve_api_token_prefers_env(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"api_auth_token": "from-settings"}', encoding="utf-8")
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.delenv("REPOCORP_API_TOKEN", raising=False)
    assert server._resolve_api_token() == "from-settings"
    monkeypatch.setenv("REPOCORP_API_TOKEN", "from-env")
    assert server._resolve_api_token() == "from-env"
