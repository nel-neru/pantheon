"""claude_code の usage 実測と task_type ルーティング配線のテスト。

実 CLI は呼ばない（binary 解決と subprocess.run を monkeypatch）。
"""

from __future__ import annotations

import json

import pytest

import core.runtime.claude_code as cc
from core.runtime.model_router import reset_router


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    reset_router()
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    monkeypatch.delenv("PANTHEON_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("PANTHEON_MODEL_ROUTING", raising=False)
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    yield
    reset_router()


def _fake_proc(payload: dict):
    class FakeProc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""

    return FakeProc()


def _capture_args(monkeypatch, payload=None):
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _fake_proc(payload or {"result": "ok", "is_error": False})

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    return captured


def test_task_type_routes_model(monkeypatch):
    captured = _capture_args(monkeypatch)
    cc.run_claude_sync("hi", task_type="conversation")
    args = captured["args"]
    assert "--model" in args
    assert args[args.index("--model") + 1] == "haiku"


def test_heavy_task_routes_opus(monkeypatch):
    captured = _capture_args(monkeypatch)
    cc.run_claude_sync("hi", task_type="improvement_execution")
    args = captured["args"]
    assert args[args.index("--model") + 1] == "opus"


def test_explicit_model_beats_router(monkeypatch):
    captured = _capture_args(monkeypatch)
    cc.run_claude_sync("hi", model="opus", task_type="conversation")
    args = captured["args"]
    assert args[args.index("--model") + 1] == "opus"
    assert "haiku" not in args


def test_untagged_call_keeps_legacy_behaviour(monkeypatch):
    """task_type 無しの呼び出しはルーティングしない（env も無ければ --model なし）。"""
    captured = _capture_args(monkeypatch)
    cc.run_claude_sync("hi")
    assert "--model" not in captured["args"]


def test_kill_switch_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PANTHEON_MODEL_ROUTING", "0")
    monkeypatch.setenv("PANTHEON_DEFAULT_MODEL", "sonnet")
    captured = _capture_args(monkeypatch)
    cc.run_claude_sync("hi", task_type="improvement_execution")
    args = captured["args"]
    assert args[args.index("--model") + 1] == "sonnet"  # router 無効 → env


def test_usage_extracted_into_response_and_timing_log(monkeypatch, tmp_path):
    log_file = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PANTHEON_CLAUDE_TIMING_LOG", str(log_file))
    payload = {
        "type": "result",
        "result": "done",
        "is_error": False,
        "usage": {"input_tokens": 1200, "output_tokens": 340, "cache_read_input_tokens": 900},
        "total_cost_usd": 0.0123,
    }
    _capture_args(monkeypatch, payload)

    response = cc.run_claude_sync("hi", task_type="code_review")

    assert response.usage == payload["usage"]
    record = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["input_tokens"] == 1200
    assert record["output_tokens"] == 340
    assert record["cache_read_tokens"] == 900
    assert record["total_cost_usd"] == 0.0123
    assert record["task_type"] == "code_review"
    assert record["model"] == "sonnet"  # ルーティング結果が記録される


def test_usage_absent_on_old_cli_falls_back(monkeypatch, tmp_path):
    log_file = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PANTHEON_CLAUDE_TIMING_LOG", str(log_file))
    _capture_args(monkeypatch, {"result": "done", "is_error": False})

    response = cc.run_claude_sync("hi", task_type="conversation")

    assert response.usage is None  # 旧 CLI: 実測なし（文字数概算へのフォールバックは呼び出し側）
    record = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["input_tokens"] is None
    assert record["prompt_chars"] == 2  # 概算用の文字数は引き続き記録される
