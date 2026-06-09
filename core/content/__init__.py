"""コンテンツ定期ジョブ（投稿生成）サブシステム。

ワークスペース repo 内に「投稿（content_asset 提案）」を定期生成する。外部公開は一切しない
（PolicyEngine が content_asset を常に human_required に強制するため、生成物は人間承認待ちで残る）。
"""

from __future__ import annotations
