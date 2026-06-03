"""
構造化ログ（J2）と相関ID（J3）の共通基盤。

- `request_id_var`: リクエスト相関ID（HTTP ミドルウェアが設定し、ログに自動付与）。
- `SecretRedactingFilter` / `redact_secrets`: APIキー/トークンらしき文字列をマスク（A6）。
  ハンドラに付与すれば子ロガーから伝播したレコードも確実に redaction される。
- `JsonLogFormatter`: 1行1JSON のログ整形（ts/level/logger/message/request_id/exc）。
- `configure_logging()`: `REPOCORP_LOG_FORMAT=json` の時のみ root を JSON ハンドラに切替える
  （既定 text では何もしない＝uvicorn 等の既存出力を壊さない）。`REPOCORP_LOG_LEVEL` でレベル指定。
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "request_id_var",
    "redact_secrets",
    "SecretRedactingFilter",
    "JsonLogFormatter",
    "configure_logging",
]

# リクエスト相関ID（未設定時は空文字）。
request_id_var: ContextVar[str] = ContextVar("repocorp_request_id", default="")

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gsk_[A-Za-z0-9]{16,}"),
]


def redact_secrets(text: str) -> str:
    """APIキー/トークンらしき文字列を ***REDACTED*** に置換する。"""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


class SecretRedactingFilter(logging.Filter):
    """ログメッセージ中の APIキー/トークンらしき文字列をマスクする（A6）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_secrets(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_STD_RECORD_KEYS = frozenset(vars(logging.makeLogRecord({})))


class JsonLogFormatter(logging.Formatter):
    """ログを 1 行 1 JSON で整形する。相関IDと追加属性を含める。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # logger.info(..., extra={...}) で渡された非標準属性を取り込む
        for key, value in record.__dict__.items():
            if key not in _STD_RECORD_KEYS and not key.startswith("_"):
                payload.setdefault(key, value)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging(force: bool = False) -> bool:
    """環境変数に応じてログを設定する。JSON へ切替えた場合のみ True を返す。

    `REPOCORP_LOG_FORMAT=json` の時だけ root ハンドラを JSON 化し（既存ハンドラを置換して
    二重出力を防止）、redaction フィルタを付与する。既定（text）では何もしない。
    `REPOCORP_LOG_LEVEL` が指定されていれば root レベルを設定する。冪等。
    """
    global _configured
    if _configured and not force:
        return False
    _configured = True

    level_name = os.getenv("REPOCORP_LOG_LEVEL", "").upper()
    if level_name:
        logging.getLogger().setLevel(getattr(logging, level_name, logging.INFO))

    log_file = os.getenv("REPOCORP_LOG_FILE", "").strip()
    is_json = os.getenv("REPOCORP_LOG_FORMAT", "").lower() == "json"
    if not is_json and not log_file:
        return False

    formatter: logging.Formatter = (
        JsonLogFormatter()
        if is_json
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    if log_file:
        # ローテーション付きファイルハンドラ（J5）。サイズ/世代は env で調整。
        from logging.handlers import RotatingFileHandler

        max_bytes = _int_env("REPOCORP_LOG_MAX_BYTES", 5 * 1024 * 1024)
        backups = _int_env("REPOCORP_LOG_BACKUPS", 3)
        handler: logging.Handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(SecretRedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    if not level_name:
        root.setLevel(logging.INFO)
    return True


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return default
