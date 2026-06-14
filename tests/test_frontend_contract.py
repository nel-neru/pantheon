"""フロント↔バックの契約テスト（C042 / 見せかけUI=0 の機械的保証）。

2 段構え:
  1. test_frontend_critical_routes_exist — 主要（破壊/外部送信/承認系）フローの
     {method, path} を読みやすい明示リストで保証。
  2. test_no_frontend_api_call_hits_missing_route — web/frontend の **全** ``api()``
     呼び出しを静的走査し、その {method, 正規化パス} が実在の FastAPI ルートに必ず
     対応することを保証（存在しないエンドポイントを叩く「見せかけUI」を 0 に保つ）。

パスはテンプレートを正規化（``{param}`` / ``${expr}`` → ``{}``）し、セグメント単位で
unify（``{}`` は両側ワイルドカード・末尾 glue の ``{}`` はクエリとして吸収）して比較する。
"""

from __future__ import annotations

import re
from pathlib import Path

from web import server

FRONTEND_SRC = Path(__file__).resolve().parent.parent / "web" / "frontend" / "src"

# api(...) 呼び出しの method + path リテラル（バッククォート/シングル/ダブル）。
_CALL_RE = re.compile(
    r"\bapi\s*(?:<[^>]*>)?\(\s*['\"](GET|POST|PUT|DELETE|PATCH)['\"]\s*,\s*"
    r"(?:`([^`]*)`|'([^']*)'|\"([^\"]*)\")",
    re.DOTALL,
)
# api('METHOD', <非リテラル>  — 動的パス変数（静的検証不能）。0 であるべき。
_DYNAMIC_RE = re.compile(
    r"\bapi\s*(?:<[^>]*>)?\(\s*['\"](?:GET|POST|PUT|DELETE|PATCH)['\"]\s*,\s*([A-Za-z_$])",
)


def _norm(path: str) -> str:
    path = path.split("?")[0]
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    return path


def _segs(path: str) -> list[str]:
    path = re.sub(r"(?<=[^/]){}$", "", path)  # 末尾 glue の {}（=クエリ）を吸収
    return [s for s in path.split("/") if s != ""]


def _unify(fp: str, br: str) -> bool:
    a, b = _segs(fp), _segs(br)
    if len(a) != len(b):
        return False
    return all(x == y or x == "{}" or y == "{}" for x, y in zip(a, b))


def _registered() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in getattr(server.app, "routes", []):
        rp = getattr(route, "path", None)
        if not rp:
            continue
        norm = re.sub(r"\{[^}]+\}", "{}", rp)
        methods = getattr(route, "methods", None)
        if methods:
            for m in methods:
                out.add((m.upper(), norm))
        else:
            out.add(("WS", norm))
    return out


def _frontend_calls() -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """(method, norm_path, file) のリテラル呼び出し一覧 と (file, line) の動的呼び出し一覧。"""
    literal: list[tuple[str, str, str]] = []
    dynamic: list[tuple[str, str]] = []
    for path in FRONTEND_SRC.rglob("*.ts*"):
        parts = set(path.parts)
        if "__tests__" in parts or "test" in parts:
            continue
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(FRONTEND_SRC).as_posix()
        for m in _CALL_RE.finditer(src):
            method = m.group(1)
            raw = m.group(2) or m.group(3) or m.group(4) or ""
            literal.append((method, _norm(raw), rel))
        for dm in _DYNAMIC_RE.finditer(src):
            if dm.group(1) not in "'\"`":
                dynamic.append((rel, dm.group(1)))
    return literal, dynamic


CRITICAL_ROUTES = [
    ("GET", "/api/inbox"),
    ("GET", "/api/platform/status"),
    ("GET", "/api/organizations"),
    ("POST", "/api/publish-jobs/{}/run"),
    ("POST", "/api/publish-jobs/{}/confirm"),
    ("DELETE", "/api/publish-jobs/{}"),
    ("POST", "/api/human-tasks/{}/complete"),
    ("POST", "/api/handoffs/{}/approve"),
    ("POST", "/api/handoffs/{}/reject"),
    ("POST", "/api/proposals/{}/{}/approve"),
    ("POST", "/api/proposals/{}/{}/reject"),
    ("POST", "/api/proposals/{}/batch"),
    ("DELETE", "/api/organizations/{}"),
    ("POST", "/api/organizations/{}/migrate-to-workspace"),
    ("POST", "/api/organizations/{}/divisions"),
    ("GET", "/api/notifications"),
    ("GET", "/api/notifications/unread-count"),
    ("POST", "/api/notifications/read-all"),
    ("POST", "/api/notifications/{}/read"),
    ("POST", "/api/init"),
]


def test_frontend_critical_routes_exist() -> None:
    """主要ルートがすべて FastAPI に登録されていること。"""
    registered = _registered()
    missing = [r for r in CRITICAL_ROUTES if r not in registered]
    assert not missing, "主要ルートが見つかりません（契約ドリフト）: " + ", ".join(
        f"{m} {p}" for m, p in missing
    )


def test_no_frontend_api_call_hits_missing_route() -> None:
    """フロントの全 api() 呼び出しが実在ルートに対応すること（見せかけUI=0）。"""
    registered = _registered()
    literal, dynamic = _frontend_calls()
    assert literal, "フロントの api() 呼び出しが検出できませんでした（走査パスを確認）"

    missing = sorted(
        {
            (m, p)
            for (m, p, _f) in literal
            if not any(rm == m and _unify(p, rp) for rm, rp in registered)
        }
    )
    assert not missing, (
        "実ルートに対応しないフロント api() 呼び出し（見せかけ/デッド）: "
        + ", ".join(f"{m} {p}" for m, p in missing)
    )

    # 静的検証できない動的パス変数は 0（増えたら手動契約確認が必要）。
    assert not dynamic, "動的パスの api() 呼び出し（静的契約検証不能）: " + ", ".join(
        f"{f}:{seg}" for f, seg in dynamic
    )
