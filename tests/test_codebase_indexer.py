from __future__ import annotations

from core.intelligence.codebase_indexer import CodebaseIndexer


def _write(repo, rel, body):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_build_is_incremental_and_prunes_deleted_files(tmp_path):
    _write(tmp_path, "a.py", "class A:\n    pass\n")
    b = _write(tmp_path, "pkg/b.py", "def f():\n    return 1\n")

    idx = CodebaseIndexer(tmp_path)
    first = idx.build()
    assert "a.py" in first["files"]
    assert "pkg/b.py" in first["files"]

    # Nothing changed -> incremental build re-indexes nothing.
    second = idx.build()
    assert second["updated_files"] == 0

    # Deleting a source file prunes its index entry on the next build.
    b.unlink()
    third = idx.build()
    assert "pkg/b.py" not in third["files"]
    assert "a.py" in third["files"]
