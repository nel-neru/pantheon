"""
自己改善ループ向けエラーハンドリングと回復力強化

将来的にはもっと高度なリトライ戦略やサーキットブレーカーも検討。
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


def with_error_handling(
    max_retries: int = 2,
    fallback_return: Any = None,
    log_errors: bool = True,
):
    """
    非同期関数用のシンプルなエラーハンドリングデコレータ
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if log_errors:
                        logger.warning(f"[ErrorHandling] {func.__name__} failed (attempt {attempt + 1}): {e}")

                    if attempt == max_retries:
                        if log_errors:
                            logger.error(f"[ErrorHandling] {func.__name__} failed after {max_retries} retries.")
                        # フォールバック値を返す（グラフが止まらないようにする）
                        return fallback_return
            return fallback_return
        return wrapper
    return decorator


# 使用例（LangGraphノードに適用する場合）
# @with_error_handling(max_retries=2, fallback_return={"status": "error", "result": None})
# async def some_node(state):
#     ...
