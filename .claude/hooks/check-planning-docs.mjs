#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) hook — Planning Document Hygiene を検証する。
 *
 * docs/ 配下の Markdown を編集したら `scripts/check_planning_docs.py` を実行し、
 * 計画段階ドキュメント（kickoff / inspiration / roadmap / WIP / phaseN 計画）が
 * 恒久フォルダ docs/design/ に誤って置かれていないことを確認する
 * （= 「新しい計画ドキュメントは docs/plans/ へ」を後押し）。
 *
 * 失敗時は stderr に内容を出して exit 2（Claude にフィードバック）。無関係ファイルや
 * 想定外エラーでは常に exit 0（編集をブロックしない）。
 */
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";

try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  const file = tool_input?.file_path;
  if (!file) process.exit(0);

  const norm = file.replace(/\\/g, "/");
  // docs/ 配下の .md を触ったときだけ検査（とくに docs/design/ への誤配置を防ぐ）。
  const relevant = /(^|\/)docs\/.*\.md$/.test(norm);
  if (!relevant) process.exit(0);

  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const py =
    process.platform === "win32"
      ? join(projectDir, ".venv", "Scripts", "python.exe")
      : join(projectDir, ".venv", "bin", "python");
  if (!existsSync(py)) process.exit(0);

  try {
    execFileSync(py, [join(projectDir, "scripts", "check_planning_docs.py")], {
      cwd: projectDir,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    const out = `${err.stdout?.toString() ?? ""}${err.stderr?.toString() ?? ""}`.trim();
    process.stderr.write(`Planning document hygiene check failed:\n${out}\n`);
    process.exit(2);
  }
} catch {
  /* never block on unexpected hook failure */
}
process.exit(0);
