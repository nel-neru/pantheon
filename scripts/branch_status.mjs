#!/usr/bin/env node
/**
 * branch_status.mjs — 作業ブランチの状態を分類して「終わったブランチ」を判別できる仕組み。
 *
 * 「完了」の最も確実なシグナルは **origin/main にマージ済みか** どうか。
 * 各ブランチを以下に分類して一覧する:
 *   ✅ done    — origin/main にマージ済み（main に固有コミットが残っていない）→ 削除して良い
 *   🟡 active  — main より先行コミットがある（作業中 / 未統合）
 *   💤 stale   — active だが最終コミットが古い（要確認: 取り込むか破棄か）
 *
 * 使い方:
 *   node scripts/branch_status.mjs            # 全ブランチを分類表示
 *   node scripts/branch_status.mjs --prune    # done のローカル作業ブランチ(work/*)を削除
 *   node scripts/branch_status.mjs --stale-days 21   # stale 判定の日数(既定14)
 */
import { execFileSync } from "node:child_process";
import { resolveGit } from "./lib/git_exec.mjs";

const argv = process.argv.slice(2);
const PRUNE = argv.includes("--prune");
const staleIdx = argv.indexOf("--stale-days");
const STALE_DAYS = staleIdx >= 0 ? Number(argv[staleIdx + 1]) || 14 : 14;

const GIT = resolveGit();

function git(args) {
  try {
    return execFileSync(GIT, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    // git コマンド自体の失敗（存在しない ref 等）は stdout を返して続行するが、
    // git が実行できない（ENOENT）のを握りつぶすと「全ブランチ 0 件」と誤報告するため fail-fast。
    if (e.code === "ENOENT") {
      console.error(`[branch_status] git を実行できません (${GIT}): ${e.message}`);
      process.exit(2);
    }
    return e.stdout?.toString() ?? "";
  }
}

// main の参照（origin/main 優先、無ければ main）
const haveOriginMain = git(["rev-parse", "--verify", "origin/main"]).trim();
const MAIN = haveOriginMain ? "origin/main" : "main";

// fetch は成否を検証して記録する（--prune の -D フォールバックは「origin/main が
// 最新」という前提に依存するため、fetch 失敗時はフォールバックを無効化する）。
function fetchOrigin() {
  try {
    execFileSync(GIT, ["fetch", "origin", "--quiet"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return true;
  } catch {
    return false;
  }
}
const FETCH_OK = fetchOrigin();

const currentBranch = git(["rev-parse", "--abbrev-ref", "HEAD"]).trim();

// ローカル + リモート(origin/)のブランチを収集（HEAD ポインタや main/master は除外）
const locals = git(["branch", "--format=%(refname:short)"])
  .split("\n")
  .map((s) => s.trim())
  .filter(Boolean);
const remotes = git(["branch", "-r", "--format=%(refname:short)"])
  .split("\n")
  .map((s) => s.trim())
  .filter((s) => s && !s.includes("->"));

const all = new Map(); // name -> {local, remote}
for (const b of locals) {
  if (b === "main" || b === "master") continue;
  all.set(b, { name: b, local: true, remote: false });
}
for (const r of remotes) {
  const name = r.replace(/^origin\//, "");
  // origin/HEAD の short 形が "origin" になるケースや main/master を除外
  if (!name || name === "origin" || name === "main" || name === "master" || name === "HEAD") continue;
  const e = all.get(name) || { name, local: false, remote: false };
  e.remote = true;
  e.remoteRef = r;
  all.set(name, e);
}

const nowMs = Date.now();
const done = [];
const active = [];
const stale = [];

// 先行コミットが ancestry 上は未マージでも、squash / rebase / 再適用マージで
// 同じ変更が main に入っているケースがある（patch-id 等価）。`git cherry MAIN ref`
// は ref 固有の各コミットを、main に等価コミットが在れば "-"、無ければ "+" で示す。
// "+"（=真に未統合）が 0 件なら、ancestry 上 ahead でも実質 done＝削除して良い。
function genuinelyAhead(ref, ahead) {
  if (ahead === 0) return 0;
  const lines = git(["cherry", MAIN, ref])
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  // 注意: git cherry は merge コミットを除外するため、merge を含む範囲では
  // 行数 < ahead が普通（行数 !== ahead を異常扱いにしてはならない＝true-done を
  // false-active に落とす）。content コミットは merge 経由でも必ず行に出るので、
  // 「+ が 0 件」判定は安全。空（cherry 異常）時のみ保守的に「全件未統合」とみなす。
  if (lines.length === 0) return ahead;
  return lines.filter((l) => l.startsWith("+")).length;
}

for (const entry of all.values()) {
  const ref = entry.local ? entry.name : entry.remoteRef;
  const ahead = Number(git(["rev-list", "--count", `${MAIN}..${ref}`]).trim() || "0");
  const unmerged = genuinelyAhead(ref, ahead);
  // ahead>0 だが未統合コミットが 0＝再適用/squash 済み（patch 等価）→ done 扱い。
  const reapplied = ahead > 0 && unmerged === 0;
  const lastIso = git(["log", "-1", "--format=%cI", ref]).trim();
  const ageDays = lastIso ? Math.floor((nowMs - Date.parse(lastIso)) / 86400000) : 0;
  const info = { ...entry, ahead, unmerged, reapplied, ageDays, lastIso };
  if (ahead === 0 || reapplied) {
    done.push(info);
  } else if (ageDays > STALE_DAYS) {
    stale.push(info);
  } else {
    active.push(info);
  }
}

function fmt(b) {
  const where = [b.local ? "local" : null, b.remote ? "remote" : null].filter(Boolean).join("+");
  const cur = b.name === currentBranch ? " (current)" : "";
  const age = b.lastIso ? `${b.ageDays}d ago` : "?";
  // 再適用済み（patch 等価で main に在るが ancestry 上は ahead）は理由を明示する。
  const reason = b.reapplied ? `  ・再適用/squash 済み（patch 等価, 未統合 0/${b.ahead}）` : "";
  return `  ${b.name}${cur}  [${where}]  ahead ${b.ahead}  ・最終 ${age}${reason}`;
}

console.log(`\nブランチ状態（基準: ${MAIN}, stale 閾値: ${STALE_DAYS}日）\n`);
console.log(`✅ done（main に統合済み・削除可）: ${done.length}`);
done.forEach((b) => console.log(fmt(b)));
console.log(`\n🟡 active（未統合・作業中）: ${active.length}`);
active.forEach((b) => console.log(fmt(b)));
console.log(`\n💤 stale（未統合だが ${STALE_DAYS}日以上更新なし・要確認）: ${stale.length}`);
stale.forEach((b) => console.log(fmt(b)));

// git() は失敗時も stdout を返して続行する設計（表示系には正しい）ため、削除のような
// 「成否が結果そのもの」の操作には使わない — かつて -d の拒否を「削除:」と誤報告していた。
function deleteBranch(name, flag) {
  try {
    execFileSync(GIT, ["branch", flag, name], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      // -D 昇格判定が stderr の英語定型句に依存するため、メッセージをロケール非依存に固定する。
      env: { ...process.env, LC_ALL: "C" },
    });
    return null;
  } catch (e) {
    return (e.stderr?.toString() || e.message || "unknown error").trim();
  }
}

if (PRUNE) {
  const prunable = done.filter((b) => b.local && b.name.startsWith("work/") && b.name !== currentBranch);
  console.log(`\n--prune: done なローカル work/* を削除します（${prunable.length} 件）`);
  // -D フォールバックの安全性根拠は done の 2 経路いずれも「変更は origin/main に在る」:
  //   (a) ancestry-done: origin/main..branch が 0 件 → 先行分も origin/main に含まれる。
  //   (b) reapplied: `git cherry origin/main branch` の未統合(+)が 0 件 → 各コミットは
  //       patch 等価で origin/main に在る（squash / rebase / 再適用マージ）。
  // どちらの論証も MAIN が実際に origin/main で、かつ fetch 成功＝最新のときだけ成立する。
  // どちらかが欠けるなら -d のみ（git 自身の保護に任せ、拒否は正直に失敗報告）。
  const forceOk = MAIN === "origin/main" && FETCH_OK;
  if (!forceOk) {
    console.log(
      `  注意: -D フォールバック無効（MAIN=${MAIN}, fetch=${FETCH_OK ? "ok" : "failed"}）— -d で拒否されたものは失敗として報告します`,
    );
  }
  let failures = 0;
  const remoteLeft = [];
  for (const b of prunable) {
    let err = deleteBranch(b.name, "-d");
    let usedForce = false;
    // -D へ昇格するのは「merge 済みでないと拒否された」場合だけ（worktree 使用中や
    // ロック等の予期しない失敗を力業で踏み抜かない）。
    if (err && forceOk && /not fully merged/.test(err)) {
      const err2 = deleteBranch(b.name, "-D");
      if (err2 === null) {
        usedForce = true;
        err = null;
      } else {
        err = err2;
      }
    }
    if (err) {
      failures += 1;
      console.error(`  失敗: ${b.name}: ${err}`);
      continue;
    }
    if (usedForce) {
      const why = b.reapplied
        ? "再適用/squash 済み（patch 等価）のため -D。変更は origin/main に在り"
        : "upstream 未同期のため -D。コミットは origin/main 統合済み";
      console.log(`  削除: ${b.name}（${why}）`);
    } else {
      console.log(`  削除: ${b.name}`);
      // リモート削除のヒントは通常 -d で消せたものだけに出す。-D 経路はローカルと
      // upstream の食い違いを示しており、リモート tip の削除を一律に誘導しない。
      if (b.remote) remoteLeft.push(b.name);
    }
  }
  if (remoteLeft.length > 0) {
    console.log(
      `  残りのリモートブランチ（消す場合は手動で）: ${remoteLeft
        .map((n) => `git push origin --delete ${n}`)
        .join(" / ")}`,
    );
  }
  if (failures > 0) process.exitCode = 1;
}

console.log(
  "\nヒント: 完了したら `node scripts/merge_to_main.mjs` で main へ統合。" +
    " done ブランチの掃除は `node scripts/branch_status.mjs --prune`。",
);
