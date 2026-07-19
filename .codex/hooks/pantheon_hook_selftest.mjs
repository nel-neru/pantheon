#!/usr/bin/env node
/**
 * Pantheon hook self-test — `node .claude/hooks/pantheon_hook_selftest.mjs`
 *
 * Pipes crafted payloads through the REAL guard-bash.mjs / protect-secrets.mjs scripts and asserts
 * each is blocked (deny) or allowed as expected. Doubles as the regression fixture for the
 * catastrophic-command guard: every known bypass that was once let through is pinned here.
 * Exit 0 = all pass; exit 1 = at least one mismatch (prints the failures).
 */
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const GUARD = join(HERE, "guard-bash.mjs");
const PROTECT = join(HERE, "protect-secrets.mjs");

/** Run a hook with a JSON payload on stdin; return true if it emitted a `deny`. */
function isDenied(script, payload) {
  let out = "";
  try {
    out = execFileSync("node", [script], { input: JSON.stringify(payload), encoding: "utf8" });
  } catch (e) {
    out = (e.stdout || "").toString();
  }
  return /"permissionDecision"\s*:\s*"deny"/.test(out);
}

const bash = (command) => ({ tool_input: { command } });
const edit = (file_path) => ({ tool_input: { file_path } });

// [label, payload, expectDeny]
const GUARD_CASES = [
  // --- must DENY: catastrophic deletes (incl. the historical bypasses) ---
  ["rm -rf /", bash("rm -rf /"), true],
  ["rm -fr /", bash("rm -fr /"), true],
  ["rm -r -f / (split flags)", bash("rm -r -f /"), true],
  ["rm --recursive --force / (long flags)", bash("rm --recursive --force /"), true],
  ["rm -r -f ~", bash("rm -r -f ~"), true],
  ["rm -rf $HOME", bash("rm -rf $HOME"), true],
  ["rm -rf .", bash("rm -rf ."), true],
  ["rm -rf ./", bash("rm -rf ./"), true],
  ["rm -rf *", bash("rm -rf *"), true],
  ["rm --no-preserve-root /", bash("rm --no-preserve-root /"), true],
  // --- must DENY: PowerShell / cmd ---
  ["Remove-Item -Recurse -Force C:\\", bash("Remove-Item -Recurse -Force C:\\"), true],
  ["Remove-Item -Force -Recurse $HOME", bash("Remove-Item -Force -Recurse $HOME"), true],
  ["rd /s /q C:\\", bash("rd /s /q C:\\"), true],
  ["del /s /q C:\\", bash("del /s /q C:\\"), true],
  // --- must DENY: other primitives ---
  ["find / -delete", bash("find / -delete"), true],
  ["find ~ -exec rm", bash("find ~ -exec rm {} ;"), true],
  ["dd of=/dev/sda", bash("dd if=/dev/zero of=/dev/sda"), true],
  ["mkfs", bash("mkfs.ext4 /dev/sdb1"), true],
  ["> /dev/sda", bash("echo x > /dev/sda"), true],
  ["git push --force", bash("git push --force origin main"), true],
  ["git push -f", bash("git push -f origin main"), true],
  ["git push +refspec", bash("git push origin +HEAD:main"), true],
  ["git clean -xfd", bash("git clean -xfd"), true],
  ["fork bomb", bash(":(){ :|:& };:"), true],
  // --- must DENY: secret read / clobber via shell ---
  ["cat .env", bash("cat .env"), true],
  ["Get-Content .env", bash("Get-Content .env"), true],
  ["type secrets.json", bash("type secrets.json"), true],
  ["> .env", bash("echo x > .env"), true],
  ["> secrets.json", bash("echo {} > secrets.json"), true],
  ["truncate server.pem", bash("truncate -s 0 server.pem"), true],
  // --- must DENY: catastrophic-delete SPELLINGS (regression pins from adversarial review) ---
  ["rm -rf /* (root glob)", bash("rm -rf /*"), true],
  ["rm -rf ~/ (home slash)", bash("rm -rf ~/"), true],
  ["rm -rf ~/* (home glob)", bash("rm -rf ~/*"), true],
  ["rm -rf ${HOME}", bash("rm -rf ${HOME}"), true],
  ["rm -rf $HOME/", bash("rm -rf $HOME/"), true],
  ["find /* -delete", bash("find /* -delete"), true],
  // --- must DENY: secret read/exfil/write where the secret is NOT the last token ---
  ["cat .env README.md (secret not last)", bash("cat .env README.md"), true],
  ["head .env > leak.txt (read+exfil)", bash("head .env > leak.txt"), true],
  ["cp .env /public/ (exfil)", bash("cp .env /public/"), true],
  ["wc -l .env", bash("wc -l .env"), true],
  ["grep x .env", bash("grep x .env"), true],
  ["Set-Content .env -Value x", bash("Set-Content .env -Value x"), true],
  ["Out-File .env", bash('"x" | Out-File .env'), true],

  // --- must ALLOW: ordinary dev commands ---
  ["rm -rf node_modules", bash("rm -rf node_modules"), false],
  ["Remove-Item -Recurse -Force node_modules", bash("Remove-Item -Recurse -Force node_modules"), false],
  ["rm -rf /tmp/scratch", bash("rm -rf /tmp/pytest_scratch"), false],
  ["rm -rf ./build", bash("rm -rf ./build"), false],
  ["find . -name *.pyc -delete", bash("find . -name '*.pyc' -delete"), false],
  ["git push origin main", bash("git push origin main"), false],
  ["git commit", bash('git commit -m "x"'), false],
  ["cat README.md", bash("cat README.md"), false],
  ["cat .env.example (template)", bash("cat .env.example"), false],
  ["echo > output.txt", bash("echo hi > output.txt"), false],
  ["npm run build", bash("npm run build"), false],
  ["cat source w/ secret-token name", bash("cat tests/test_secrets.py"), false],
  ["head README.md -n 5", bash("head README.md -n 5"), false],
  ["cp dist/a dist/b", bash("cp dist/a dist/b"), false],
  ["wc -l README.md", bash("wc -l README.md"), false],
  ["grep -rn TODO src/", bash("grep -rn TODO src/"), false],
];

const PROTECT_CASES = [
  // must DENY: real secret/credential files
  [".env", edit(".env"), true],
  [".env.production", edit(".env.production"), true],
  ["server.pem", edit("server.pem"), true],
  ["tls.key", edit("tls.key"), true],
  ["secrets.json", edit("secrets.json"), true],
  ["credentials.json", edit("credentials.json"), true],
  [".npmrc", edit(".npmrc"), true],
  [".git-credentials", edit(".git-credentials"), true],
  ["id_rsa", edit("/home/u/.ssh/id_rsa"), true],
  ["service-account.json", edit("service-account.json"), true],
  ["prod.env (<name>.env)", edit("prod.env"), true],
  ["staging.env", edit("config/staging.env"), true],
  // must ALLOW: templates and ordinary source (incl. files whose NAME has a secret token)
  [".env.example", edit(".env.example"), false],
  ["secret_manager.py", edit("core/secret_manager.py"), false],
  ["test_secrets.py", edit("tests/test_secrets.py"), false],
  ["secrets.py (bare-stem source)", edit("core/secrets.py"), false],
  ["secret.ts (bare-stem source)", edit("web/src/secret.ts"), false],
  ["credentials.js (bare-stem source)", edit("credentials.js"), false],
  ["protect-secrets.mjs (this hook family)", edit(".claude/hooks/protect-secrets.mjs"), false],
  ["sensitive-paths.mjs", edit(".claude/hooks/sensitive-paths.mjs"), false],
  ["README.md", edit("README.md"), false],
];

let failures = 0;
function run(name, script, cases) {
  for (const [label, payload, expectDeny] of cases) {
    const got = isDenied(script, payload);
    if (got !== expectDeny) {
      failures++;
      console.error(`FAIL [${name}] ${label}: expected ${expectDeny ? "DENY" : "ALLOW"}, got ${got ? "DENY" : "ALLOW"}`);
    }
  }
}

run("guard-bash", GUARD, GUARD_CASES);
run("protect-secrets", PROTECT, PROTECT_CASES);

const total = GUARD_CASES.length + PROTECT_CASES.length;
if (failures === 0) {
  console.log(`hook self-test: ${total}/${total} passed`);
  process.exit(0);
} else {
  console.error(`hook self-test: ${failures}/${total} FAILED`);
  process.exit(1);
}
