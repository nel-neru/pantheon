from __future__ import annotations

import json
from pathlib import Path

from core.intelligence.codebase_indexer import CodebaseIndexer, invalidate_cache


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


def test_invalidate_cache_removes_only_exact_path_not_same_basename(tmp_path):
    # Index keys are POSIX-normalized relative paths. invalidate_cache must
    # remove only the exact path requested, NOT every entry sharing a basename
    # across different directories (the old basename fallback over-removed).
    index_file = tmp_path / "index.json"
    index_file.write_text(
        json.dumps(
            {
                "files": {
                    "pkg/a.py": {"mtime": 1},
                    "other/a.py": {"mtime": 2},
                    "b.py": {"mtime": 3},
                },
                "total_files": 3,
            }
        ),
        encoding="utf-8",
    )

    invalidate_cache(index_file, [Path("pkg/a.py")])

    data = json.loads(index_file.read_text(encoding="utf-8"))
    assert set(data["files"]) == {"other/a.py", "b.py"}
    assert data["total_files"] == 2
