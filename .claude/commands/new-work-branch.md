---
description: 命名規約に沿った作業ブランチを最新 main から切る
---

# /new-work-branch — 規約準拠の作業ブランチを作成

命名規約: `work/<slug>-<YYYYMMDD>`（slug は kebab-case のトピック）。必ず `work/` プレフィックス。

```powershell
node scripts/new_work_branch.mjs <slug>
```

例: `node scripts/new_work_branch.mjs phase9-foo` → `work/phase9-foo-20260608`（最新 main から分岐）。

オプション:

- `--from-current` — main へ ff せず現在地から切る

挙動: 未コミットがあれば中止 → origin を fetch → main を ff → `work/<slug>-<date>` を作成。
完了後は `/merge-to-main` で main へ統合し、`/branch-status --prune` で done を掃除する。
