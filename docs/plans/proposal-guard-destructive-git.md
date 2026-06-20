# 提案: guard-bash.mjs に「未コミット作業を不可逆破壊する git 操作」のブロックを追加

- 状態: **人間レビュー待ち**（セキュリティフック編集はハーネスの sensitive-file 確認ゲートの内側＝無人 /evolve では自己承認しない）
- 起票: Cycle 71（2026-06-20）/evolve 自律ループ。trend-watcher の提案 #1 を実コードで検証し再設計したもの。
- レバレッジ: **高**（/evolve 24/7 無人ループ自身の安全網。auto-commit がまだ捕捉していない新規 untracked module/test や in-flight 編集を、一撃で失う唯一の穴を塞ぐ）
- リスク/可逆性: **低**（work ブランチ＋git＋テストゲートで完全可逆。FP は self-test の ALLOW ケースで担保）

## 背景

現状の `guard-bash.mjs`（PreToolUse: Bash|PowerShell）が防ぐもの:
`rm -rf` 系・`find -delete`・秘密ファイル read/clobber・fork bomb・disk format・raw device write・
`git push --force` / force refspec・`git clean -x`。

**欠けている保護**: 作業ツリー / 未追跡ファイル / stash を **reflog でも復旧不能**な形で破壊する git 操作。
reflog は commit 済み履歴しか追わないため、24/7 無人ループが「直前のミスを戻そう」として
`git reset --hard` 等を自動発火すると、per-turn auto-commit がまだ拾っていない作業
（特に新規作成した untracked な module/test）を不可逆に失う。既存の `git push --force` ゲートと
同じ哲学＝「破壊的 git は人間が端末で明示的に」。

## 追加するブロック（設計確定済み）

| 操作 | ブロック条件 | 通す（ALLOW） |
|------|------|------|
| `git reset --hard` | `--hard` フラグあり | `git reset` / `--soft` / `--mixed` / unstage (`git reset HEAD file`) |
| `git checkout` 破棄形 | `--` pathspec 区切り / 裸の `.` / `-f`･`--force` | ブランチ切替 `git checkout main` / 作成 `-b` / detached `HEAD~1` |
| `git restore` worktree 破棄 | `--worktree` あり、または `--staged` なし | `git restore --staged file`（unstage のみ） |
| `git clean -f` | force あり (`-f`/`--force`)・dry-run でない | `git clean -n` / `--dry-run` |
| `git stash drop`/`clear` | `drop`/`clear` サブコマンド | `git stash` / `push` / `pop` / `list` / `apply` |

スコープ外（意図的）: `git switch`（このリポジトリでは稀。破棄には明示 `--discard-changes`/`-f` が要るため別途）。

## 実装（guard-bash.mjs の RULES 配列直前に挿入する専用ブロック）

```js
// ---------- git ops that IRREVERSIBLY destroy uncommitted / untracked / stashed work ---------- //
// reflog はコミット済み履歴しか追わないため、24/7 /evolve ループで未捕捉作業を一撃で失う。
// 既存の git push --force ゲートの姉妹: 破壊的 git は人間が端末で。ブランチ切替/安全 reset は通す。
// このフックは Bash/PowerShell ツール経由の git だけを見る（auto-commit/merge_to_main は node
// subprocess なので無影響）。git switch はスコープ外。
{
  if (/\bgit\s+reset\b[^&|;]*\s--hard\b/i.test(cmd)) {
    deny("git reset --hard (discards all uncommitted changes; not recoverable via reflog)");
  }
  {
    const m = cmd.match(/\bgit\s+checkout\b([^&|;]*)/i);
    if (m) {
      const rest = m[1];
      const pathspecDiscard = /\s--(\s|$)/.test(rest) || /(^|\s)\.(\s|$)/.test(rest);
      const force = /(^|\s)(--force|-[a-z]*f)/i.test(rest);
      if (pathspecDiscard || force) {
        deny("git checkout that discards working-tree changes (branch off / stash to keep work)");
      }
    }
  }
  {
    const m = cmd.match(/\bgit\s+restore\b([^&|;]*)/i);
    if (m) {
      const rest = m[1];
      const staged = /(^|\s)--staged\b/i.test(rest);
      const worktree = /(^|\s)--worktree\b/i.test(rest);
      if (worktree || !staged) {
        deny("git restore that discards working-tree changes (use --staged to only unstage)");
      }
    }
  }
  {
    const m = cmd.match(/\bgit\s+clean\b([^&|;]*)/i);
    if (m) {
      const rest = m[1];
      const dryRun = /(^|\s)(--dry-run|-[a-z]*n)/i.test(rest);
      const force = /(^|\s)(--force|-[a-z]*f)/i.test(rest);
      const ignored = /(^|\s)-[a-z]*x/i.test(rest);
      if (force && !dryRun) {
        deny(`git clean -f (irreversibly deletes untracked${ignored ? "/gitignored" : ""} files)`);
      }
    }
  }
  if (/\bgit\s+stash\s+(drop|clear)\b/i.test(cmd)) {
    deny("git stash drop/clear (permanently deletes stashed work)");
  }
}
```

既存の `git clean -x` RULES エントリは上記 clean ブロックが内包するので削除してよい
（`git clean -x` は `-f` 無しだと git 自身が拒否する no-op、`-n` dry-run は新ブロックが正しく通す）。

## self-test に追加するケース（`pantheon_hook_selftest.mjs` の GUARD_CASES）

```js
// must DENY
["git reset --hard", bash("git reset --hard"), true],
["git reset --hard HEAD~1", bash("git reset --hard HEAD~1"), true],
["git reset --hard origin/main", bash("git reset --hard origin/main"), true],
["git checkout -- file", bash("git checkout -- core/foo.py"), true],
["git checkout -- .", bash("git checkout -- ."), true],
["git checkout .", bash("git checkout ."), true],
["git checkout -f main", bash("git checkout -f main"), true],
["git checkout tree -- path", bash("git checkout origin/main -- config.yaml"), true],
["git restore file", bash("git restore core/foo.py"), true],
["git restore .", bash("git restore ."), true],
["git restore --worktree --staged", bash("git restore --worktree --staged core/foo.py"), true],
["git clean -fd", bash("git clean -fd"), true],
["git clean -f", bash("git clean -f"), true],
["git stash drop", bash("git stash drop"), true],
["git stash clear", bash("git stash clear"), true],
// must ALLOW
["git reset HEAD file (unstage)", bash("git reset HEAD core/foo.py"), false],
["git reset --soft HEAD~1", bash("git reset --soft HEAD~1"), false],
["git reset --mixed HEAD~1", bash("git reset --mixed HEAD~1"), false],
["git checkout main (switch)", bash("git checkout main"), false],
["git checkout -b work/x", bash("git checkout -b work/feature-20260620"), false],
["git checkout HEAD~1 (detached)", bash("git checkout HEAD~1"), false],
["git restore --staged (unstage)", bash("git restore --staged core/foo.py"), false],
["git clean -n (dry-run)", bash("git clean -n"), false],
["git clean -nd (dry-run dirs)", bash("git clean -nd"), false],
["git stash (save)", bash("git stash"), false],
["git stash pop", bash("git stash pop"), false],
["git stash list", bash("git stash list"), false],
```

## 適用手順（人間が承認できる時）

1. work ブランチを切る（`node scripts/new_work_branch.mjs guard-destructive-git`）。
2. 上記ブロックを `guard-bash.mjs` に挿入＋`git clean -x` 旧ルール削除。
3. self-test に上記ケース追加 → `node .claude/hooks/pantheon_hook_selftest.mjs` が全 pass。
4. `code-reviewer` で敵対的レビュー（FP・regex 抜けを懐疑的に確認）。
5. backend テストゲート（フック変更は backend に無影響だが規律として）→ `merge_to_main.mjs`。
