"""Vault 全 .md を node/edge グラフ化する（Pantheon GUI のグラフビュー用）。

``build_link_index``（links.py）を再利用し、管理ノートを node に、``[[wikilink]]`` を edge にする。
未解決リンク（対応ノートが無い ``[[org:Foo]]`` / ``[[file:...]]`` 等）は leaf node として残す。

出力 shape は Atlas（``core/atlas.build_atlas``）の graph（``nodes:{id,label,files}`` /
``edges:{source,target,weight}``）と互換にし、フロントの SVG レンダラ（AtlasPage）を流用できる
（``group`` で pantheon_type 別に色分け）。Obsidian 自身もこの ``[[...]]`` から native にグラフを
描くので、このグラフは Pantheon GUI 用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.vault.links import build_link_index


def build_vault_graph(vault_dir: Path | str) -> Dict[str, Any]:
    """Vault のノード/エッジ/バックリンクグラフを構築する。"""
    index = build_link_index(vault_dir)

    nodes: List[Dict[str, Any]] = []
    node_ids: set[str] = set()
    for ref in index.notes:
        nodes.append(
            {
                "id": ref.node_id,
                "label": ref.title,
                "group": ref.pantheon_type,
                "path": ref.path,
                "files": 1,
            }
        )
        node_ids.add(ref.node_id)

    edges: List[Dict[str, Any]] = []
    for ref in index.notes:
        for link in ref.wikilinks:
            target = link.node_id
            if target not in node_ids:
                # 未解決リンク（対応ノート無し）は leaf node として残す（外部/コード参照）。
                nodes.append(
                    {
                        "id": target,
                        "label": link.target,
                        "group": link.type or "external",
                        "path": "",
                        "files": 0,
                    }
                )
                node_ids.add(target)
            edges.append({"source": ref.node_id, "target": target, "weight": 1})

    resolved_links = sum(1 for ref in index.notes for link in ref.wikilinks if link.resolved)
    counts = {
        "notes": len(index.notes),
        "nodes": len(nodes),
        "edges": len(edges),
        "resolved_links": resolved_links,
        "groups": sorted({str(node["group"]) for node in nodes}),
    }
    return {
        "nodes": nodes,
        "edges": edges,
        "backlinks": index.backlinks,
        "counts": counts,
    }


def to_dot(graph: Dict[str, Any]) -> str:
    """グラフを Graphviz DOT 文字列に変換する（CLI ``vault graph --format dot`` 用）。"""

    def esc(text: Any) -> str:
        return str(text).replace("\\", "\\\\").replace('"', '\\"')

    lines = ["digraph vault {", "  rankdir=LR;"]
    for node in graph["nodes"]:
        lines.append(f'  "{esc(node["id"])}" [label="{esc(node["label"])}"];')
    for edge in graph["edges"]:
        lines.append(f'  "{esc(edge["source"])}" -> "{esc(edge["target"])}";')
    lines.append("}")
    return "\n".join(lines)
