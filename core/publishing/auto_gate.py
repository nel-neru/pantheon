"""PUB-AUTO: 無人実投稿の安全ゲート（計画 §1.1 原則3 / Phase 2）。

「24/7 で寝てる間に出力」を実現するため、auto モードのジョブを **送信の直前まで** 自動準備する。
ただし **実際の外部送信（取り消せない外向きアクション）は既定で人手承認（handed_off）に委ねる**。

このモジュールは「無人の実送信を許可するか」のフラグだけを司る（既定 OFF）:
- OFF（既定）: auto ジョブは assisted 経路で下書きまで自動準備し handed_off（人間が最終送信）。
  → デーモンが寝ている間に投稿を準備し、人は1タップで送信するだけ。実送信は人手ゲートのまま。
- ON: 無人の実送信を許可する意思表示。ただし各アダプタの実 auto 送信実装（``supports_auto_send``）が
  揃って初めて実際に無人送信される（現状アダプタは未実装＝Phase 2 の明示的な残作業）。

フラグは ``~/.pantheon/publish_config.json`` の ``auto_send_enabled``（bool）。LLM 非依存。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PUBLISH_CONFIG_FILE = "publish_config.json"


def _config_path(platform_home: Path) -> Path:
    return Path(platform_home) / PUBLISH_CONFIG_FILE


def _resolve_home(platform_home: Optional[Path]) -> Path:
    if platform_home is not None:
        return Path(platform_home)
    from core.platform.state import get_platform_home

    return Path(get_platform_home())


def auto_send_enabled(platform_home: Optional[Path] = None) -> bool:
    """無人の実送信が許可されているか（既定 False＝安全側）。"""
    path = _config_path(_resolve_home(platform_home))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("auto_send_enabled", False)) if isinstance(data, dict) else False
    except (OSError, ValueError):
        return False


def set_auto_send_enabled(value: bool, *, platform_home: Optional[Path] = None) -> bool:
    """無人実送信フラグを設定して永続化する（atomic）。設定後の値を返す。"""
    home = _resolve_home(platform_home)
    path = _config_path(home)
    data = {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            data = existing
    except (OSError, ValueError):
        pass
    data["auto_send_enabled"] = bool(value)
    try:
        home.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:  # pragma: no cover
        logger.warning("failed to persist publish_config.json: %s", exc)
    return bool(value)
