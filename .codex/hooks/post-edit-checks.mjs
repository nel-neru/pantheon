#!/usr/bin/env node
/**
 * Claude Code `PostToolUse` (Write|Edit) dispatcher — Pantheon の軽量検証を1プロセスに集約する。
 *
 * 旧構成では validate-config / check-flows / check-planning-docs が個別フックとして毎回
 * node を 3 回起動していた（無関係ファイルでも cold-start を 3 回払う）。本ディスパッチャは
 * stdin を 1 回だけ読み、編集ファイルに該当する検証だけを走らせる（多くの編集では Python を
 * 一切起動しない）。各検証の relevance 判定・失敗時 exit 2・無関係/想定外 exit 0 の挙動は
 * 元フックと同一。format.mjs（ruff/prettier、重い・専用 60s timeout）は別フックのまま。
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

// 各検証: relevance(norm) が true のときだけ script を実行。label は失敗メッセージ用。
const CHECKS = [
  {
    label: "Pantheon config validation",
    script: "validate_config.py",
    relevant: (norm, ext) =>
      (ext === ".yaml" || ext === ".yml") &&
      (/(^|\/)config\//.test(norm) || /(^|\/)skills\//.test(norm)),
  },
  {
    label: "Atlas flows.json consistency check",
    script: "check_flows.py",
    relevant: (norm) =>
      /core\/atlas\/data\/flows\.json$/.test(norm) ||
      /core\/atlas\/.*\.py$/.test(norm) ||
      /(^|\/)commands\/.*\.py$/.test(norm) ||
      /(^|\/)main\.py$/.test(norm) ||
      /web\/server\.py$/.test(norm) ||
      /web\/frontend\/src\/pages\/.*\.tsx$/.test(norm),
  },
  {
    label: "Planning document hygiene check",
    script: "check_planning_docs.py",
    relevant: (norm) => /(^|\/)docs\/.*\.md$/.test(norm),
  },
];

try {
  const { tool_input } = JSON.parse(readFileSync(0, "utf8"));
  const file = tool_input?.file_path;
  if (!file) process.exit(0);

  const norm = file.replace(/\\/g, "/");
  const ext = (norm.match(/\.[^./]+$/)?.[0] ?? "").toLowerCase();

  const applicable = CHECKS.filter((c) => c.relevant(norm, ext));
  if (applicable.length === 0) process.exit(0);

  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const py =
    process.platform === "win32"
      ? join(projectDir, ".venv", "Scripts", "python.exe")
      : join(projectDir, ".venv", "bin", "python");
  if (!existsSync(py)) process.exit(0);

  const failures = [];
  for (const check of applicable) {
    try {
      execFileSync(py, [join(projectDir, "scripts", check.script)], {
        cwd: projectDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (err) {
      const out = `${err.stdout?.toString() ?? ""}${err.stderr?.toString() ?? ""}`.trim();
      failures.push(`${check.label} failed after editing ${norm}:\n${out}`);
    }
  }

  if (failures.length > 0) {
    process.stderr.write(failures.join("\n\n") + "\n");
    process.exit(2);
  }
} catch {
  /* never block on unexpected hook failure */
}
process.exit(0);
