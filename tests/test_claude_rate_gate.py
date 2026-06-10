"""Rate-limit integration of the Claude Code backend (core.runtime.claude_code).

Never invokes the real ``claude`` CLI: the binary resolver and
``subprocess.run`` are monkeypatched, mirroring tests/test_claude_code.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import core.runtime.claude_code as cc
from core.runtime.claude_code import ClaudeRateLimitedError, ClaudeUnavailableError
from core.runtime.rate_limit import RateLimitInfo, detect_rate_limit
from core.runtime.usage_gate import RateLimitGate


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    """Gate state / timing log を tmp_path に隔離する（conftest パターン準拠）。"""
    monkeypatch.setattr("core.platform.state.get_platform_home", lambda: tmp_path)
    return tmp_path


def test_rate_limited_error_is_unavailable_subclass():
    # 既存の except ClaudeUnavailableError フォールバックを壊さないための契約。
    assert issubclass(ClaudeRateLimitedError, ClaudeUnavailableError)


def test_precall_gate_blocks_without_spawning(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    reset = datetime.now(timezone.utc) + timedelta(minutes=10)
    RateLimitGate().report(
        RateLimitInfo(limited=True, reset_at=reset, scope="session", message="usage limit")
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess must not be spawned while rate-limited")

    monkeypatch.setattr(cc.subprocess, "run", fail_run)

    with pytest.raises(ClaudeRateLimitedError) as ei:
        cc.run_claude_sync("hello")
    assert ei.value.info.limited
    # メッセージには ISO reset 時刻が埋め込まれ、str(exc) を detect_rate_limit に
    # かけ直すレガシー callers（content_runner 等）でも正確に再パースできる。
    reparsed = detect_rate_limit(str(ei.value))
    assert reparsed.limited
    assert reparsed.reset_at is not None


def test_precall_gate_bypass_env(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    RateLimitGate().report(
        RateLimitInfo(limited=True, reset_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    )
    monkeypatch.setenv("PANTHEON_NO_RATE_GATE", "1")

    class FakeProc:
        returncode = 0
        stdout = json.dumps({"type": "result", "result": "ok", "is_error": False})
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    assert cc.run_claude_sync("hello").content == "ok"


def test_nonzero_exit_limit_detected_and_reported_to_gate(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "Claude usage limit reached. Your limit will reset in 3 hours."

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())

    with pytest.raises(ClaudeRateLimitedError) as ei:
        cc.run_claude_sync("hello")
    assert ei.value.info.reset_at is not None

    # gate に共有された → 以後の呼び出しは subprocess を起動せずに即 raise
    assert RateLimitGate().is_limited()

    def fail_run(*args, **kwargs):
        raise AssertionError("second call must be blocked by the gate")

    monkeypatch.setattr(cc.subprocess, "run", fail_run)
    with pytest.raises(ClaudeRateLimitedError):
        cc.run_claude_sync("hello again")


def test_nonzero_exit_without_limit_raises_unavailable(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ClaudeUnavailableError) as ei:
        cc.run_claude_sync("hello")
    assert not isinstance(ei.value, ClaudeRateLimitedError)
    assert not RateLimitGate().is_limited()


def test_exit0_is_error_limit_detected(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 0
        stdout = json.dumps(
            {"type": "result", "is_error": True, "result": "5-hour usage limit reached"}
        )
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ClaudeRateLimitedError):
        cc.run_claude_sync("hello")
    assert RateLimitGate().is_limited()


def test_exit0_short_limit_text_detected(isolated_home, monkeypatch):
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 0
        stdout = json.dumps({"result": "Usage limit reached — try again in 2 hours"})
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ClaudeRateLimitedError) as ei:
        cc.run_claude_sync("hello")
    assert ei.value.info.reset_at is not None


def test_exit0_long_content_mentioning_limits_is_not_flagged(isolated_home, monkeypatch):
    """誤検知ガード: 長文の正常な生成物が 'rate limit' に言及しても pause しない。"""
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    body = "このAPIには rate limit があるため、429 が返ったら指数バックオフしてください。" * 20
    assert len(body) > 400

    class FakeProc:
        returncode = 0
        stdout = json.dumps({"result": body, "is_error": False})
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    response = cc.run_claude_sync("hello")
    assert response.content == body
    assert not RateLimitGate().is_limited()


def test_exit0_short_content_with_bare_signals_is_not_flagged(isolated_home, monkeypatch):
    """誤検知ガード: X 投稿サイズの正常な短文に '429'/'quota'/'rate limit' が
    含まれても、結果は破棄されず gate も汚染されない（strict 検知）。"""
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    bodies = [
        "対象記事は1,429件でした。詳細はレポートをご覧ください。",
        "API の rate limit に備えて quota 監視を自動化しよう！ #開発 #API",
    ]
    for body in bodies:
        assert len(body) <= 400

        class FakeProc:
            returncode = 0
            stdout = json.dumps({"result": body, "is_error": False})
            stderr = ""

        monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
        response = cc.run_claude_sync("hello")
        assert response.content == body
        assert not RateLimitGate().is_limited()


def test_exit0_real_cli_session_limit_phrasing_detected(isolated_home, monkeypatch):
    """実際の CLI 文言（You've hit your session limit · resets …）を検知できる。"""
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 0
        stdout = json.dumps(
            {"result": "You've hit your session limit · resets 3:20am (Asia/Tokyo)"}
        )
        stderr = ""

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ClaudeRateLimitedError) as ei:
        cc.run_claude_sync("hello")
    assert ei.value.info.reset_at is not None
    assert RateLimitGate().is_limited()


def test_nonzero_exit_with_bare_429_in_trace_is_not_flagged(isolated_home, monkeypatch):
    """失敗出力のスタックトレースに偶発的な '429' が含まれても全体 pause しない。"""
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = 'File "cli.js", line 429, in main\nTypeError: cannot read undefined'

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ClaudeUnavailableError) as ei:
        cc.run_claude_sync("hello")
    assert not isinstance(ei.value, ClaudeRateLimitedError)
    assert not RateLimitGate().is_limited()


def test_scan_result_text_ignores_numeric_stats_in_envelope():
    """1行 JSON の統計値（duration_ms:14290 等）では発火しない。"""
    stdout = json.dumps(
        {
            "type": "result",
            "result": "完了しました。3件の提案を生成。",
            "is_error": False,
            "duration_ms": 14290,
            "total_cost_usd": 0.0429,
        }
    )
    assert cc.scan_result_text_for_rate_limit(stdout) is None


def test_scan_result_text_detects_is_error_limit():
    stdout = json.dumps(
        {
            "type": "result",
            "result": "You've hit your session limit · resets 3:20am (Asia/Tokyo)",
            "is_error": True,
            "duration_ms": 120,
        }
    )
    info = cc.scan_result_text_for_rate_limit(stdout)
    assert info is not None and info.limited
    assert info.reset_at is not None
