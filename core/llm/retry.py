"""
retry — LLM 呼び出しのタイムアウト / 指数バックオフ / エラー正規化（B2, B3, B9）

すべての provider 呼び出しをこのラッパで包むことで「どのプロバイダーでも」一貫した
信頼性（ハング防止・一時障害のリトライ・統一エラー型）を得る。

ベストプラクティス:
- 一時障害（429 / 5xx / タイムアウト / コネクション断）のみ指数バックオフでリトライ
- 恒久エラー（400/401/404 等）は即時に正規化例外として送出（無駄なリトライをしない）
- 全呼び出しにタイムアウト（無限ハング防止）
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, Tuple

__all__ = [
    "LLMError",
    "classify_exception",
    "call_with_retry",
    "DEFAULT_TIMEOUT",
    "DEFAULT_ATTEMPTS",
]

DEFAULT_TIMEOUT = 60.0
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0

# 一時障害を示す文字列マーカー（SDK 例外メッセージのヒューリスティック分類用）
_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "temporarily",
    "overloaded",
    "rate limit",
    "ratelimit",
    "too many requests",
    "try again",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
)


class LLMError(Exception):
    """プロバイダー非依存に正規化された LLM 呼び出しエラー。"""

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status: Optional[int] = None,
        retryable: bool = False,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retryable = retryable
        if cause is not None:
            self.__cause__ = cause


def classify_exception(exc: BaseException) -> Tuple[bool, Optional[int]]:
    """例外が一時障害（リトライ可）かを判定し、(retryable, status) を返す。"""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "status", None)
    if isinstance(status, int):
        if status == 429 or 500 <= status < 600:
            return True, status
        return False, status

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return True, None

    text = f"{type(exc).__name__} {exc}".lower()
    if any(marker in text for marker in _RETRYABLE_MARKERS):
        return True, None
    return False, None


async def call_with_retry(
    factory: Callable[[], Awaitable[Any]],
    *,
    provider: str = "",
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    timeout: Optional[float] = DEFAULT_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    """`factory()`（毎回新しい awaitable を返す）をタイムアウト＋リトライ付きで実行する。

    一時障害のみ指数バックオフでリトライ。最終的に失敗したら LLMError を送出する。
    """
    attempts = max(1, attempts)
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            awaitable = factory()
            if timeout and timeout > 0:
                return await asyncio.wait_for(awaitable, timeout)
            return await awaitable
        except asyncio.CancelledError:
            raise
        except LLMError:
            raise
        except BaseException as exc:  # noqa: BLE001 — 分類して正規化するため一旦広く捕捉
            if not isinstance(exc, Exception):
                raise
            retryable, status = classify_exception(exc)
            last_exc = exc
            if not retryable or attempt >= attempts:
                raise LLMError(
                    f"{provider or 'LLM'} 呼び出しに失敗しました: {exc}",
                    provider=provider,
                    status=status,
                    retryable=retryable,
                    cause=exc,
                ) from exc
            await sleep(min(max_delay, base_delay * (2 ** (attempt - 1))))

    raise LLMError(
        f"{provider or 'LLM'} 呼び出しに失敗しました（リトライ上限）",
        provider=provider,
        retryable=True,
        cause=last_exc,
    )
