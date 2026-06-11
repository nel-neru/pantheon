#!/usr/bin/env node
/**
 * merge_to_main.mjs — 完了した作業ブランチを安全に main へ統合する仕組み化スクリプト。
 *
 * 背景: auto-commit フック(.claude/hooks/auto-commit.mjs)は各ターンの作業を
 * `work/auto-<timestamp>` ブランチに積むだけで、main には決して直接コミットしない。
 * 「作業が *完了* したら main に混ぜる」のは明示的な判断なので、毎ターン発火する
 * フックではなく、テストゲート付きの本スクリプト(＋ `/merge-to-main` コマンド)で行う。
 *
 * 手順:
 *   1. 現在ブランチを確認（main/master からは実行不可）
 *   2. 作業ツリーがクリーンか確認（未コミットがあれば中止）
 *   3. origin を fetch
 *   4. バックエンドテストを実行し、既知ベースライン以外の失敗(新規回帰)が無いか確認
 *      （--no-test でスキップ可）
 *   5. main へ checkout → origin/main へ ff → 作業ブランチを --no-ff マージ → push
 *   6. 元の作業ブランチへ戻る（--stay で main に留まる）
 *   7. --delete-branch 指定時はローカル/リモートの作業ブランチを削除
 *
 * 使い方:
 *   node scripts/merge_to_main.mjs [--no-test] [--stay] [--delete-branch] [--dry-run]
 *
 * 安全策: いずれかの git 操作が失敗したら即中止。main の push は通常の fast-forward
 * （--force は使わない）。main が origin から乖離していたら手動解決を促す。
 */
import { execFileSync } from "node:child_process";
import { resolveGit } from "./lib/git_exec.mjs";

const argv = new Set(process.argv.slice(2));
const NO_TEST = argv.has("--no-test");
const STAY = argv.has("--stay");
const DELETE_BRANCH = argv.has("--delete-branch");
const DRY_RUN = argv.has("--dry-run");

// CLAUDE.md に記載の既知失敗（Windows chmod / order-flaky）。
// これらは回帰ではないので、新規失敗の判定から除外する（テスト関数名で照合）。
// CLAUDE.md と同期。**ファイル(::クラス)::関数 のフル nodeid** で照合する
// （関数名だけだと別ファイルの同名テストの回帰を baseline と誤判定するため）。
// 注: 旧 path-separator 4 件は 2026-06-12 に as_posix() 正規化で根治済み。
const KNOWN_BASELINE_FAILURES = new Set([
  "tests/test_web_server.py::test_get_settings_warns_on_open_permissions",
  "tests/test_web_server.py::test_update_settings_sets_restrictive_permissions",
  // order-flaky（単体では通るが全体実行で稀に落ちる）
  "tests/test_theme_fgh_remaining.py::test_backup_manager_cleanup_old",
  "tests/test_self_improvement.py::TestSelfImprovementCycle::test_get_improvement_history",
]);

const PROTECTED = new Set(["main", "master"]);

const GIT = resolveGit();

function git(args, { capture = true } = {}) {
  return execFileSync(GIT, args, {
    encoding: "utf8",
    stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
  });
}

function fail(msg) {
  console.error(`\n[merge_to_main] 中止: ${msg}`);
  process.exit(1);
}

function step(msg) {
  console.log(`\n[merge_to_main] ${msg}`);
}

// --- 1. 現在ブランチ ---
let branch;
try {
  branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).trim();
} catch {
  fail("git リポジトリではありません。");
}
if (PROTECTED.has(branch)) {
  fail(`現在 '${branch}' 上です。作業ブランチから実行してください（main へは直接マージしません）。`);
}

// --- 2. クリーン確認 ---
const dirty = git(["status", "--porcelain"]).trim();
if (dirty) {
  fail(
    "未コミットの変更があります。先にコミットしてください" +
      "（通常は Stop フックが自動コミットします）。\n" +
      dirty,
  );
}

console.log(`[merge_to_main] 作業ブランチ: ${branch}`);
if (DRY_RUN) console.log("[merge_to_main] --dry-run: 実際の checkout/merge/push は行いません。");

// --- 3. fetch ---
step("origin を fetch...");
try {
  git(["fetch", "origin", "--quiet"]);
} catch (e) {
  fail(`fetch に失敗: ${e.message}`);
}

// --- 4. テストゲート ---
if (!NO_TEST) {
  step("バックエンドテストを実行（新規回帰チェック）...");
  const py =
    process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
  let out = "";
  let code = 0;
  try {
    out = execFileSync(py, ["-m", "pytest", "tests/", "-q"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (e) {
    // venv python が見つからない等は status が数値にならない → ハード失敗扱い。
    if (e.code === "ENOENT" || typeof e.status !== "number") {
      fail(
        `pytest を実行できませんでした（venv python が見つからない可能性: ${py}）: ${e.message}`,
      );
    }
    code = e.status;
    out = `${e.stdout ?? ""}${e.stderr ?? ""}`;
  }

  // FAILED だけでなく、収集エラー / fixture ERROR / 中断 / 実行0件も「ハード失敗」とみなす。
  // （FAILED 行ゼロでも壊れているケースをすべて捕捉する）
  const hasErrorMarkers =
    /^ERROR\s/m.test(out) ||
    /errors? during collection/.test(out) ||
    /Interrupted:/.test(out);
  const ranSomething = /\d+\s+passed/.test(out);
  const failed = [...out.matchAll(/^FAILED\s+(\S+)/gm)].map((m) => m[1]);
  const newFailures = failed.filter((nodeid) => {
    const id = nodeid.split("[")[0].replace(/\\/g, "/"); // パラメタ除去 + パス区切り正規化
    return !KNOWN_BASELINE_FAILURES.has(id);
  });

  if (code !== 0 && code !== 1) {
    fail(`pytest が異常終了しました (exit ${code})。収集エラー/使用法エラー等の可能性。`);
  }
  if (hasErrorMarkers) {
    fail(
      "収集エラー / セットアップ ERROR / 中断 を検出しました（FAILED ではなく ERROR）。" +
        "テストが壊れています。修正してください。",
    );
  }
  if (!ranSomething) {
    fail("テストが1件も pass していません（テスト未実行の可能性）。venv とテスト構成を確認してください。");
  }
  if (newFailures.length > 0) {
    fail(
      `既知ベースライン以外のテスト失敗（新規回帰）が ${newFailures.length} 件あります:\n` +
        newFailures.map((f) => `  - ${f}`).join("\n") +
        "\n修正してから再実行するか、確認の上 --no-test を付けてください。",
    );
  }
  console.log(
    `[merge_to_main] テストOK（exit ${code} / 失敗 ${failed.length} 件はすべて既知ベースライン）。`,
  );
}

if (DRY_RUN) {
  step(`dry-run 完了。実行すると: main へ ff → '${branch}' を --no-ff マージ → push します。`);
  process.exit(0);
}

// --- 5. main へ統合 ---
step("main へ checkout...");
try {
  git(["checkout", "main"], { capture: false });
} catch (e) {
  fail(`main への checkout に失敗: ${e.message}`);
}

step("origin/main へ fast-forward...");
try {
  git(["merge", "--ff-only", "origin/main"], { capture: false });
} catch {
  // ローカル main が origin/main より進んでいる/乖離している場合 ff できないことがある。
  // 乖離していなければ続行可能なので、behind のときだけ厳格に扱う。
  const behind = git(["rev-list", "--count", "HEAD..origin/main"]).trim();
  if (behind !== "0") {
    git(["checkout", branch], { capture: false });
    fail(
      "ローカル main が origin/main から乖離しています。手動で解決してから再実行してください。",
    );
  }
}

step(`'${branch}' を main へ --no-ff マージ...`);
try {
  git(["merge", "--no-ff", branch, "-m", `merge: ${branch} → main (completed work)`], {
    capture: false,
  });
} catch (e) {
  git(["merge", "--abort"]);
  git(["checkout", branch], { capture: false });
  fail(`マージで競合が発生しました（自動中止しました）。手動で解決してください: ${e.message}`);
}

step("main を push...");
try {
  git(["push", "origin", "main"], { capture: false });
} catch (e) {
  fail(`push に失敗: ${e.message}`);
}

// --- 6. 後処理 ---
if (!STAY) {
  step(`元の作業ブランチ '${branch}' へ戻ります...`);
  git(["checkout", branch], { capture: false });
}

if (DELETE_BRANCH) {
  step(`作業ブランチ '${branch}' を削除...`);
  try {
    git(["checkout", "main"], { capture: false });
    git(["branch", "-d", branch], { capture: false });
    git(["push", "origin", "--delete", branch], { capture: false });
  } catch (e) {
    console.error(`[merge_to_main] ブランチ削除に失敗（無視可）: ${e.message}`);
  }
}

console.log(`\n[merge_to_main] 完了: '${branch}' を main へ統合し push しました。`);
