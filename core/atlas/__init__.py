"""
core.atlas — Repository Atlas

大規模化した Pantheon リポジトリを人間が俯瞰できるよう、コードベースを
静的・実行時イントロスペクションして構造モデル（CLI コマンド木 / FastAPI ルート /
フロントエンドページ / モジュール依存グラフ / サブシステム在庫 / 使用フローカタログ）を
生成する。Web の ``/api/atlas`` と CLI の ``pantheon atlas`` から利用される。
"""

from __future__ import annotations

from core.atlas.introspect import build_atlas
from core.atlas.proposal_generator import build_atlas_proposals, generate_atlas_proposals

__all__ = ["build_atlas", "build_atlas_proposals", "generate_atlas_proposals"]
