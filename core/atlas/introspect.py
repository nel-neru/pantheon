"""
Repository introspection for the Atlas visualization.

すべて読み取り専用。生成系（claude CLI）には一切依存しないので、API キーや
ネットワークなしで動作する。実行時イントロスペクション（argparse パーサ / FastAPI app）と
静的解析（AST 依存グラフ / フロントエンド正規表現）を組み合わせる。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import resource_path, resource_root

# Atlas は同梱されたソースツリーを静的解析する。exe 化時は sys._MEIPASS 配下に
# 展開されたソース／データを参照する（packaging で source tree を datas に同梱）。
PROJECT_ROOT = resource_root()
_DATA_DIR = resource_path("core", "atlas", "data")

# サブシステム分類: ラベル -> そのサブシステムに属するトップレベル相対パスの接頭辞
SUBSYSTEMS: dict[str, dict[str, Any]] = {
    "cli": {
        "label": "CLI",
        "paths": ["main.py", "commands"],
        "purpose": "pantheon CLI のエントリと各サブコマンド実装",
    },
    "web-api": {
        "label": "Web API",
        "paths": ["web/server.py", "web/__init__.py"],
        "purpose": "FastAPI ベースのプラットフォーム REST/WebSocket API",
    },
    "frontend": {
        "label": "Frontend",
        "paths": ["web/frontend/src"],
        "purpose": "React 19 / Vite / Tailwind の Web GUI",
    },
    "agents": {
        "label": "Agents",
        "paths": ["agents"],
        "purpose": "実行可能エージェント（レビュー/改善適用/探索/オーケストレータ等）",
    },
    "orchestration": {
        "label": "Orchestration",
        "paths": ["core/orchestration"],
        "purpose": "Pre-Task 分析・ルーティング・実行パターン学習",
    },
    "goals": {
        "label": "Goals",
        "paths": ["core/goals"],
        "purpose": "抽象ゴール→計画→実行→検証パイプライン",
    },
    "intelligence": {
        "label": "Intelligence",
        "paths": ["core/intelligence", "core/knowledge"],
        "purpose": "能力レジストリ・ギャップ分析・スキルエンジン・索引",
    },
    "quality": {
        "label": "Quality / Policy",
        "paths": ["core/quality", "core/policy", "core/metrics"],
        "purpose": "自己改善ループ・HITL 承認ポリシー・組織健康度指標",
    },
    "runtime": {
        "label": "Runtime",
        "paths": ["core/runtime"],
        "purpose": "claude CLI 実行バックエンドと wmux/cmux マルチプレクサ",
    },
    "state": {
        "label": "State / Models",
        "paths": ["core/platform", "core/state", "core/models", "core/bootstrap.py"],
        "purpose": "Organization データモデルとグローバル/リポジトリ状態の永続化",
    },
    "core-misc": {
        "label": "Core (misc)",
        "paths": [
            "core/hierarchy",
            "core/profile",
            "core/execution",
            "core/events",
            "core/security",
            "core/monitoring",
            "core/loaders",
            "core/ui",
            "core/llm",
        ],
        "purpose": "階層/プロファイル/実行/イベント/UI 補助など中核補助モジュール",
    },
    "atlas": {
        "label": "Atlas",
        "paths": ["core/atlas"],
        "purpose": "リポジトリ俯瞰のための構造イントロスペクション（本機能）",
    },
    "integrations": {
        "label": "Integrations",
        "paths": ["github_integration", "config", "skills"],
        "purpose": "GitHub PR 連携・YAML テンプレート/ペルソナ・Pantheon スキル定義",
    },
    "tests": {"label": "Tests", "paths": ["tests"], "purpose": "pytest バックエンドテスト群"},
}

_TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".md"}
_SKIP_DIR_PARTS = {
    "__pycache__",
    "node_modules",
    ".venv",
    "dist",
    ".git",
    "egg-info",
    ".pytest_cache",
    ".ruff_cache",
}


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_PARTS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES:
            yield path


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except OSError:
        return 0


# --------------------------------------------------------------------------- CLI


def _subparser_help_map(action: argparse._SubParsersAction) -> dict[str, str]:
    # argparse internal (_choices_actions) — best-effort, tolerate version drift.
    helps: dict[str, str] = {}
    try:
        for pseudo in getattr(action, "_choices_actions", []):
            helps[pseudo.dest] = pseudo.help or ""
    except Exception:  # noqa: BLE001
        return {}
    return helps


def _collect_args(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    # parser._actions is a private argparse attr — guard against drift.
    args: list[dict[str, Any]] = []
    try:
        actions = parser._actions
    except Exception:  # noqa: BLE001
        return []
    for act in actions:
        try:
            if isinstance(act, (argparse._SubParsersAction, argparse._HelpAction)):
                continue
            if not act.option_strings and act.dest == "help":
                continue
            args.append(
                {
                    "name": ", ".join(act.option_strings) if act.option_strings else act.dest,
                    "required": bool(getattr(act, "required", False)) or not act.option_strings,
                    "help": act.help or "",
                }
            )
        except Exception:  # noqa: BLE001 - 1 個の壊れた action で全体を落とさない
            continue
    return args


def _walk_cli(parser: argparse.ArgumentParser, prefix: str, out: list[dict[str, Any]]) -> None:
    # _actions / _SubParsersAction / _defaults はすべて argparse の私的 API。
    # バージョン差異で壊れても 1 サブパーサ分だけスキップし、木全体は壊さない。
    try:
        actions = parser._actions
    except Exception:  # noqa: BLE001
        return
    for act in actions:
        if not isinstance(act, argparse._SubParsersAction):
            continue
        helps = _subparser_help_map(act)
        for name, sub in act.choices.items():
            try:
                full = f"{prefix} {name}".strip()
                handler = (getattr(sub, "_defaults", {}) or {}).get("handler_name")
                # 末端（handler を持つ）コマンドのみ記録し、グループはたどる
                has_sub = any(isinstance(a, argparse._SubParsersAction) for a in sub._actions)
                if handler or not has_sub:
                    out.append(
                        {
                            "command": f"pantheon {full}",
                            "group": full.split(" ")[0],
                            "handler": handler,
                            "help": helps.get(name, ""),
                            "args": _collect_args(sub),
                        }
                    )
                _walk_cli(sub, full, out)
            except Exception:  # noqa: BLE001 - 壊れた sub-parser はスキップ
                continue


def introspect_cli() -> list[dict[str, Any]]:
    try:
        from commands import build_parser

        parser = build_parser()
    except Exception as exc:  # pragma: no cover - defensive
        return [
            {
                "command": "(unavailable)",
                "error": str(exc),
                "group": "",
                "handler": None,
                "help": "",
                "args": [],
            }
        ]

    out: list[dict[str, Any]] = []
    _walk_cli(parser, "", out)
    out.sort(key=lambda c: c["command"])
    return out


# --------------------------------------------------------------------------- API


def introspect_api() -> list[dict[str, Any]]:
    try:
        from web.server import app
    except Exception as exc:  # pragma: no cover - defensive
        return [
            {"path": "(unavailable)", "methods": [], "name": str(exc), "kind": "error", "tags": []}
        ]

    routes: list[dict[str, Any]] = []
    # Starlette/FastAPI のルート属性は getattr で防御。壊れたルート 1 件で全体を落とさない。
    for route in getattr(app, "routes", []):
        try:
            path = getattr(route, "path", None)
            if not path:
                continue
            methods = sorted(
                m for m in (getattr(route, "methods", None) or []) if m not in {"HEAD", "OPTIONS"}
            )
            is_ws = path.startswith("/ws") or route.__class__.__name__ == "WebSocketRoute"
            kind = "websocket" if is_ws else "rest"
            if not (path.startswith("/api") or path.startswith("/ws") or path == "/"):
                continue
            routes.append(
                {
                    "path": path,
                    "methods": methods or (["WS"] if is_ws else []),
                    "name": getattr(route, "name", "") or "",
                    "kind": kind,
                    "tags": list(getattr(route, "tags", []) or []),
                }
            )
        except Exception:  # noqa: BLE001 - 壊れたルートはスキップ
            continue
    routes.sort(key=lambda r: (r["kind"] != "rest", r["path"]))
    return routes


# ----------------------------------------------------------------------- Frontend

_ROUTE_RE = re.compile(r"<Route\s+path=\"([^\"]+)\"\s+element=\{<(\w+)")
_NAV_RE = re.compile(r"\{\s*to:\s*'([^']+)',\s*label:\s*'([^']+)'")


def introspect_frontend() -> dict[str, Any]:
    src = PROJECT_ROOT / "web" / "frontend" / "src"
    app_tsx = src / "App.tsx"
    nav: list[dict[str, str]] = []
    routes: list[dict[str, str]] = []
    if app_tsx.exists():
        text = app_tsx.read_text(encoding="utf-8", errors="ignore")
        routes = [{"path": p, "element": e} for p, e in _ROUTE_RE.findall(text)]
        nav = [{"to": t, "label": lbl} for t, lbl in _NAV_RE.findall(text)]

    pages_dir = src / "pages"
    pages: list[dict[str, Any]] = []
    if pages_dir.exists():
        for page in sorted(pages_dir.glob("*.tsx")):
            pages.append(
                {
                    "name": page.stem,
                    "path": str(page.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "lines": _count_lines(page),
                }
            )
    return {"nav": nav, "routes": routes, "pages": pages}


# ------------------------------------------------------------------- Module graph


def _subsystem_of(rel_path: str) -> str:
    norm = rel_path.replace("\\", "/")
    best_label = "core-misc"
    best_len = -1
    for key, meta in SUBSYSTEMS.items():
        for prefix in meta["paths"]:
            pfx = prefix.replace("\\", "/")
            if norm == pfx or norm.startswith(pfx + "/") or norm.startswith(pfx):
                if len(pfx) > best_len:
                    best_len = len(pfx)
                    best_label = key
    return best_label


_GRAPH_ROOTS = ("core", "agents", "commands", "github_integration")
_GRAPH_FILES = ("main.py", "web/server.py")


def _project_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _GRAPH_ROOTS:
        base = PROJECT_ROOT / root
        if base.is_dir():
            files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    for rel in _GRAPH_FILES:
        fpath = PROJECT_ROOT / rel
        if fpath.is_file():
            files.append(fpath)
    return files


def _dotted_name(rel: str) -> str:
    parts = rel[:-3].split("/")  # strip .py
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_module_graph() -> dict[str, Any]:
    """プロジェクト内 .py の import を AST 解析し、ファイル依存グラフと
    サブシステム集約グラフを返す（.venv / node_modules は対象外）。"""
    import ast

    py_files = _project_py_files()
    module_map: dict[str, str] = {}
    rels: list[str] = []
    for path in py_files:
        rel = path.resolve().relative_to(PROJECT_ROOT).as_posix()
        rels.append(rel)
        module_map[_dotted_name(rel)] = rel

    def _resolve(dotted: str) -> str | None:
        # 完全一致、なければ末尾を削って親パッケージ __init__ を探す
        if dotted in module_map:
            return module_map[dotted]
        parts = dotted.split(".")
        while parts:
            parts = parts[:-1]
            candidate = ".".join(parts)
            if candidate in module_map:
                return module_map[candidate]
        return None

    file_graph: dict[str, list[str]] = {}
    for path, rel in zip(py_files, rels):
        deps: set[str] = set()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError):
            file_graph[rel] = []
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _resolve(alias.name)
                    if resolved:
                        deps.add(resolved)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 相対 import は同一パッケージ内（同一サブシステム）なので無視
                    continue
                base = node.module or ""
                if not base:
                    continue
                matched = False
                for alias in node.names:
                    resolved = _resolve(f"{base}.{alias.name}")
                    if resolved:
                        deps.add(resolved)
                        matched = True
                if not matched:
                    resolved = _resolve(base)
                    if resolved:
                        deps.add(resolved)
        deps.discard(rel)
        file_graph[rel] = sorted(deps)

    # サブシステム単位に集約したエッジ（重み付き）
    edge_weights: dict[tuple[str, str], int] = defaultdict(int)
    node_files: dict[str, int] = defaultdict(int)
    for src_rel, deps in file_graph.items():
        src_sub = _subsystem_of(src_rel)
        node_files[src_sub] += 1
        for dep in deps:
            dep_rel = dep.replace("\\", "/")
            if not (dep_rel.endswith(".py")):
                continue
            dst_sub = _subsystem_of(dep_rel)
            if dst_sub != src_sub:
                edge_weights[(src_sub, dst_sub)] += 1

    nodes = [
        {"id": key, "label": SUBSYSTEMS[key]["label"], "files": node_files.get(key, 0)}
        for key in SUBSYSTEMS
        if node_files.get(key, 0) > 0
    ]
    edges = [
        {"source": s, "target": t, "weight": w}
        for (s, t), w in sorted(edge_weights.items(), key=lambda kv: -kv[1])
    ]
    return {"nodes": nodes, "edges": edges, "file_count": len(file_graph)}


# --------------------------------------------------------------- Subsystem inventory


def build_inventory() -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for key, meta in SUBSYSTEMS.items():
        files = 0
        lines = 0
        for prefix in meta["paths"]:
            target = PROJECT_ROOT / prefix
            if target.is_file():
                files += 1
                lines += _count_lines(target)
            elif target.is_dir():
                for path in _iter_source_files(target):
                    files += 1
                    lines += _count_lines(path)
        inventory.append(
            {
                "id": key,
                "label": meta["label"],
                "purpose": meta["purpose"],
                "paths": meta["paths"],
                "files": files,
                "lines": lines,
            }
        )
    return inventory


# ------------------------------------------------------------------ Flows (curated)


def load_flows() -> list[dict[str, Any]]:
    flows_path = _DATA_DIR / "flows.json"
    if not flows_path.exists():
        return []
    try:
        data = json.loads(flows_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("flows", data) if isinstance(data, dict) else data


# --------------------------------------------------------------------- Aggregate


def build_atlas() -> dict[str, Any]:
    cli = introspect_cli()
    api = introspect_api()
    frontend = introspect_frontend()
    graph = build_module_graph()
    inventory = build_inventory()
    flows = load_flows()

    overview = {
        "flows": len(flows),
        "cli_commands": len([c for c in cli if c.get("handler")]),
        "api_routes": len([r for r in api if r["kind"] == "rest"]),
        "websockets": len([r for r in api if r["kind"] == "websocket"]),
        "pages": len(frontend["pages"]),
        "subsystems": len(inventory),
        "modules": graph["file_count"],
        "total_lines": sum(s["lines"] for s in inventory),
        "total_files": sum(s["files"] for s in inventory),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overview": overview,
        "flows": flows,
        "cli": cli,
        "api": api,
        "frontend": frontend,
        "graph": graph,
        "subsystems": inventory,
    }
