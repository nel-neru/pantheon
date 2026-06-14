"""フロント↔バックの契約テスト（C042）。

web/frontend が依存する主要（破壊的/外部送信/中核）フローの {method, path} が、
実際に FastAPI に登録されているルートと一致することを保証する。全テストが api を全
モックしているとフロントの叩く実ルートが消えても気づけないため、その盲点を塞ぐ。

パスはテンプレートを正規化（``{param}`` → ``{}``）して比較する。
"""

from __future__ import annotations

import re

from web import server

# フロントが実際に叩く主要エンドポイント（method, 正規化パス）。
# 破壊的/外部送信/承認系（誤って消すと「見せかけUI」になる）を中心に列挙する。
CRITICAL_ROUTES = [
    ("GET", "/api/inbox"),
    ("GET", "/api/platform/status"),
    ("GET", "/api/organizations"),
    # 外部公開・投稿ジョブ（取り消し不能の外部送信）
    ("POST", "/api/publish-jobs/{}/run"),
    ("POST", "/api/publish-jobs/{}/confirm"),
    ("DELETE", "/api/publish-jobs/{}"),
    # 人間タスク完了
    ("POST", "/api/human-tasks/{}/complete"),
    # 引き渡し承認/却下
    ("POST", "/api/handoffs/{}/approve"),
    ("POST", "/api/handoffs/{}/reject"),
    # 提案の承認/却下/一括
    ("POST", "/api/proposals/{}/{}/approve"),
    ("POST", "/api/proposals/{}/{}/reject"),
    ("POST", "/api/proposals/{}/batch"),
    # 組織の破壊/移行・事業部追加
    ("DELETE", "/api/organizations/{}"),
    ("POST", "/api/organizations/{}/migrate-to-workspace"),
    ("POST", "/api/organizations/{}/divisions"),
    # 通知（ベル刷新 C007）
    ("GET", "/api/notifications"),
    ("GET", "/api/notifications/unread-count"),
    ("POST", "/api/notifications/read-all"),
    ("POST", "/api/notifications/{}/read"),
    # プラットフォーム初期化
    ("POST", "/api/init"),
]


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _registered_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in getattr(server.app, "routes", []):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        norm = _normalize(path)
        for method in methods:
            routes.add((method.upper(), norm))
    return routes


def test_frontend_critical_routes_exist() -> None:
    """フロントが依存する主要ルートがすべて FastAPI に登録されていること。"""
    registered = _registered_routes()
    missing = [route for route in CRITICAL_ROUTES if route not in registered]
    assert not missing, "フロントが叩く実ルートが見つかりません（契約ドリフト）: " + ", ".join(
        f"{m} {p}" for m, p in missing
    )
