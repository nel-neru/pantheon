---
name: "source-command-merge-to-main"
description: "完了した作業ブランチを安全に main へ統合する（テストゲート→ff→--no-ff マージ→push）"
---

# source-command-merge-to-main

Use this skill when the user asks to run the migrated source command `merge-to-main`.

## Command Template

# /merge-to-main — 作業ブランチを main へ統合

現在の `work/*` 作業ブランチの作業が **完了** したら、これで main へ混ぜる。
auto-commit フックは各ターンを作業ブランチに積むだけなので、main への統合は
この明示ステップで行う（毎ターンの自動 main コミットは安全上しない）。

## 実行

```powershell
node scripts/merge_to_main.mjs
```

オプション:

- `--no-test` — テストゲートをスキップ（非推奨。CI/手元検証済みのときのみ）
- `--stay` — マージ後 main に留まる（既定は作業ブランチへ戻る）
- `--delete-branch` — 統合後にローカル/リモートの作業ブランチを削除
- `--dry-run` — テストまで実行し、checkout/merge/push はしない

## 挙動（安全策）

1. main/master 上では実行不可（作業ブランチからのみ）
2. 未コミットがあれば中止（通常は Stop フックがコミット済み）
3. `origin` を fetch
4. `pytest tests/` を実行し、**既知ベースライン以外の失敗（新規回帰）が 0 件**であることを確認
5. main へ ff → 作業ブランチを `--no-ff` マージ → `origin/main` へ push（`--force` は使わない）
6. 競合時は `git merge --abort` して中止し、手動解決を促す

完了後は通常どおり新しい作業ブランチで作業を続ける（auto-commit フックが新ブランチを切る）。
