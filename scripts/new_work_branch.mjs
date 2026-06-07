#!/usr/bin/env node
/**
 * new_work_branch.mjs — 命名規約に沿った作業ブランチを最新 main から切る。
 *
 * 命名規約（CLAUDE.md / AGENTS.md に明文化）:
 *   work/<slug>-<YYYYMMDD>   … Claude/人が起点の集中作業（slug は kebab-case のトピック）
 *   work/auto-<timestamp>    … auto-commit フックの自動フォールバック（main 起点・無名時）
 *   いずれも必ず `work/` プレフィックス。main へ直接コミットしない。
 *
 * 使い方:
 *   node scripts/new_work_branch.mjs <slug>        # 例: phase9-foo → work/phase9-foo-20260608
 *   node scripts/new_work_branch.mjs <slug> --from-current   # main へ ff せず現在地から切る
 */
import { execFileSync } from "node:child_process";

const argv = process.argv.slice(2);
const FROM_CURRENT = argv.includes("--from-current");
const rawSlug = argv.find((a) => !a.startsWith("--"));

function git(args, { capture = true } = {}) {
  return execFileSync("git", args, {
    encoding: "utf8",
    stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
  });
}
function fail(m) {
  console.error(`\n[new_work_branch] 中止: ${m}`);
  process.exit(1);
}

if (!rawSlug) fail("slug を指定してください。例: node scripts/new_work_branch.mjs phase9-foo");

// slug を kebab-case に正規化（英数とハイフンのみ）
const slug = rawSlug
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, "-")
  .replace(/^-+|-+$/g, "");
if (!slug) fail("slug が空になりました（英数字を含めてください）。");

const dirty = git(["status", "--porcelain"]).trim();
if (dirty) fail("未コミットの変更があります。先にコミット/退避してください。\n" + dirty);

const d = new Date();
const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
const branch = `work/${slug}-${ymd}`;

// 既存チェック
const exists = git(["branch", "--list", branch]).trim();
if (exists) fail(`ブランチ '${branch}' は既に存在します。`);

if (!FROM_CURRENT) {
  git(["fetch", "origin", "--quiet"]);
  git(["checkout", "main"], { capture: false });
  try {
    git(["merge", "--ff-only", "origin/main"], { capture: false });
  } catch {
    console.error("[new_work_branch] 注意: main を origin/main へ ff できませんでした（乖離）。現在の main から切ります。");
  }
}

git(["checkout", "-b", branch], { capture: false });
console.log(`\n[new_work_branch] 作成しました: ${branch}`);
console.log("完了後は `node scripts/merge_to_main.mjs` で main へ統合してください。");
