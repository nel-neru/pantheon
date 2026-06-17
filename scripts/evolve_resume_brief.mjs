#!/usr/bin/env node
/**
 * evolve_resume_brief.mjs — /evolve 自律ループを中断点から再開するための「現在地ブリーフ」。
 *
 * SessionStart の git スナップショット（.claude/hooks/session-context.mjs）は branch /
 * dirty / last-commit しか出さないため、中断した /evolve を再開するたびに
 * evolution-log と未マージ work ブランチと並行ワーカーのロックを手で読み直す必要があった。
 * このスクリプトはその 3 点をまとめて出力し、再開の立ち上がりを速くする。
 *
 *   - 直近サイクル: docs/plans/evolution-log.md の最新 "Cycle N — …" タイトル＋その Next 候補
 *     （最大日付→同日最大番号で選ぶ。append 方向・番号リスタート混在に頑健）
 *   - 未マージ work ブランチ: origin/main に未統合の work/* （= 続き / 取りこぼし）
 *   - evolve ロック: ~/.pantheon/evolve_resume.lock の pid/経過分（evolve_resume.ps1 が書く位置。
 *     [[concurrent-evolve-worker-hazard]] のシグナル — repo 直下ではない）
 *
 * 使い方:
 *   node scripts/evolve_resume_brief.mjs
 *
 * 任意のフック配線（人間承認が必要 — .claude/hooks/* は protect-secrets ガードで保護される）:
 *   .claude/hooks/session-context.mjs から本スクリプトの stdout を
 *   additionalContext に連結すれば、再開時に自動でブリーフが出る。ガード対象ファイルの
 *   編集は無人運転では権限ゲートで止まるため、配線は人間が承認して行うこと。
 */
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { resolveGit } from "./lib/git_exec.mjs";

const cwd = process.cwd();
const GIT = resolveGit();

function git(args) {
  try {
    return execFileSync(GIT, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    if (e.code === "ENOENT") {
      console.error(`[evolve_resume_brief] git を実行できません (${GIT}): ${e.message}`);
      process.exit(2);
    }
    return e.stdout?.toString() ?? "";
  }
}

/** origin/main を優先、無ければ main を基準 ref として返す（branch_status と同じ規約）。 */
function baseRef() {
  if (git(["rev-parse", "--verify", "--quiet", "origin/main"]).trim()) return "origin/main";
  if (git(["rev-parse", "--verify", "--quiet", "main"]).trim()) return "main";
  return "";
}

/** リポジトリルート（--show-toplevel 優先・失敗時 cwd）。サブディレクトリ実行でも log を見つける。 */
function repoRoot() {
  const top = git(["rev-parse", "--show-toplevel"]).trim();
  return top || cwd;
}

/**
 * 最も新しいサイクルの "Cycle N — …" タイトル行と、そのブロックの "Next:" 行を返す。
 *
 * evolution-log.md は run ごとに追記方向（上/下）が混在し、番号もリスタートしうる
 * （旧 run: Cycle 46→1 を上から / 現 run: Cycle 2→12 を下から）。ファイル位置に依存せず
 * **「タイトル末尾の (YYYY-MM-DD) が最大 → 同日内はサイクル番号が最大」**で最新を選ぶ
 * （番号は1 run 内で単調増加・run 跨ぎは日付で分離）。日付が無い場合はファイル末尾の Cycle に倒す。
 */
function lastCycle() {
  const logPath = join(repoRoot(), "docs", "plans", "evolution-log.md");
  let text = "";
  try {
    text = readFileSync(logPath, "utf8");
  } catch {
    return null;
  }
  const lines = text.split(/\r?\n/);
  let best = null; // { idx, date, num }
  for (let i = 0; i < lines.length; i++) {
    const m = /^Cycle (\d+)\b/.exec(lines[i]);
    if (!m) continue;
    const num = Number(m[1]);
    const dm = /\((\d{4}-\d{2}-\d{2})/.exec(lines[i]);
    const date = dm ? dm[1] : "";
    // 比較キー: 日付（辞書順=時系列）→ サイクル番号 → ファイル位置。日付欠落は最弱。
    if (
      best === null ||
      date > best.date ||
      (date === best.date && num > best.num) ||
      (date === best.date && num === best.num && i > best.idx)
    ) {
      best = { idx: i, date, num };
    }
  }
  if (best === null) return null;
  const titleIdx = best.idx;
  const title = lines[titleIdx].trim();
  // 同ブロック内（次の "Cycle N" まで）の最初の "Next" 行を拾う。
  let next = "";
  for (let i = titleIdx + 1; i < lines.length; i++) {
    if (/^Cycle \d+\b/.test(lines[i])) break;
    if (/^\s*Next\s*:/.test(lines[i])) {
      next = lines[i].trim();
      break;
    }
  }
  return { title, next };
}

/** origin/main（無ければ main）に未統合のローカル work/* ブランチ名一覧。 */
function unmergedWorkBranches(base) {
  if (!base) return [];
  const out = git(["branch", "--no-merged", base, "--list", "work/*", "--format=%(refname:short)"]);
  return out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

function main() {
  if (git(["rev-parse", "--is-inside-work-tree"]).trim() !== "true") {
    console.error("[evolve_resume_brief] git リポジトリ内ではありません。");
    process.exit(1);
  }
  const base = baseRef();
  const cycle = lastCycle();
  const unmerged = unmergedWorkBranches(base);
  // ロックは evolve_resume.ps1 が ~/.pantheon に書く（state はグローバル＝~/.pantheon の規約）。
  // repo 直下ではないことに注意。pid 生存判定は Windows で偽陽性になりうる（[[windows-process-portability]]）
  // ため断定せず、pid と更新経過分を提示し「確認してから動け」に倒す。
  const lockPath = join(homedir(), ".pantheon", "evolve_resume.lock");

  const lines = ["Pantheon /evolve 再開ブリーフ (scripts/evolve_resume_brief.mjs):"];
  if (cycle) {
    lines.push(`- 直近サイクル: ${cycle.title}`);
    if (cycle.next) lines.push(`  ${cycle.next}`);
  } else {
    lines.push("- 直近サイクル: evolution-log.md が無い / Cycle エントリ無し");
  }
  lines.push(
    `- 未マージ work ブランチ (${base || "main"} 基準): ${unmerged.length}` +
      (unmerged.length ? ` — ${unmerged.slice(0, 5).join(", ")}${unmerged.length > 5 ? " …" : ""}` : ""),
  );
  lines.push(`- evolve_resume.lock: ${describeLock(lockPath)}`);

  process.stdout.write(lines.join("\n") + "\n");
}

/** ロックファイルの有無・pid・更新経過分を 1 行で説明する（断定せず確認を促す）。 */
function describeLock(lockPath) {
  if (!existsSync(lockPath)) return "なし";
  let pid = "?";
  let ageMin = "?";
  try {
    pid = readFileSync(lockPath, "utf8").trim().split(/\r?\n/)[0] || "?";
  } catch {
    /* ignore */
  }
  try {
    ageMin = Math.round((Date.now() - statSync(lockPath).mtimeMs) / 60000);
  } catch {
    /* ignore */
  }
  return `あり (pid=${pid}, ${ageMin}分前) — 自セッションか並行ワーカーか pid 生存と mtime を確認してから編集/マージ`;
}

main();
