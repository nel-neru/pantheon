"""PyInstaller spec 健全性チェック（P3.1 ビルド硬化）。

フルビルドは重く CI 不向きなため、**最頻の配布事故**＝「リポジトリに足した読み取り専用
リソースを ``packaging/pantheon.spec`` の ``datas`` に入れ忘れ、exe 実行時に欠落する」を
静的に検出する。具体的には:

1. spec が Python として compile できる（構文崩れの早期検知）。
2. 実行時に ``core.paths.resource_path`` で参照される重要リソース（config/skills/knowledge と
   Atlas 用ソースツリー）が **spec の datas に列挙され、かつ実体がリポジトリに存在する**。
3. ランタイムが文字列から動的解決する uvicorn/websocket 系の hiddenimports が宣言されている。
4. フロントのビルド出力（web/dist / web/atelier/dist）は任意（未ビルドは警告のみ）。

LLM 非依存・決定論。``main()`` は致命的欠落があれば終了コード 1。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "packaging" / "pantheon.spec"

# spec の datas に必ず列挙され、かつ実体が存在すべき重要リソース（実行時に resource_path 経由で読む）。
CRITICAL_DATA_TOKENS: Tuple[str, ...] = (
    "config",
    "skills",
    "knowledge",
    "main.py",
    "commands",
    "core",
    "agents",
    "server.py",
    "scripts",  # watchdog の .ps1 等を実行時に resource_path("scripts", ...) で読む
)

# 実体が存在すべきパス（datas トークンに対応するリポジトリ内リソース）。
CRITICAL_PATHS: Tuple[str, ...] = (
    "config",
    "skills",
    "knowledge",
    "main.py",
    "commands",
    "core",
    "agents",
    "web/server.py",
    "scripts",
)

# 実行時に文字列から動的解決され、宣言漏れだと exe で落ちる hiddenimports。
REQUIRED_HIDDENIMPORTS: Tuple[str, ...] = (
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "yaml",
)

# 任意（未ビルドは警告）。
OPTIONAL_PATHS: Tuple[str, ...] = (
    "web/dist",
    "web/atelier/dist",
)


def check_build_spec(repo_root: Path = REPO_ROOT) -> Tuple[List[str], List[str]]:
    """spec を検査し ``(errors, warnings)`` を返す（純粋・副作用なし）。"""
    errors: List[str] = []
    warnings: List[str] = []

    spec_path = repo_root / "packaging" / "pantheon.spec"
    if not spec_path.exists():
        return [f"spec が見つかりません: {spec_path}"], warnings

    spec_text = spec_path.read_text(encoding="utf-8")

    # 1. 構文チェック（PyInstaller のグローバルは無いが compile は通る）。
    try:
        compile(spec_text, str(spec_path), "exec")
    except SyntaxError as exc:  # pragma: no cover - 構文崩れ時のみ
        errors.append(f"spec の構文エラー: {exc}")
        return errors, warnings

    # 2. 重要リソースが datas に列挙されているか（トークンの出現で判定）。
    for token in CRITICAL_DATA_TOKENS:
        if token not in spec_text:
            errors.append(f"datas に重要リソースの記載がありません: '{token}'")

    # 2b. 重要リソースの実体が存在するか。
    for rel in CRITICAL_PATHS:
        if not (repo_root / rel).exists():
            errors.append(f"重要リソースの実体がありません: {rel}")

    # 3. 動的解決 hiddenimports の宣言。
    for imp in REQUIRED_HIDDENIMPORTS:
        if imp not in spec_text:
            errors.append(f"hiddenimports に必須項目がありません: '{imp}'")

    # 4. フロント成果物（任意）。
    for rel in OPTIONAL_PATHS:
        if not (repo_root / rel).exists():
            warnings.append(f"未ビルド（任意）: {rel} — 配布前に npm run build を推奨")

    # 5. 実行時リソース解決の sanity（resource_path が config を引けるか）。
    try:
        sys.path.insert(0, str(repo_root))
        from core.paths import resource_path

        if not resource_path("config", "model_tiers.yaml").exists():
            errors.append("resource_path('config','model_tiers.yaml') が解決できません")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"resource_path の検証をスキップ（import 失敗）: {exc}")

    return errors, warnings


def main() -> int:
    errors, warnings = check_build_spec()
    print(f"[check-build-spec] spec: {SPEC_PATH}")
    for w in warnings:
        print(f"  [warn] {w}")
    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        print(f"[check-build-spec] 失敗: {len(errors)} 件の致命的問題")
        return 1
    print("[check-build-spec] OK: spec は必要リソースをすべて同梱対象にしています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
