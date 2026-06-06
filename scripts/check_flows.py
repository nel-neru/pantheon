"""
flows.json staleness / consistency checker.

`core/atlas/data/flows.json`（Atlas の使用フローカタログ）がライブのコード面と
ずれていないかを検証する。新しい meta 変更を入れたら flows.json も更新する、を
強制するためのチェック（PostToolUse フック + test から呼ばれる）。

検証内容（保守的＝誤検知を避ける）:
  - flows.json が有効な JSON で、各フローが必須キーと有効な status を持つ
  - flow id が重複していない
  - verification の "tests/*.py" 参照が実在する
  - steps[].component の「明確に単一ファイルを指すパス」が実在する
    （空白・ワイルドカードを含む説明的コンポーネントは対象外）
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FLOWS_PATH = REPO_ROOT / "core" / "atlas" / "data" / "flows.json"

_REQUIRED_KEYS = {"id", "name", "summary", "trigger", "steps", "surfaces", "status"}
_VALID_STATUS = {"solid", "partial", "fragile", "unknown"}
_FILE_SUFFIXES = (".py", ".tsx", ".ts")


def _is_single_file_path(token: str) -> bool:
    token = token.strip()
    if " " in token or "*" in token or "{" in token:
        return False
    return "/" in token and token.endswith(_FILE_SUFFIXES)


def check_flows() -> list[str]:
    errors: list[str] = []
    if not FLOWS_PATH.exists():
        return [f"flows.json not found: {FLOWS_PATH}"]
    try:
        data = json.loads(FLOWS_PATH.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"flows.json invalid JSON: {exc}"]

    flows = data.get("flows", data) if isinstance(data, dict) else data
    if not isinstance(flows, list) or not flows:
        return ["flows.json has no flows"]

    seen_ids: set[str] = set()
    for index, flow in enumerate(flows):
        fid = str(flow.get("id", ""))
        label = fid or f"#{index}"
        missing = _REQUIRED_KEYS - set(flow)
        if missing:
            errors.append(f"[{label}] missing keys: {sorted(missing)}")
        if flow.get("status") not in _VALID_STATUS:
            errors.append(f"[{label}] invalid status: {flow.get('status')!r}")
        if fid and fid in seen_ids:
            errors.append(f"duplicate flow id: {fid}")
        seen_ids.add(fid)

        for ver in flow.get("verification", []) or []:
            normalized = str(ver).replace("\\", "/").strip()
            if normalized.startswith("tests/") and normalized.endswith(".py"):
                if not (REPO_ROOT / normalized).exists():
                    errors.append(f"[{label}] verification file missing: {normalized}")

        for step in flow.get("steps", []) or []:
            component = str(step.get("component", "")).replace("\\", "/")
            file_part = component.split(":", 1)[0].strip()
            if _is_single_file_path(file_part) and not (REPO_ROOT / file_part).exists():
                errors.append(f"[{label}] step component file missing: {file_part}")

    return errors


def main() -> int:
    errors = check_flows()
    if errors:
        print(f"flows.json consistency check failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"- {error}")
        print("\ncore/atlas/data/flows.json を更新してください（meta 変更時は必須）。")
        return 1
    print("flows.json consistency check passed.")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
