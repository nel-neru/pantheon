# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Pantheon を onedir 形式の単一実行体 (Pantheon.exe) にまとめる。

ビルド手順（リポジトリルートから）:
    1. web/frontend で `npm run build`（→ web/dist を生成）
    2. `.venv/Scripts/python.exe -m PyInstaller packaging/pantheon.spec --noconfirm`
    出力: dist/Pantheon/Pantheon.exe + dist/Pantheon/_internal/...

ポイント:
  - CLI と GUI は同一 exe。引数なし起動で GUI（main.py の main() を参照）。
  - 生成は外部の `claude` CLI 依存（同梱不可）。GUI/CLI 本体のみ同梱で完結する。
  - commands.* は実行時に動的 import されるため collect_submodules で確実に同梱。
  - Atlas の静的解析が exe 下でも動くよう、ソースツリーを datas として同梱する
    （core.paths.resource_root() が sys._MEIPASS を返す）。
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))


def _src(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


# --- 同梱データ（読み取り専用リソース + Atlas 用ソースツリー） --------------- #
_raw_datas = [
    # 人間用可視化サイト（ビルド済み SPA）と静的フォールバック
    (_src("web", "dist"), os.path.join("web", "dist")),
    (_src("web", "static"), os.path.join("web", "static")),
    # YAML テンプレート・スキル・ナレッジ
    (_src("config"), "config"),
    (_src("skills"), "skills"),
    (_src("knowledge"), "knowledge"),
    # Atlas の AST 静的解析・フロントエンド検出が参照するソースツリー
    (_src("main.py"), "."),
    (_src("commands"), "commands"),
    (_src("core"), "core"),
    (_src("agents"), "agents"),
    (_src("github_integration"), "github_integration"),
    (_src("web", "server.py"), "web"),
    (_src("web", "__init__.py"), "web"),
    (_src("web", "frontend", "src"), os.path.join("web", "frontend", "src")),
]
datas = [(s, d) for (s, d) in _raw_datas if os.path.exists(s)]

binaries = []
hiddenimports = []

# --- 動的 import されるパッケージを確実に同梱 ------------------------------ #
for pkg in ("commands", "agents", "core", "github_integration", "web", "pydantic"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

# --- サーバ/オーケストレーション系: data も含めて丸ごと収集 ----------------- #
for pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "langgraph",
    "langgraph_checkpoint_sqlite",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# uvicorn は実行時にプロトコル実装を文字列から動的解決するため明示しておく
hiddenimports += [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "websockets",
    "websockets.legacy",
    "wsproto",
    "git",
    "github",
    "yaml",
    "dotenv",
]

hiddenimports = sorted(set(hiddenimports))

block_cipher = None

a = Analysis(
    [_src("main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "ruff", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pantheon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # サーバログ表示 + CLI 兼用のためコンソール付き
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Pantheon",
)
