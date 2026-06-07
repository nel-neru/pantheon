---
description: 作業ブランチを done/active/stale に分類し、終わったブランチを判別する
---

# /branch-status — 作業ブランチの状態を判別

「完了」= **origin/main にマージ済み** を基準に、全ブランチを分類して表示する。

```powershell
node scripts/branch_status.mjs
```

- ✅ **done** — origin/main にマージ済み（固有コミットなし）→ 削除して良い
- 🟡 **active** — main より先行コミットあり（作業中 / 未統合）
- 💤 **stale** — active だが最終コミットが古い（既定 14日超）→ 取り込むか破棄か要確認

オプション:

- `--prune` — done なローカル `work/*` ブランチを削除（掃除）
- `--stale-days N` — stale 判定の日数（既定 14）

関連: 完了ブランチの統合は `/merge-to-main`、新規作成は `/new-work-branch`。
