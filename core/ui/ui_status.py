"""UI/UX 状態監視サブシステム — Web GUI 全ページの「実際に動くか」を宣言＋実測する。

このモジュールは Pantheon の React フロントエンドが持つ**全ページ**を、実ネットワーク捕捉に
基づく正確な宣言マップ（``PAGE_REGISTRY``）として保持する。各ページがマウント時にパラメータ
なしで叩く GET API を実際に HTTP で probe し、ステータス/レイテンシ/エラーを記録して、
ページ単位（ok / degraded / error）と全体集計を持つレポートを生成する。

設計上の正直さ（facade 禁止）:
- probe 対象は **マウント時ロードの GET（パラメータ不要）API のみ**。param 付き・mutating
  （POST/PUT/DELETE）なルートは ``apis`` に入れず、``controls`` に**文字列**として宣言する
  （勝手に副作用のある呼び出しはしない）。
- ``static: true`` のページは API を持たない（クライアント完結）。空の ``apis`` で status="ok"。
- 例外（接続不可など）は握り潰さず ``ok=False`` ＋ ``error`` 文字列＋ ``status_code=0`` として
  記録する。全 green の捏造はしない。

レポートは ``write_ui_status`` で ``~/.pantheon/ui_status.json`` へ原子的に書き出し、
GUI の ``/ui-status`` ページと CLI ``pantheon ui-status`` から共有される。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.persistence import atomic_write_text
from core.platform.state import get_platform_home

# ---------------------------------------------------------------------------
# PAGE_REGISTRY — 実ネットワーク捕捉に基づく宣言マップ
#
# 各要素 dict:
#   route:    フロントエンドのルート（"/dashboard" 等）
#   label:    人間可読のページ名
#   group:    ナビゲーション上のグループ
#   apis:     [{method, path}] — マウント時にパラメータ不要で叩く GET のみ（= probe 対象）
#   controls: [str] — ページが持つボタン/フォーム/param 付き or mutating API（文字列で宣言）
#   static:   true のとき API を持たないクライアント完結ページ
# ---------------------------------------------------------------------------
PAGE_REGISTRY: list[dict[str, Any]] = [
    {
        "route": "/dashboard",
        "label": "ダッシュボード",
        "group": "はじめに",
        "apis": [
            {"method": "GET", "path": "/api/platform/status"},
            {"method": "GET", "path": "/api/organizations"},
            {"method": "GET", "path": "/api/daemon/status"},
            {"method": "GET", "path": "/api/tasks"},
            {"method": "GET", "path": "/api/execution-history?limit=40"},
            {"method": "GET", "path": "/api/dashboard/orchestra"},
            {"method": "GET", "path": "/api/notifications/unread-count"},
        ],
        "controls": ["更新", "デーモン起動/停止", "初期化", "パスコピー"],
        "static": False,
    },
    {
        "route": "/onboarding",
        "label": "初回セットアップ",
        "group": "はじめに",
        "apis": [
            {"method": "GET", "path": "/api/company-plugin-manifests"},
            {"method": "GET", "path": "/api/organizations"},
        ],
        "controls": ["会社作成(install)", "始める"],
        "static": False,
    },
    {
        "route": "/inbox",
        "label": "承認インボックス",
        "group": "要対応",
        "apis": [
            {"method": "GET", "path": "/api/inbox"},
        ],
        "controls": ["承認/却下/介入/投稿/完了/プレビュー"],
        "static": False,
    },
    {
        "route": "/notifications",
        "label": "通知センター",
        "group": "要対応",
        "apis": [
            {"method": "GET", "path": "/api/notifications"},
            {"method": "GET", "path": "/api/notifications/settings"},
            {"method": "GET", "path": "/api/notifications/unread-count"},
        ],
        "controls": ["既読/全既読/設定保存"],
        "static": False,
    },
    {
        "route": "/human-tasks",
        "label": "あなたのタスク",
        "group": "要対応",
        "apis": [
            {"method": "GET", "path": "/api/human-tasks?status=open"},
        ],
        "controls": ["完了"],
        "static": False,
    },
    {
        "route": "/orgs",
        "label": "組織",
        "group": "組織・エージェント",
        "apis": [
            {"method": "GET", "path": "/api/organizations"},
        ],
        "controls": [
            "新規/編集/削除/詳細",
            "アイコン変更",
            "proposals(param)",
            "migrate",
        ],
        "static": False,
    },
    {
        "route": "/agents",
        "label": "エージェント",
        "group": "組織・エージェント",
        "apis": [
            {"method": "GET", "path": "/api/agents"},
            {"method": "GET", "path": "/api/skills"},
            {"method": "GET", "path": "/api/agents/runtime"},
        ],
        "controls": ["設定モーダル", "orchestration/analyze(param)"],
        "static": False,
    },
    {
        "route": "/goals",
        "label": "ゴール実行",
        "group": "組織・エージェント",
        "apis": [
            {"method": "GET", "path": "/api/goals/history"},
        ],
        "controls": ["実行(SSE /api/goals/stream)", "中止"],
        "static": False,
    },
    {
        "route": "/portfolio",
        "label": "ポートフォリオ司令塔",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/portfolio/overview"},
        ],
        "controls": ["承認インボックス/マーケットプレイス遷移"],
        "static": False,
    },
    {
        "route": "/studio",
        "label": "コンテンツ・スタジオ",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/design-styles"},
            {"method": "GET", "path": "/api/personas"},
        ],
        "controls": ["媒体タブ/コピー/クリア(クライアント)"],
        "static": False,
    },
    {
        "route": "/content",
        "label": "コンテンツ・スケジュール",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/content-jobs"},
            {"method": "GET", "path": "/api/organizations"},
            {"method": "GET", "path": "/api/content-daemon/status"},
            {"method": "GET", "path": "/api/content-daemon/logs?limit=10"},
        ],
        "controls": ["ジョブ追加/今すぐ生成/有効化/削除/ループ開始停止"],
        "static": False,
    },
    {
        "route": "/handoffs",
        "label": "引き渡し",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/handoffs?status=pending"},
        ],
        "controls": ["承認+本文生成/却下/本文のみ生成"],
        "static": False,
    },
    {
        "route": "/revenue",
        "label": "収益ダッシュボード",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/metrics/revenue"},
            {"method": "GET", "path": "/api/metrics/revenue/report"},
            {"method": "GET", "path": "/api/metrics/revenue/intelligence"},
            {"method": "GET", "path": "/api/hq/portfolio"},
            {"method": "GET", "path": "/api/daemons/status"},
            {"method": "GET", "path": "/api/metrics/revenue/integrity"},
            {"method": "GET", "path": "/api/metrics/efficiency"},
        ],
        "controls": ["手動記録/インポート/エクスポート/プラン起票/収益デーモン"],
        "static": False,
    },
    {
        "route": "/businesses",
        "label": "事業",
        "group": "収益化",
        "apis": [
            {"method": "GET", "path": "/api/businesses"},
        ],
        "controls": ["作成/成果/ヘルス/実体化/一時停止/削除"],
        "static": False,
    },
    {
        "route": "/connections",
        "label": "連携設定",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/publishing/connections"},
        ],
        "controls": ["接続(login)/切断"],
        "static": False,
    },
    {
        "route": "/marketplace",
        "label": "マーケットプレイス",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/company-plugin-manifests"},
            {"method": "GET", "path": "/api/division-plugins"},
            {"method": "GET", "path": "/api/organizations"},
            {"method": "GET", "path": "/api/hq/business-proposals"},
        ],
        "controls": ["会社作成/事業部追加/スキャン"],
        "static": False,
    },
    {
        "route": "/atlas",
        "label": "Atlas",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/atlas"},
        ],
        "controls": ["タブ/フィルタ/ズーム(クライアント)"],
        "static": False,
    },
    {
        "route": "/sessions",
        "label": "セッション",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/sessions"},
            {"method": "GET", "path": "/api/sessions/runtime"},
        ],
        "controls": ["停止/ログ表示(param)"],
        "static": False,
    },
    {
        "route": "/board",
        "label": "作業ボード",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/tasks?limit=200"},
            {"method": "GET", "path": "/api/organizations"},
        ],
        "controls": ["新規タスク/キャンセル"],
        "static": False,
    },
    {
        "route": "/data",
        "label": "データ管理",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/goals/history"},
            {"method": "GET", "path": "/api/knowledge/files"},
        ],
        "controls": ["ナレッジCRUD/履歴クリア"],
        "static": False,
    },
    {
        "route": "/usage",
        "label": "使用量",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/usage/summary"},
        ],
        "controls": ["更新"],
        "static": False,
    },
    {
        "route": "/observability",
        "label": "オブザーバビリティ",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/observability/summary"},
        ],
        "controls": ["更新"],
        "static": False,
    },
    {
        "route": "/settings",
        "label": "設定",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/settings"},
            {"method": "GET", "path": "/api/storage/info"},
            {"method": "GET", "path": "/api/sessions/runtime"},
            {"method": "GET", "path": "/api/providers/claude/models"},
        ],
        "controls": ["保存/トークン/モデル選択"],
        "static": False,
    },
    {
        "route": "/proposals",
        "label": "改善提案",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/organizations"},
        ],
        "controls": [
            "org/status/category フィルタ",
            "承認/却下/一括(param org)",
        ],
        "static": False,
    },
    {
        "route": "/help",
        "label": "ヘルプ",
        "group": "システム",
        "apis": [],
        "controls": ["タブ/アコーディオン(クライアント)"],
        "static": True,
    },
    {
        # この監視ページ自身も登録し自己参照する（自分の API も probe 対象）。
        "route": "/ui-status",
        "label": "UI状態監視",
        "group": "システム",
        "apis": [
            {"method": "GET", "path": "/api/ui/status"},
        ],
        "controls": ["再チェック(POST /api/ui/status/refresh)", "自動更新トグル"],
        "static": False,
    },
]


def _probe_api(client: Any, api: dict[str, Any]) -> dict[str, Any]:
    """1 つの GET API を ``client.get`` で実測し、結果 dict を返す。

    ``client`` は ``.get(path) -> resp(.status_code)`` を持つ httpx 互換
    （``httpx.Client`` / ``fastapi.testclient.TestClient``）。例外時は握り潰さず
    ``ok=False`` ＋ ``error=str(e)`` ＋ ``status_code=0`` で正直に記録する。
    """
    method = api.get("method", "GET")
    path = api["path"]
    started = time.perf_counter()
    try:
        resp = client.get(path)
        status_code = int(resp.status_code)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "method": method,
            "path": path,
            "status_code": status_code,
            "ok": 200 <= status_code < 400,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — 接続不可等は捏造せず正直に記録
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "method": method,
            "path": path,
            "status_code": 0,
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(exc),
        }


def _page_status(apis: list[dict[str, Any]], static: bool) -> str:
    """ページの総合ステータスを決める。

    - static（API なし）→ "ok"
    - 全 api ok → "ok"
    - 一部のみ失敗 → "degraded"
    - api ありで全失敗 → "error"
    """
    if static or not apis:
        return "ok"
    ok_count = sum(1 for a in apis if a["ok"])
    if ok_count == len(apis):
        return "ok"
    if ok_count == 0:
        return "error"
    return "degraded"


def build_ui_status(client: Any, registry: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """全ページの宣言マップを実測 probe し、状態レポート dict を生成する。

    ``client`` は ``.get(path) -> resp(.status_code)`` を持つ httpx 互換
    （``httpx.Client`` か ``fastapi.testclient.TestClient``）。各ページの各 api を
    ``client.get`` で叩き、``time.perf_counter`` でレイテンシを計測する。

    戻り値 shape::

        {
          "generated_at": "<ISO8601 UTC>",
          "overall": {pages, ok, degraded, error, total_apis, ok_apis},
          "pages": [
            {route, label, group, status, static, apis:[...], controls:[...]},
            ...
          ],
        }
    """
    reg = registry if registry is not None else PAGE_REGISTRY
    pages: list[dict[str, Any]] = []
    total_apis = 0
    ok_apis = 0
    status_counts = {"ok": 0, "degraded": 0, "error": 0}

    for page in reg:
        static = bool(page.get("static", False))
        probed: list[dict[str, Any]] = []
        for api in page.get("apis", []):
            result = _probe_api(client, api)
            probed.append(result)
            total_apis += 1
            if result["ok"]:
                ok_apis += 1
        status = _page_status(probed, static)
        status_counts[status] = status_counts.get(status, 0) + 1
        pages.append(
            {
                "route": page["route"],
                "label": page["label"],
                "group": page["group"],
                "status": status,
                "static": static,
                "apis": probed,
                "controls": list(page.get("controls", [])),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "pages": len(pages),
            "ok": status_counts["ok"],
            "degraded": status_counts["degraded"],
            "error": status_counts["error"],
            "total_apis": total_apis,
            "ok_apis": ok_apis,
        },
        "pages": pages,
    }


def write_ui_status(report: dict[str, Any], path: Path | str) -> None:
    """``report`` を JSON（``ensure_ascii=False, indent=2``）で原子的に書き出す。"""
    atomic_write_text(path, json.dumps(report, ensure_ascii=False, indent=2))


def default_status_path() -> Path:
    """共有レポートの既定パス（``~/.pantheon/ui_status.json``）。"""
    return get_platform_home() / "ui_status.json"


def load_ui_status(path: Path | str | None = None) -> dict[str, Any] | None:
    """保存済みレポートを読む。無い/壊れている場合は ``None``。"""
    target = Path(path) if path is not None else default_status_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data
