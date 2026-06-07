"""Tests for the one-shot fast-path + timing instrumentation in claude_code.

Covers the cold-start-trimming flags (PANTHEON_CLAUDE_FAST / *_FAST_ARGS), the
flag-error fallback (so a CLI version mismatch never breaks generation), and the
per-call timing JSONL log.
"""

from __future__ import annotations

import json
import subprocess

from core.runtime import claude_code as cc


def _completed(returncode=0, stdout='{"result": "ok"}', stderr=""):
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# --------------------------------------------------------------------------- #
# _build_cli_args / _fast_args
# --------------------------------------------------------------------------- #
def test_fast_args_default_suppress_mcp(monkeypatch):
    monkeypatch.delenv(cc.FAST_ENV, raising=False)
    monkeypatch.delenv(cc.FAST_ARGS_ENV, raising=False)
    args = cc._build_cli_args("claude", "hi", "sys", "opus")
    assert args[:5] == ["claude", "-p", "hi", "--output-format", "json"]
    assert "--append-system-prompt" in args and "sys" in args
    assert "--model" in args and "opus" in args
    # default fast args suppress project MCP servers
    assert "--strict-mcp-config" in args
    assert args[args.index("--mcp-config") + 1] == "{}"


def test_fast_args_disabled(monkeypatch):
    monkeypatch.setenv(cc.FAST_ENV, "0")
    args = cc._build_cli_args("claude", "hi", None, None)
    assert "--strict-mcp-config" not in args
    assert args == ["claude", "-p", "hi", "--output-format", "json"]


def test_fast_args_override(monkeypatch):
    monkeypatch.setenv(cc.FAST_ENV, "1")
    monkeypatch.setenv(cc.FAST_ARGS_ENV, "--bare --max-turns 1")
    args = cc._build_cli_args("claude", "hi", None, None)
    assert "--bare" in args
    assert args[args.index("--max-turns") + 1] == "1"
    assert "--strict-mcp-config" not in args


def test_build_cli_args_fast_false_ignores_env(monkeypatch):
    monkeypatch.setenv(cc.FAST_ENV, "1")
    args = cc._build_cli_args("claude", "hi", None, None, fast=False)
    assert "--strict-mcp-config" not in args


def test_looks_like_flag_error():
    assert cc._looks_like_flag_error("error: unknown option '--strict-mcp-config'")
    assert cc._looks_like_flag_error("Unexpected argument --bare")
    # a problem with the injected --mcp-config "{}" value also triggers a clean retry
    assert cc._looks_like_flag_error("failed to parse --mcp-config")
    assert cc._looks_like_flag_error("invalid mcpServers configuration")
    assert not cc._looks_like_flag_error("rate limit reached, try again later")
    assert not cc._looks_like_flag_error("")


# --------------------------------------------------------------------------- #
# run_claude_sync: timing log + flag-error fallback
# --------------------------------------------------------------------------- #
def test_timing_log_written(monkeypatch, tmp_path):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv(cc.TIMING_LOG_ENV, str(log))
    monkeypatch.delenv(cc.FAST_ENV, raising=False)
    monkeypatch.delenv(cc.FAST_ARGS_ENV, raising=False)
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: _completed())

    resp = cc.run_claude_sync("hello", model="opus")
    assert resp.content == "ok"

    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["returncode"] == 0
    assert rec["timed_out"] is False
    assert rec["fast"] is True
    assert rec["prompt_chars"] == len("hello")
    assert rec["model"] == "opus"
    assert isinstance(rec["elapsed_ms"], int)


def test_fallback_on_flag_error(monkeypatch, tmp_path):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv(cc.TIMING_LOG_ENV, str(log))
    monkeypatch.delenv(cc.FAST_ENV, raising=False)
    monkeypatch.delenv(cc.FAST_ARGS_ENV, raising=False)
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        if len(calls) == 1:
            # first attempt: CLI rejects a fast-path flag
            return _completed(
                returncode=2, stdout="", stderr="error: unknown option --strict-mcp-config"
            )
        return _completed(returncode=0, stdout='{"result": "recovered"}')

    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    resp = cc.run_claude_sync("hello")
    assert resp.content == "recovered"
    assert len(calls) == 2
    # retry dropped the fast-path flags
    assert "--strict-mcp-config" in calls[0]
    assert "--strict-mcp-config" not in calls[1]

    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["fast"] is False  # reflects the retry that actually returned


def test_non_flag_error_does_not_retry(monkeypatch):
    monkeypatch.delenv(cc.FAST_ENV, raising=False)
    monkeypatch.setenv(cc.TIMING_LOG_ENV, "off")
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")

    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return _completed(returncode=1, stdout="", stderr="some unrelated failure")

    monkeypatch.setattr(cc.subprocess, "run", fake_run)

    try:
        cc.run_claude_sync("hello")
    except cc.ClaudeUnavailableError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ClaudeUnavailableError")
    assert len(calls) == 1  # no retry on a non-flag error


def test_timing_log_disabled(monkeypatch, tmp_path):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv(cc.TIMING_LOG_ENV, "off")
    monkeypatch.setattr(cc, "claude_binary", lambda: "claude")
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: _completed())
    cc.run_claude_sync("hello")
    assert not log.exists()
