#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) hook — Atlas の flows.json 整合性を検証する。
 *
 * flows.json 本体、または flows が参照しうる「面」のファイル（commands/*.py, main.py,
 * web/server.py, core/atlas/*.py, web frontend の pages/*.tsx）を編集したら
 * `scripts/check_flows.py` を実行し、flows.json が壊れていない／参照先ファイルが実在する
 * ことを確認する（= 「meta 変更時は flows.json も更新する」を後押し）。
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
  const relevant =
    /core\/atlas\/data\/flows\.json$/.test(norm) ||
    /core\/atlas\/.*\.py$/.test(norm) ||
    /(^|\/)commands\/.*\.py$/.test(norm) ||
    /(^|\/)main\.py$/.test(norm) ||
    /web\/server\.py$/.test(norm) ||
    /web\/frontend\/src\/pages\/.*\.tsx$/.test(norm);
  if (!relevant) process.exit(0);

  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const py =
    process.platform === "win32"
      ? join(projectDir, ".venv", "Scripts", "python.exe")
      : join(projectDir, ".venv", "bin", "python");
  if (!existsSync(py)) process.exit(0);

  try {
    execFileSync(py, [join(projectDir, "scripts", "check_flows.py")], {
      cwd: projectDir,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    const out = `${err.stdout?.toString() ?? ""}${err.stderr?.toString() ?? ""}`.trim();
    process.stderr.write(`Atlas flows.json consistency check failed:\n${out}\n`);
    process.exit(2);
  }
} catch {
  /* never block on unexpected hook failure */
}
process.exit(0);
