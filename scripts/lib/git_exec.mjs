#!/usr/bin/env node
/**
 * git_exec.mjs — scripts/ 共通の git 実体解決ヘルパ。
 *
 * 背景: PATH に git が無い環境（例: 一部の PowerShell セッション）では
 * `execFileSync("git", ...)` が ENOENT を投げる。これを握りつぶすと
 * branch_status.mjs が「全ブランチ 0 件」と誤報告するような実害が出る（2026-06-12 実発生）。
 * ここで git 実体を一度だけ解決し、見つからなければ明確に fail-fast する。
 *
 * 解決順:
 *   1. 環境変数 PANTHEON_GIT（明示上書き・テスト用）
 *   2. PATH 上の "git"
 *   3. Git for Windows の標準インストール先（win32 のみ）
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

let cached = null;

function canRun(cmd) {
  try {
    execFileSync(cmd, ["--version"], { stdio: "ignore" });
    return true;
  } catch (e) {
    // 実行はできたが失敗した（≒実体は存在する）場合は ENOENT 以外になる
    return e.code !== "ENOENT";
  }
}

export function resolveGit() {
  if (cached) return cached;

  const override = process.env.PANTHEON_GIT;
  if (override) {
    if (!canRun(override)) {
      console.error(`[git] PANTHEON_GIT に指定された git を実行できません: ${override}`);
      process.exit(2);
    }
    cached = override;
    return cached;
  }

  if (canRun("git")) {
    cached = "git";
    return cached;
  }

  if (process.platform === "win32") {
    const fallbacks = [
      "C:\\Program Files\\Git\\cmd\\git.exe",
      "C:\\Program Files (x86)\\Git\\cmd\\git.exe",
      process.env.LOCALAPPDATA ? `${process.env.LOCALAPPDATA}\\Programs\\Git\\cmd\\git.exe` : null,
    ];
    for (const p of fallbacks) {
      if (p && existsSync(p)) {
        cached = p;
        return cached;
      }
    }
  }

  console.error(
    "[git] git が見つかりません（PATH にも標準インストール先にも無し）。" +
      "PATH へ git を追加するか、環境変数 PANTHEON_GIT で git 実体のパスを指定してください。",
  );
  process.exit(2);
}
