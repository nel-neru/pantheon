"""構造化ログ（J2）/ 相関ID（J3）/ リクエストメトリクス（J4）のテスト。"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

import core.logging_config as lc
import web.server as server
from core.logging_config import JsonLogFormatter, redact_secrets, request_id_var
from core.metrics.request_metrics import RequestMetrics

client = TestClient(server.app)


# --------------------------------------------------------------------------- #
# J2: 構造化ログ
# --------------------------------------------------------------------------- #


def test_json_log_formatter_includes_core_fields_and_request_id():
    fmt = JsonLogFormatter()
    record = logging.LogRecord("mylogger", logging.INFO, "f.py", 1, "hello %s", ("world",), None)
    token = request_id_var.set("rid-123")
    try:
        out = json.loads(fmt.format(record))
    finally:
        request_id_var.reset(token)
    assert out["level"] == "INFO"
    assert out["logger"] == "mylogger"
    assert out["message"] == "hello world"
    assert out["request_id"] == "rid-123"
    assert "ts" in out


def test_json_log_formatter_omits_request_id_when_unset():
    out = json.loads(JsonLogFormatter().format(logging.LogRecord("l", logging.INFO, "f", 1, "m", (), None)))
    assert "request_id" not in out


def test_json_log_formatter_includes_extra_attributes():
    record = logging.LogRecord("l", logging.INFO, "f", 1, "m", (), None)
    record.path = "/api/x"
    record.status_code = 200
    out = json.loads(JsonLogFormatter().format(record))
    assert out["path"] == "/api/x"
    assert out["status_code"] == 200


def test_redact_secrets_core_impl():
    assert "***REDACTED***" in redact_secrets("key sk-ant-ABCDEFGH12345678 end")
    assert "sk-ant-ABCDEFGH12345678" not in redact_secrets("sk-ant-ABCDEFGH12345678")


def test_configure_logging_json_installs_json_handler(monkeypatch):
    root = logging.getLogger()
    orig_handlers = root.handlers[:]
    orig_level = root.level
    orig_configured = lc._configured
    try:
        monkeypatch.setenv("REPOCORP_LOG_FORMAT", "json")
        assert lc.configure_logging(force=True) is True
        assert any(isinstance(h.formatter, JsonLogFormatter) for h in root.handlers)
    finally:
        root.handlers = orig_handlers
        root.setLevel(orig_level)
        lc._configured = orig_configured


def test_configure_logging_text_is_noop(monkeypatch):
    root = logging.getLogger()
    orig_handlers = root.handlers[:]
    orig_configured = lc._configured
    try:
        monkeypatch.delenv("REPOCORP_LOG_FORMAT", raising=False)
        monkeypatch.delenv("REPOCORP_LOG_FILE", raising=False)
        assert lc.configure_logging(force=True) is False
        assert root.handlers == orig_handlers
    finally:
        root.handlers = orig_handlers
        lc._configured = orig_configured


def test_configure_logging_file_uses_rotating_handler(tmp_path, monkeypatch):
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    orig_handlers = root.handlers[:]
    orig_level = root.level
    orig_configured = lc._configured
    try:
        monkeypatch.delenv("REPOCORP_LOG_FORMAT", raising=False)
        monkeypatch.setenv("REPOCORP_LOG_FILE", str(tmp_path / "app.log"))
        assert lc.configure_logging(force=True) is True
        assert any(isinstance(h, RotatingFileHandler) for h in root.handlers)
        logging.getLogger("test.j5").warning("hello-j5")
        assert (tmp_path / "app.log").exists()
    finally:
        for handler in root.handlers:
            try:
                handler.close()
            except Exception:
                pass
        root.handlers = orig_handlers
        root.setLevel(orig_level)
        lc._configured = orig_configured


# --------------------------------------------------------------------------- #
# J3: 相関ID（X-Request-ID）
# --------------------------------------------------------------------------- #


def test_request_id_generated_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "s.json")
    resp = client.get("/api/health")
    assert resp.headers.get("x-request-id")


def test_request_id_propagated_from_request(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "s.json")
    resp = client.get("/api/health", headers={"X-Request-ID": "my-rid-1"})
    assert resp.headers.get("x-request-id") == "my-rid-1"


# --------------------------------------------------------------------------- #
# J4: リクエストメトリクス
# --------------------------------------------------------------------------- #


def test_request_metrics_unit_record_and_reset():
    m = RequestMetrics()
    m.record(200, 10.0)
    m.record(500, 30.0)
    snap = m.snapshot()
    assert snap["requests"] == 2
    assert snap["errors"] == 1
    assert snap["avg_duration_ms"] == 20.0
    assert snap["by_status"] == {"200": 1, "500": 1}
    m.reset()
    assert m.snapshot()["requests"] == 0


def test_metrics_endpoint_counts_and_resets(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SETTINGS_FILE", tmp_path / "s.json")
    client.delete("/api/metrics")
    client.get("/api/health")
    snap = client.get("/api/metrics").json()
    assert snap["requests"] >= 1
    assert "by_status" in snap and "avg_duration_ms" in snap
